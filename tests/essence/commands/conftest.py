"""
Pytest configuration for command tests.

Mocks external dependencies to allow testing without full service stack.
"""
import sys
from unittest.mock import MagicMock

# Mock external dependencies before any imports
sys.modules['httpx'] = MagicMock()
sys.modules['grpc'] = MagicMock()
sys.modules['june_grpc_api'] = MagicMock()

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
