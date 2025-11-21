#!/usr/bin/env python3
"""
Script to increment version for a service.

Usage:
    python scripts/increment_version.py <service_name> [--major|--minor|--patch]

Examples:
    python scripts/increment_version.py telegram --patch  # Increment patch version (default)
    python scripts/increment_version.py telegram --minor  # Increment minor version
    python scripts/increment_version.py telegram --major  # Increment major version
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from essence.utils.version import (
    get_service_version,
    increment_major_version,
    increment_minor_version,
    increment_patch_version,
    set_service_version,
)


def main():
    """Main entry point for version increment script."""
    parser = argparse.ArgumentParser(
        description="Increment version for a service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s telegram --patch  # Increment patch version (default)
  %(prog)s telegram --minor  # Increment minor version
  %(prog)s telegram --major  # Increment major version
        """,
    )
    parser.add_argument(
        "service",
        choices=["telegram", "discord", "stt", "tts", "message-api"],
        help="Service name to increment version for",
    )
    parser.add_argument(
        "--major",
        action="store_true",
        help="Increment major version (resets minor and patch to 0)",
    )
    parser.add_argument(
        "--minor",
        action="store_true",
        help="Increment minor version (resets patch to 0)",
    )
    parser.add_argument(
        "--patch",
        action="store_true",
        default=True,
        help="Increment patch version (default)",
    )

    args = parser.parse_args()

    # Get current version
    current_version = get_service_version(args.service)
    print(f"Current version for {args.service}: {current_version}")

    # Determine increment type
    if args.major:
        new_version = increment_major_version(current_version)
        increment_type = "major"
    elif args.minor:
        new_version = increment_minor_version(current_version)
        increment_type = "minor"
    else:
        new_version = increment_patch_version(current_version)
        increment_type = "patch"

    # Set new version
    set_service_version(args.service, new_version)
    print(f"Incremented {increment_type} version: {current_version} -> {new_version}")
    print(f"Updated VERSION file for {args.service}")


if __name__ == "__main__":
    main()
