"""
Pytest configuration for Telegram service tests.

This conftest.py handles the telegram package name conflict between
python-telegram-bot (installed package) and essence/services/telegram (local code).
"""
import sys
import os
import site

# Ensure we import from installed python-telegram-bot, not local telegram dir
# This prevents pytest from trying to import test files as telegram.test_* modules

# Find site-packages directory with telegram (check both system and user)
_site_packages = None
for sp_dir in list(site.getsitepackages()) + [site.getusersitepackages()]:
    if sp_dir and 'site-packages' in sp_dir:
        _telegram_pkg_path = os.path.join(sp_dir, 'telegram', '__init__.py')
        if os.path.exists(_telegram_pkg_path):
            _site_packages = sp_dir
            break

# Ensure site-packages is in path before test directories
# This ensures python-telegram-bot is found before local telegram code
if _site_packages and _site_packages not in sys.path:
    # Insert at beginning to prioritize installed packages
    sys.path.insert(0, _site_packages)
