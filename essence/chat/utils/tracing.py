"""
Tracing utilities for OpenTelemetry integration with Jaeger.

This module provides tracing setup and utilities for instrumenting
the chat agent streaming pipeline.
"""
import os
import logging
from typing import Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Import gRPC instrumentation for automatic trace propagation
try:
    from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
    from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
    GRPC_INSTRUMENTATION_AVAILABLE = True
except ImportError:
    # Try alternative import pattern
    try:
        from opentelemetry.instrumentation.grpc import GrpcInstrumentor
        GRPC_INSTRUMENTATION_AVAILABLE = True
        GrpcInstrumentorClient = GrpcInstrumentor
        GrpcInstrumentorServer = GrpcInstrumentor
    except ImportError:
        GRPC_INSTRUMENTATION_AVAILABLE = False
        GrpcInstrumentorClient = None
        GrpcInstrumentorServer = None
        GrpcInstrumentor = None

logger = logging.getLogger(__name__)

_tracer_provider: Optional[TracerProvider] = None
_grpc_client_instrumentor: Optional[GrpcInstrumentorClient] = None
_grpc_server_instrumentor: Optional[GrpcInstrumentorServer] = None


def setup_tracing(service_name: str = "june-telegram", jaeger_endpoint: Optional[str] = None):
    """
    Setup OpenTelemetry tracing with Jaeger exporter.
    
    Args:
        service_name: Name of the service for tracing
        jaeger_endpoint: Jaeger endpoint URL (defaults to common-jaeger:14268)
    """
    global _tracer_provider
    
    if _tracer_provider is not None:
        logger.info("Tracing already initialized")
        return
    
    # Get Jaeger endpoint from config or environment
    if jaeger_endpoint is None:
        jaeger_endpoint = os.getenv(
            "JAEGER_ENDPOINT",
            "http://common-jaeger:14268/api/traces"
        )
    
    # Check if tracing is enabled
    enable_tracing = os.getenv("ENABLE_TRACING", "true").lower() == "true"
    if not enable_tracing:
        logger.info("Tracing is disabled")
        return
    
    try:
        # Create resource with service name
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0"
        })
        
        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)
        
        # Create Jaeger exporter
        # JaegerExporter uses agent_host_name and agent_port for UDP, or collector_endpoint for HTTP
        jaeger_agent_host = os.getenv("JAEGER_AGENT_HOST", "common-jaeger")
        jaeger_agent_port = int(os.getenv("JAEGER_AGENT_PORT", "6831"))
        
        # Use collector_endpoint for HTTP (port 14268) or agent for UDP (port 6831)
        # Try HTTP collector endpoint first
        collector_endpoint = os.getenv("JAEGER_COLLECTOR_ENDPOINT", f"http://{jaeger_agent_host}:14268/api/traces")
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_agent_host,
            agent_port=jaeger_agent_port,
            collector_endpoint=collector_endpoint
        )
        
        # Add span processor
        span_processor = BatchSpanProcessor(jaeger_exporter)
        _tracer_provider.add_span_processor(span_processor)
        
        # Set as global tracer provider
        trace.set_tracer_provider(_tracer_provider)
        
        # Enable gRPC instrumentation for automatic trace context propagation
        if GRPC_INSTRUMENTATION_AVAILABLE:
            global _grpc_client_instrumentor, _grpc_server_instrumentor
            try:
                # Instrument gRPC clients (for outgoing calls)
                _grpc_client_instrumentor = GrpcInstrumentorClient()
                _grpc_client_instrumentor.instrument()
                
                # Instrument gRPC servers (for incoming calls)
                _grpc_server_instrumentor = GrpcInstrumentorServer()
                _grpc_server_instrumentor.instrument()
                
                logger.info("gRPC instrumentation enabled for automatic trace context propagation")
            except Exception as e:
                logger.warning(f"Failed to enable gRPC instrumentation: {e}. Trace context may not propagate across gRPC calls.")
        else:
            logger.warning("opentelemetry-instrumentation-grpc not available. Trace context may not propagate across gRPC calls.")
        
        logger.info(f"Tracing initialized for service '{service_name}' with Jaeger endpoint: {jaeger_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to initialize tracing: {e}. Continuing without tracing.")


def get_tracer(name: str = __name__):
    """
    Get a tracer instance.
    
    Args:
        name: Name of the tracer (usually __name__)
    
    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)


def get_or_create_tracer(name: str = __name__):
    """
    Get or create a tracer, initializing tracing if needed.
    
    Args:
        name: Name of the tracer
    
    Returns:
        Tracer instance
    """
    if _tracer_provider is None:
        setup_tracing()
    return get_tracer(name)

