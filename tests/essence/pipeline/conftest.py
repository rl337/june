"""
Pytest configuration for pipeline tests.
"""
import pytest
from tests.essence.pipeline.test_pipeline_framework import PipelineTestFramework


@pytest.fixture
def pipeline_framework():
    """Fixture providing a pipeline test framework with mocked services."""
    return PipelineTestFramework(use_real_services=False)


@pytest.fixture
def pipeline_framework_real():
    """Fixture providing a pipeline test framework with real services (if available)."""
    # Check if real services are available
    use_real = pytest.config.getoption("--use-real-services", default=False)
    return PipelineTestFramework(use_real_services=use_real)


def pytest_addoption(parser):
    """Add pytest command-line options."""
    parser.addoption(
        "--use-real-services",
        action="store_true",
        default=False,
        help="Use real services instead of mocks (requires services to be running)"
    )
