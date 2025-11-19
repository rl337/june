"""
Pytest configuration for agentic reasoning tests.

Mocks external dependencies to allow testing without full service stack.
"""
import sys
from unittest.mock import MagicMock

# Mock grpc and related modules before any imports
sys.modules['grpc'] = MagicMock()
sys.modules['june_grpc_api'] = MagicMock()
sys.modules['june_grpc_api.llm_pb2'] = MagicMock()
sys.modules['june_grpc_api.llm_pb2_grpc'] = MagicMock()

# Mock OpenTelemetry modules
sys.modules['opentelemetry'] = MagicMock()
sys.modules['opentelemetry.trace'] = MagicMock()
sys.modules['opentelemetry.sdk'] = MagicMock()
sys.modules['opentelemetry.sdk.trace'] = MagicMock()
sys.modules['opentelemetry.sdk.trace.export'] = MagicMock()
sys.modules['opentelemetry.sdk.resources'] = MagicMock()
sys.modules['opentelemetry.exporter'] = MagicMock()
sys.modules['opentelemetry.exporter.jaeger'] = MagicMock()
sys.modules['opentelemetry.exporter.jaeger.thrift'] = MagicMock()
sys.modules['opentelemetry.instrumentation'] = MagicMock()
sys.modules['opentelemetry.instrumentation.grpc'] = MagicMock()

# Mock docker modules
sys.modules['docker'] = MagicMock()
sys.modules['docker.errors'] = MagicMock()

# Create mock trace objects
mock_tracer = MagicMock()
mock_span = MagicMock()
mock_span.__enter__ = MagicMock(return_value=mock_span)
mock_span.__exit__ = MagicMock(return_value=False)
mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)

# Set up opentelemetry.trace to return our mock tracer
import opentelemetry.trace
opentelemetry.trace.get_tracer = MagicMock(return_value=mock_tracer)
opentelemetry.trace.start_as_current_span = MagicMock(return_value=mock_span)
