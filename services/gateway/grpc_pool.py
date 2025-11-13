"""gRPC connection pooling for Gateway service."""
import asyncio
import logging
import os
import grpc.aio
from typing import Optional, Dict
from contextlib import asynccontextmanager
from prometheus_client import Gauge, Counter

logger = logging.getLogger(__name__)

# Prometheus metrics for gRPC connection pool
GRPC_POOL_SIZE = Gauge(
    'gateway_grpc_pool_size',
    'Current gRPC connection pool size',
    ['service_name']
)
GRPC_POOL_ACTIVE = Gauge(
    'gateway_grpc_pool_active_connections',
    'Active connections in gRPC pool',
    ['service_name']
)
GRPC_POOL_IDLE = Gauge(
    'gateway_grpc_pool_idle_connections',
    'Idle connections in gRPC pool',
    ['service_name']
)
GRPC_POOL_WAIT_TIME = Counter(
    'gateway_grpc_pool_wait_seconds_total',
    'Total time waiting for connections from pool',
    ['service_name']
)
GRPC_POOL_ERRORS = Counter(
    'gateway_grpc_pool_errors_total',
    'Total gRPC connection pool errors',
    ['service_name', 'error_type']
)


class GatewayGrpcConnectionPool:
    """Manages pooled gRPC connections for STT, TTS, and LLM services."""
    
    def __init__(
        self,
        stt_address: str,
        tts_address: str,
        llm_address: str,
        max_connections_per_service: int = 10,
        keepalive_time_ms: int = 30000,
        keepalive_timeout_ms: int = 5000,
        keepalive_permit_without_calls: bool = True,
        http2_max_pings_without_data: int = 0,
        http2_min_time_between_pings_ms: int = 10000,
        http2_min_ping_interval_without_data_ms: int = 300000
    ):
        """Initialize connection pool.
        
        Args:
            stt_address: STT service address (host:port)
            tts_address: TTS service address (host:port)
            llm_address: LLM service address (host:port)
            max_connections_per_service: Maximum connections per service
            keepalive_time_ms: Keepalive time in milliseconds
            keepalive_timeout_ms: Keepalive timeout in milliseconds
            keepalive_permit_without_calls: Allow keepalive pings without active calls
            http2_max_pings_without_data: Max pings without data
            http2_min_time_between_pings_ms: Min time between pings
            http2_min_ping_interval_without_data_ms: Min ping interval without data
        """
        self.stt_address = stt_address
        self.tts_address = tts_address
        self.llm_address = llm_address
        self.max_connections = max_connections_per_service
        
        # Connection pools: service_name -> list of channels
        self._pools: Dict[str, list] = {
            'stt': [],
            'tts': [],
            'llm': []
        }
        
        # Semaphores to limit concurrent connections
        self._semaphores: Dict[str, asyncio.Semaphore] = {
            'stt': asyncio.Semaphore(max_connections_per_service),
            'tts': asyncio.Semaphore(max_connections_per_service),
            'llm': asyncio.Semaphore(max_connections_per_service)
        }
        
        # Active connection counts for metrics
        self._active_counts: Dict[str, int] = {
            'stt': 0,
            'tts': 0,
            'llm': 0
        }
        
        # gRPC channel options for connection pooling and keepalive
        self._channel_options = [
            ('grpc.keepalive_time_ms', keepalive_time_ms),
            ('grpc.keepalive_timeout_ms', keepalive_timeout_ms),
            ('grpc.keepalive_permit_without_calls', keepalive_permit_without_calls),
            ('grpc.http2.max_pings_without_data', http2_max_pings_without_data),
            ('grpc.http2.min_time_between_pings_ms', http2_min_time_between_pings_ms),
            ('grpc.http2.min_ping_interval_without_data_ms', http2_min_ping_interval_without_data_ms),
            ('grpc.max_connection_idle_ms', 300000),  # Close idle connections after 5 minutes
            ('grpc.max_connection_age_ms', 1800000),  # Close connections after 30 minutes
            ('grpc.max_connection_age_grace_ms', 5000),  # Grace period for closing
        ]
        
        self._shutdown = False
        
        # Update initial metrics
        for service_name in ['stt', 'tts', 'llm']:
            GRPC_POOL_SIZE.labels(service_name=service_name).set(max_connections_per_service)
    
    @asynccontextmanager
    async def get_stt_channel(self):
        """Get STT service channel from pool."""
        async with self._get_channel('stt', self.stt_address) as channel:
            yield channel
    
    @asynccontextmanager
    async def get_tts_channel(self):
        """Get TTS service channel from pool."""
        async with self._get_channel('tts', self.tts_address) as channel:
            yield channel
    
    @asynccontextmanager
    async def get_llm_channel(self):
        """Get LLM service channel from pool."""
        async with self._get_channel('llm', self.llm_address) as channel:
            yield channel
    
    @asynccontextmanager
    async def _get_channel(self, service_name: str, address: str):
        """Get channel from pool or create new one.
        
        Uses semaphore to limit concurrent connections and reuses channels when possible.
        """
        import time
        start_time = time.time()
        
        if self._shutdown:
            raise RuntimeError("Connection pool is shut down")
        
        # Acquire semaphore to limit concurrent connections
        async with self._semaphores[service_name]:
            # Update wait time metric
            wait_time = time.time() - start_time
            GRPC_POOL_WAIT_TIME.labels(service_name=service_name).inc(wait_time)
            
            # Increment active count
            self._active_counts[service_name] += 1
            self._update_metrics(service_name)
            
            # Try to reuse existing channel from pool
            if self._pools[service_name]:
                channel = self._pools[service_name].pop()
                # Check if channel is still ready
                try:
                    state = channel.get_state()
                    if state == grpc.ChannelConnectivity.READY:
                        try:
                            yield channel
                            # Return channel to pool if still ready
                            if channel.get_state() == grpc.ChannelConnectivity.READY:
                                if len(self._pools[service_name]) < self.max_connections:
                                    self._pools[service_name].append(channel)
                                else:
                                    # Pool is full, close the channel
                                    await channel.close()
                            else:
                                # Channel is not ready, close it
                                await channel.close()
                        except Exception as e:
                            logger.warning(f"Error using pooled {service_name} channel: {e}")
                            GRPC_POOL_ERRORS.labels(
                                service_name=service_name,
                                error_type=type(e).__name__
                            ).inc()
                            try:
                                await channel.close()
                            except Exception:
                                pass
                        finally:
                            self._active_counts[service_name] -= 1
                            self._update_metrics(service_name)
                        return
                    else:
                        # Channel not ready, close it
                        try:
                            await channel.close()
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"Error checking {service_name} channel state: {e}")
                    GRPC_POOL_ERRORS.labels(
                        service_name=service_name,
                        error_type=type(e).__name__
                    ).inc()
                    try:
                        await channel.close()
                    except Exception:
                        pass
            
            # Create new channel
            channel = grpc.aio.insecure_channel(address, options=self._channel_options)
            try:
                # Wait for channel to be ready (with timeout)
                try:
                    await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Channel {service_name} connection timeout")
                    GRPC_POOL_ERRORS.labels(
                        service_name=service_name,
                        error_type="timeout"
                    ).inc()
                    await channel.close()
                    raise
                
                yield channel
                
                # Return channel to pool if still ready
                if not self._shutdown and channel.get_state() == grpc.ChannelConnectivity.READY:
                    if len(self._pools[service_name]) < self.max_connections:
                        self._pools[service_name].append(channel)
                    else:
                        # Pool is full, close the channel
                        await channel.close()
                else:
                    await channel.close()
            except Exception as e:
                logger.error(f"Error with {service_name} channel: {e}", exc_info=True)
                GRPC_POOL_ERRORS.labels(
                    service_name=service_name,
                    error_type=type(e).__name__
                ).inc()
                try:
                    await channel.close()
                except Exception:
                    pass
                raise
            finally:
                self._active_counts[service_name] -= 1
                self._update_metrics(service_name)
    
    def _update_metrics(self, service_name: str):
        """Update Prometheus metrics for pool state."""
        try:
            active = self._active_counts[service_name]
            idle = len(self._pools[service_name])
            GRPC_POOL_ACTIVE.labels(service_name=service_name).set(active)
            GRPC_POOL_IDLE.labels(service_name=service_name).set(idle)
        except Exception as e:
            logger.debug(f"Could not update gRPC pool metrics: {e}")
    
    async def shutdown(self):
        """Shutdown connection pool and close all channels."""
        self._shutdown = True
        logger.info("Shutting down gRPC connection pool...")
        
        for service_name in ['stt', 'tts', 'llm']:
            channels = self._pools[service_name]
            self._pools[service_name] = []
            
            for channel in channels:
                try:
                    await channel.close()
                except Exception as e:
                    logger.warning(f"Error closing {service_name} channel: {e}")
        
        logger.info("gRPC connection pool shut down")


