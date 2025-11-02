"""
Pytest Configuration for Agentic Tests

Provides shared fixtures and configuration for all agentic tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture(scope="session")
def temp_base_dir():
    """Create temporary base directory for all tests."""
    temp_dir = tempfile.mkdtemp(prefix="june_agentic_tests_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def clean_temp_dir():
    """Create clean temporary directory for individual tests."""
    temp_dir = tempfile.mkdtemp(prefix="june_agentic_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


# Pytest markers
pytest_plugins = []


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )
    config.addinivalue_line(
        "markers", "safety: marks tests as safety tests"
    )
    config.addinivalue_line(
        "markers", "regression: marks tests as regression tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
