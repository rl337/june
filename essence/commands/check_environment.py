"""
Pre-flight environment check command - Validates environment readiness for Phase 10 operational tasks.

Usage:
    poetry run -m essence check-environment

This command performs comprehensive pre-flight checks to ensure the environment is ready
for Phase 10 operational tasks (model download, service startup, etc.):
- Docker and docker compose availability
- GPU availability and NVIDIA Container Toolkit
- Required environment variables (HUGGINGFACE_TOKEN, etc.)
- Model cache directory permissions
- Docker network configuration
- Service definitions in docker-compose.yml

Use this before attempting model downloads or service startup to catch configuration
issues early.
"""
import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from essence.command import Command

logger = logging.getLogger(__name__)


def check_docker_available() -> Tuple[bool, str]:
    """Check if Docker is installed and accessible."""
    try:
        result = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, "Docker command failed"
    except FileNotFoundError:
        return False, "Docker not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "Docker command timed out"
    except Exception as e:
        return False, f"Error checking Docker: {e}"


def check_docker_compose_available() -> Tuple[bool, str]:
    """Check if docker compose is available."""
    try:
        # Try docker compose (V2)
        result = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return True, result.stdout.strip()

        # Try docker-compose (V1)
        result = subprocess.run(
            ["docker-compose", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return True, f"{result.stdout.strip()} (V1 - consider upgrading to V2)"
        return False, "docker compose not found"
    except FileNotFoundError:
        return False, "docker compose not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "docker compose command timed out"
    except Exception as e:
        return False, f"Error checking docker compose: {e}"


def check_gpu_available() -> Tuple[bool, str]:
    """Check if GPU is available via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            # Extract GPU info from output
            lines = result.stdout.split("\n")
            gpu_line = [l for l in lines if "NVIDIA" in l or "GPU" in l]
            if gpu_line:
                return True, gpu_line[0].strip()
            return True, "GPU detected (nvidia-smi successful)"
        return False, "nvidia-smi failed"
    except FileNotFoundError:
        return False, "nvidia-smi not found (NVIDIA drivers may not be installed)"
    except subprocess.TimeoutExpired:
        return False, "nvidia-smi command timed out"
    except Exception as e:
        return False, f"Error checking GPU: {e}"


def check_nvidia_container_toolkit() -> Tuple[bool, str]:
    """Check if NVIDIA Container Toolkit is configured."""
    try:
        # Check if nvidia-container-runtime is available
        result = subprocess.run(
            ["nvidia-container-runtime", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, "nvidia-container-runtime not found"
    except FileNotFoundError:
        return False, "NVIDIA Container Toolkit not installed or not in PATH"
    except subprocess.TimeoutExpired:
        return False, "nvidia-container-runtime command timed out"
    except Exception as e:
        return False, f"Error checking NVIDIA Container Toolkit: {e}"


def check_huggingface_token() -> Tuple[bool, str]:
    """Check if HUGGINGFACE_TOKEN is set."""
    token = os.getenv("HUGGINGFACE_TOKEN")
    if not token:
        return False, "HUGGINGFACE_TOKEN not set (required for gated models)"
    if token == "your_huggingface_token_here":
        return False, "HUGGINGFACE_TOKEN appears to be a placeholder"
    return True, f"HUGGINGFACE_TOKEN is set (length: {len(token)} chars)"


def check_model_cache_directory() -> Tuple[bool, str]:
    """Check if model cache directory exists and is writable."""
    cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/home/rlee/models"))

    if not cache_dir.exists():
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            return True, f"Created model cache directory: {cache_dir}"
        except Exception as e:
            return False, f"Cannot create model cache directory {cache_dir}: {e}"

    if not cache_dir.is_dir():
        return False, f"Model cache path exists but is not a directory: {cache_dir}"

    # Check write permissions
    test_file = cache_dir / ".write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
        return True, f"Model cache directory is writable: {cache_dir}"
    except Exception as e:
        return False, f"Model cache directory is not writable {cache_dir}: {e}"


def check_docker_compose_file() -> Tuple[bool, str]:
    """Check if docker-compose.yml exists."""
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        return False, "docker-compose.yml not found in current directory"

    # Check if required services are defined
    # Note: TensorRT-LLM is expected to be in home_infra (shared-network), not june docker-compose.yml
    try:
        content = compose_file.read_text()
        required_services = [
            "cli-tools"
        ]  # inference-api removed - using TensorRT-LLM from home_infra
        missing_services = [s for s in required_services if f"{s}:" not in content]
        if missing_services:
            return (
                False,
                f"Required services missing in docker-compose.yml: {missing_services}",
            )
        return (
            True,
            f"docker-compose.yml found with required services (TensorRT-LLM expected in home_infra)",
        )
    except Exception as e:
        return False, f"Error reading docker-compose.yml: {e}"


def check_docker_network() -> Tuple[bool, str]:
    """Check if june_network exists."""
    try:
        result = subprocess.run(
            [
                "docker",
                "network",
                "ls",
                "--filter",
                "name=june_network",
                "--format",
                "{{.Name}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "june_network" in result.stdout:
            return True, "june_network exists"
        return (
            False,
            "june_network not found (will be created automatically by docker compose)",
        )
    except Exception as e:
        return False, f"Error checking Docker network: {e}"


class CheckEnvironmentCommand(Command):
    """
    Command for pre-flight environment validation before Phase 10 operational tasks.

    Performs comprehensive checks to ensure the environment is ready for:
    - Model downloads (requires Docker, HUGGINGFACE_TOKEN, writable cache)
    - Service startup (requires Docker, docker compose, GPU, NVIDIA Container Toolkit)
    - Benchmark evaluation (requires all above plus network configuration)

    Provides clear feedback on what's ready and what needs to be configured before
    attempting operational tasks.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "check-environment"
        """
        return "check-environment"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Pre-flight environment check for Phase 10 operational tasks"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures output format options for the environment check report.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Show detailed information for each check",
        )

    def init(self) -> None:
        """
        Initialize check environment command.

        No initialization is needed for this read-only validation tool.
        The command checks system configuration without requiring service setup.
        """
        # No initialization needed for this tool

    def run(self) -> None:
        """
        Run the environment check and generate report.

        Performs comprehensive checks of:
        - Docker and docker compose availability
        - GPU availability and NVIDIA Container Toolkit
        - Required environment variables (HUGGINGFACE_TOKEN)
        - Model cache directory permissions
        - Docker network configuration
        - Service definitions in docker-compose.yml

        Outputs a human-readable report showing what's ready and what needs attention.
        """
        logger.info("Starting environment pre-flight check...")

        checks: List[Tuple[str, Tuple[bool, str]]] = [
            ("Docker", check_docker_available()),
            ("Docker Compose", check_docker_compose_available()),
            ("GPU (nvidia-smi)", check_gpu_available()),
            ("NVIDIA Container Toolkit", check_nvidia_container_toolkit()),
            ("HUGGINGFACE_TOKEN", check_huggingface_token()),
            ("Model Cache Directory", check_model_cache_directory()),
            ("docker-compose.yml", check_docker_compose_file()),
            ("Docker Network", check_docker_network()),
        ]

        # Generate report
        print("=" * 80)
        print("Environment Pre-Flight Check")
        print("=" * 80)
        print()

        all_passed = True
        for name, (passed, message) in checks:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {name}")
            if self.args.verbose or not passed:
                print(f"       {message}")
            if not passed:
                all_passed = False
            print()

        print("=" * 80)
        if all_passed:
            print(
                "✅ All checks passed! Environment is ready for Phase 10 operational tasks."
            )
        else:
            print(
                "❌ Some checks failed. Please fix the issues above before proceeding."
            )
            print()
            print("Common fixes:")
            print("- Install Docker: https://docs.docker.com/get-docker/")
            print(
                "- Install NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            )
            print("- Set HUGGINGFACE_TOKEN: export HUGGINGFACE_TOKEN=your_token_here")
            print("- Check model cache directory permissions")
        print("=" * 80)

        # Exit with error code if checks failed
        if not all_passed:
            sys.exit(1)

    def cleanup(self) -> None:
        """
        Clean up check environment command.

        No cleanup is needed for this read-only tool. The command only checks
        system configuration and does not maintain any persistent resources.
        """
        # No cleanup needed for this tool
        pass