# Global connection pool instance
_grpc_pool: Optional[GatewayGrpcConnectionPool] = None


def get_grpc_pool() -> GatewayGrpcConnectionPool:
    """Get global gRPC connection pool instance."""
    global _grpc_pool
    if _grpc_pool is None:
        def get_service_address(env_var: str, default: str) -> str:
            """Get service address from environment variable."""
            url = os.getenv(env_var, default)
            # Remove grpc:// prefix if present
            return url.replace("grpc://", "").replace("http://", "").replace("https://", "")
        
        stt_address = get_service_address("STT_URL", "stt:50052")
        tts_address = get_service_address("TTS_URL", "tts:50053")
        llm_address = get_service_address("INFERENCE_API_URL", "inference-api:50051")
        
        max_connections = int(os.getenv("GRPC_MAX_CONNECTIONS_PER_SERVICE", "10"))
        keepalive_time_ms = int(os.getenv("GRPC_KEEPALIVE_TIME_MS", "30000"))
        keepalive_timeout_ms = int(os.getenv("GRPC_KEEPALIVE_TIMEOUT_MS", "5000"))
        
        _grpc_pool = GatewayGrpcConnectionPool(
            stt_address=stt_address,
            tts_address=tts_address,
            llm_address=llm_address,
            max_connections_per_service=max_connections,
            keepalive_time_ms=keepalive_time_ms,
            keepalive_timeout_ms=keepalive_timeout_ms
        )
    return _grpc_pool


async def shutdown_grpc_pool():
    """Shutdown global gRPC connection pool."""
    global _grpc_pool
    if _grpc_pool is not None:
        await _grpc_pool.shutdown()
        _grpc_pool = None
