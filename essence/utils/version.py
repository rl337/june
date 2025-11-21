"""
Version management utilities for June services.

Each service maintains its own version following semantic versioning (MAJOR.MINOR.PATCH).
Versions are stored in VERSION files in each service directory.
"""
import os
import re
from pathlib import Path
from typing import Optional


def get_service_version(service_name: str) -> str:
    """
    Get the version for a specific service.
    
    Args:
        service_name: Name of the service (e.g., 'telegram', 'discord', 'stt', 'tts', 'message-api')
    
    Returns:
        Version string in format MAJOR.MINOR.PATCH (e.g., '1.0.0')
        Defaults to '0.1.0' if version file not found
    """
    # Map service names to their directory paths
    service_dirs = {
        'telegram': 'essence/services/telegram',
        'discord': 'essence/services/discord',
        'stt': 'services/stt',
        'tts': 'services/tts',
        'message-api': 'essence/services/message_api',
    }
    
    # Try to find version from service directory
    project_root = Path(__file__).parent.parent.parent
    service_dir = service_dirs.get(service_name)
    
    if service_dir:
        version_file = project_root / service_dir / 'VERSION'
        if version_file.exists():
            return version_file.read_text().strip()
    
    # Try environment variable as fallback
    env_version = os.getenv(f'{service_name.upper().replace("-", "_")}_VERSION')
    if env_version:
        return env_version
    
    # Default version
    return '0.1.0'


def parse_version(version_str: str) -> tuple[int, int, int]:
    """
    Parse a version string into (major, minor, patch) tuple.
    
    Args:
        version_str: Version string in format MAJOR.MINOR.PATCH
    
    Returns:
        Tuple of (major, minor, patch) integers
    
    Raises:
        ValueError: If version string is invalid
    """
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}. Expected MAJOR.MINOR.PATCH")
    
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def increment_patch_version(version_str: str) -> str:
    """
    Increment the patch version by 1.
    
    Args:
        version_str: Current version string in format MAJOR.MINOR.PATCH
    
    Returns:
        New version string with incremented patch version
    """
    major, minor, patch = parse_version(version_str)
    return f'{major}.{minor}.{patch + 1}'


def increment_minor_version(version_str: str) -> str:
    """
    Increment the minor version by 1 and reset patch to 0.
    
    Args:
        version_str: Current version string in format MAJOR.MINOR.PATCH
    
    Returns:
        New version string with incremented minor version
    """
    major, minor, _ = parse_version(version_str)
    return f'{major}.{minor + 1}.0'


def increment_major_version(version_str: str) -> str:
    """
    Increment the major version by 1 and reset minor and patch to 0.
    
    Args:
        version_str: Current version string in format MAJOR.MINOR.PATCH
    
    Returns:
        New version string with incremented major version
    """
    major, _, _ = parse_version(version_str)
    return f'{major + 1}.0.0'


def set_service_version(service_name: str, version: str) -> None:
    """
    Set the version for a specific service by writing to its VERSION file.
    
    Args:
        service_name: Name of the service
        version: Version string in format MAJOR.MINOR.PATCH
    
    Raises:
        ValueError: If version format is invalid
    """
    # Validate version format
    parse_version(version)
    
    # Map service names to their directory paths
    service_dirs = {
        'telegram': 'essence/services/telegram',
        'discord': 'essence/services/discord',
        'stt': 'services/stt',
        'tts': 'services/tts',
        'message-api': 'essence/services/message_api',
    }
    
    project_root = Path(__file__).parent.parent.parent
    service_dir = service_dirs.get(service_name)
    
    if not service_dir:
        raise ValueError(f"Unknown service: {service_name}")
    
    version_file = project_root / service_dir / 'VERSION'
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(f'{version}\n')
