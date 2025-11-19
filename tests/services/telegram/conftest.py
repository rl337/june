"""
Pytest configuration for Telegram service tests.

This conftest.py handles the telegram package name conflict between
python-telegram-bot (installed package) and essence/services/telegram (local code).
Also mocks opentelemetry and other dependencies that may not be available in test environment.
"""
import os
import site
import sys
from unittest.mock import MagicMock

# Ensure we import from installed python-telegram-bot, not local telegram dir
# This prevents pytest from trying to import test files as telegram.test_* modules

# Find site-packages directory with telegram (check both system and user)
_site_packages = None
for sp_dir in list(site.getsitepackages()) + [site.getusersitepackages()]:
    if sp_dir and "site-packages" in sp_dir:
        _telegram_pkg_path = os.path.join(sp_dir, "telegram", "__init__.py")
        if os.path.exists(_telegram_pkg_path):
            _site_packages = sp_dir
            break

# Ensure site-packages is in path before test directories
# This ensures python-telegram-bot is found before local telegram code
if _site_packages and _site_packages not in sys.path:
    # Insert at beginning to prioritize installed packages
    sys.path.insert(0, _site_packages)

# Mock opentelemetry before any essence imports (essence.chat.utils.tracing requires it)
# This prevents ModuleNotFoundError when running tests without opentelemetry installed
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()
sys.modules["opentelemetry.sdk"] = MagicMock()
sys.modules["opentelemetry.sdk.trace"] = MagicMock()
sys.modules["opentelemetry.sdk.trace.export"] = MagicMock()
sys.modules["opentelemetry.sdk.resources"] = MagicMock()
sys.modules["opentelemetry.exporter"] = MagicMock()
sys.modules["opentelemetry.exporter.jaeger"] = MagicMock()
sys.modules["opentelemetry.exporter.jaeger.thrift"] = MagicMock()
sys.modules["opentelemetry.instrumentation"] = MagicMock()
sys.modules["opentelemetry.instrumentation.grpc"] = MagicMock()

# Create mock tracer for get_tracer() function
mock_tracer = MagicMock()
mock_tracer.start_as_current_span = MagicMock(return_value=MagicMock())
mock_trace = MagicMock()
mock_trace.get_tracer = MagicMock(return_value=mock_tracer)
sys.modules["opentelemetry.trace"] = mock_trace
