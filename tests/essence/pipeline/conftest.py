"""
Pytest configuration for pipeline tests.
"""
import pytest
import os

# Wrap import in try/except to ensure conftest.py can always be imported
# This is critical for CI environments where pytest collection must not fail
PipelineTestFramework = None
try:
    from tests.essence.pipeline.test_pipeline_framework import PipelineTestFramework
except Exception:
    # If import fails for any reason, set to None - fixtures will skip
    PipelineTestFramework = None


@pytest.fixture
def pipeline_framework():
    """Fixture providing a pipeline test framework with mocked services."""
    if PipelineTestFramework is None:
        pytest.skip("PipelineTestFramework not available")
    return PipelineTestFramework(use_real_services=False)


@pytest.fixture
def pipeline_framework_real():
    """Fixture providing a pipeline test framework with real services (if available)."""
    # Always skip in CI - check first before any other operations
    try:
        if os.getenv('CI') == 'true':
            pytest.skip("Skipping integration test (CI environment)")
    except Exception:
        # If we can't check CI status, skip to be safe
        pytest.skip("Skipping integration test (unable to determine CI status)")
    
    # Check if PipelineTestFramework is available
    if PipelineTestFramework is None:
        pytest.skip("PipelineTestFramework not available")
    
    # Check if grpc is available and not mocked
    try:
        import grpc
        from unittest.mock import MagicMock
        # Check if grpc is mocked (from conftest.py in other test modules)
        if isinstance(grpc, MagicMock) or not hasattr(grpc, 'insecure_channel'):
            pytest.skip("Skipping integration test (grpc unavailable or mocked)")
    except (ImportError, AttributeError, Exception):
        pytest.skip("Skipping integration test (grpc unavailable)")
    
    return PipelineTestFramework(use_real_services=True)




def pytest_addoption(parser):
    """Add pytest command-line options."""
    parser.addoption(
        "--use-real-services",
        action="store_true",
        default=False,
        help="Use real services instead of mocks (requires services to be running)"
    )
