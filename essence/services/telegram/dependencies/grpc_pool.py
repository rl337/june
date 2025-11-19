"""gRPC connection pooling for production use."""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Optional

import grpc.aio

logger = logging.getLogger(__name__)


class GrpcConnectionPool:
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
        http2_max_pings_without_data: int = 2,  # Limit pings to prevent "too_many_pings" error
        http2_min_time_between_pings_ms: int = 10000,
        http2_min_ping_interval_without_data_ms: int = 300000,
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
        self._pools: Dict[str, list] = {"stt": [], "tts": [], "llm": []}

        # Semaphores to limit concurrent connections
        self._semaphores: Dict[str, asyncio.Semaphore] = {
            "stt": asyncio.Semaphore(max_connections_per_service),
            "tts": asyncio.Semaphore(max_connections_per_service),
            "llm": asyncio.Semaphore(max_connections_per_service),
        }

        # gRPC channel options for connection pooling and keepalive
        self._channel_options = [
            ("grpc.keepalive_time_ms", keepalive_time_ms),
            ("grpc.keepalive_timeout_ms", keepalive_timeout_ms),
            ("grpc.keepalive_permit_without_calls", keepalive_permit_without_calls),
            ("grpc.http2.max_pings_without_data", http2_max_pings_without_data),
            ("grpc.http2.min_time_between_pings_ms", http2_min_time_between_pings_ms),
            (
                "grpc.http2.min_ping_interval_without_data_ms",
                http2_min_ping_interval_without_data_ms,
            ),
            (
                "grpc.max_connection_idle_ms",
                300000,
            ),  # Close idle connections after 5 minutes
            (
                "grpc.max_connection_age_ms",
                1800000,
            ),  # Close connections after 30 minutes
            ("grpc.max_connection_age_grace_ms", 5000),  # Grace period for closing
        ]

        self._shutdown = False

    @asynccontextmanager
    async def get_stt_channel(self):
        """Get STT service channel from pool."""
        async with self._get_channel("stt", self.stt_address) as channel:
            yield channel

    @asynccontextmanager
    async def get_tts_channel(self):
        """Get TTS service channel from pool."""
        async with self._get_channel("tts", self.tts_address) as channel:
            yield channel

    @asynccontextmanager
    async def get_llm_channel(self):
        """Get LLM service channel from pool."""
        async with self._get_channel("llm", self.llm_address) as channel:
            yield channel

    @asynccontextmanager
    async def _get_channel(self, service_name: str, address: str):
        """Get channel from pool or create new one.

        Uses semaphore to limit concurrent connections and reuses channels when possible.
        """
        if self._shutdown:
            raise RuntimeError("Connection pool is shut down")

        # Acquire semaphore to limit concurrent connections
        async with self._semaphores[service_name]:
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
                                self._pools[service_name].append(channel)
                            else:
                                # Channel is not ready, close it
                                await channel.close()
                        except Exception as e:
                            logger.warning(
                                f"Error using pooled {service_name} channel: {e}"
                            )
                            try:
                                await channel.close()
                            except Exception:
                                pass
                        return
                    else:
                        # Channel not ready, close it
                        try:
                            await channel.close()
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"Error checking {service_name} channel state: {e}")
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
                    await channel.close()
                    raise

                yield channel

                # Return channel to pool if still ready
                if (
                    not self._shutdown
                    and channel.get_state() == grpc.ChannelConnectivity.READY
                ):
                    if len(self._pools[service_name]) < self.max_connections:
                        self._pools[service_name].append(channel)
                    else:
                        # Pool is full, close the channel
                        await channel.close()
                else:
                    await channel.close()
            except Exception as e:
                logger.error(f"Error with {service_name} channel: {e}", exc_info=True)
                try:
                    await channel.close()
                except Exception:
                    pass
                raise

    async def shutdown(self):
        """Shutdown connection pool and close all channels."""
        self._shutdown = True
        logger.info("Shutting down gRPC connection pool...")

        for service_name in ["stt", "tts", "llm"]:
            channels = self._pools[service_name]
            self._pools[service_name] = []

            for channel in channels:
                try:
                    await channel.close()
                except Exception as e:
                    logger.warning(f"Error closing {service_name} channel: {e}")

        logger.info("gRPC connection pool shut down")


# Global connection pool instance
_pool: Optional[GrpcConnectionPool] = None


def get_grpc_pool() -> GrpcConnectionPool:
    """Get global gRPC connection pool instance."""
    global _pool
    if _pool is None:
        import os

        from dependencies.config import (
            get_llm_address,
            get_stt_address,
            get_tts_address,
        )

        max_connections = int(os.getenv("GRPC_MAX_CONNECTIONS_PER_SERVICE", "10"))
        keepalive_time_ms = int(os.getenv("GRPC_KEEPALIVE_TIME_MS", "30000"))
        keepalive_timeout_ms = int(os.getenv("GRPC_KEEPALIVE_TIMEOUT_MS", "5000"))

        _pool = GrpcConnectionPool(
            stt_address=get_stt_address(),
            tts_address=get_tts_address(),
            llm_address=get_llm_address(),
            max_connections_per_service=max_connections,
            keepalive_time_ms=keepalive_time_ms,
            keepalive_timeout_ms=keepalive_timeout_ms,
        )
    return _pool


async def shutdown_grpc_pool():
    """Shutdown global gRPC connection pool."""
    global _pool
    if _pool is not None:
        await _pool.shutdown()
        _pool = None
