"""
Verify TensorRT-LLM setup and migration status.

This command verifies that TensorRT-LLM is properly set up and can replace the legacy inference-api service.
It checks container status, model repository, model loading, gRPC connectivity, and GPU usage.

Usage:
    poetry run -m essence verify-tensorrt-llm [--tensorrt-llm-url URL] [--grpc-port PORT] [--json]

This command performs comprehensive verification:
- Checks if TensorRT-LLM container is running and accessible
- Verifies model repository structure and accessibility
- Tests model listing and status checking
- Verifies gRPC endpoint connectivity
- Checks GPU availability and usage
- Provides migration readiness assessment
"""
import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Tuple

try:
    import grpc

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False

from essence.command import Command
from essence.commands.manage_tensorrt_llm import TensorRTLLMManager

logger = logging.getLogger(__name__)


def check_container_connectivity(base_url: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if TensorRT-LLM HTTP API is accessible.

    Returns:
        Tuple of (success, message, details_dict)
    """
    manager = TensorRTLLMManager(base_url=base_url, timeout=10)
    success, models, message = manager.list_models()

    details = {
        "base_url": base_url,
        "accessible": success,
        "models_count": len(models) if success else 0,
        "models": models if success else [],
    }

    return success, message, details


def check_grpc_connectivity(grpc_address: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if TensorRT-LLM gRPC endpoint is accessible.

    Returns:
        Tuple of (success, message, details_dict)
    """
    if not GRPC_AVAILABLE:
        return False, "gRPC library not available", {"grpc_available": False}

    details = {
        "grpc_address": grpc_address,
        "grpc_available": True,
        "connectable": False,
    }

    try:
        # Try to create a channel and check connectivity
        channel = grpc.insecure_channel(grpc_address)

        # Try to wait for channel to be ready (with short timeout)
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
            details["connectable"] = True
            channel.close()
            return True, f"gRPC endpoint accessible at {grpc_address}", details
        except grpc.FutureTimeoutError:
            channel.close()
            return (
                False,
                f"gRPC endpoint at {grpc_address} not responding (timeout)",
                details,
            )
        except Exception as e:
            channel.close()
            return False, f"Error checking gRPC connectivity: {e}", details

    except Exception as e:
        return False, f"Failed to check gRPC connectivity: {e}", details


def check_model_repository(repository_path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if model repository directory exists and has proper structure.

    Returns:
        Tuple of (success, message, details_dict)
    """
    from pathlib import Path

    repo_path = Path(repository_path)
    details = {
        "repository_path": str(repo_path),
        "exists": False,
        "is_directory": False,
        "models": [],
    }

    if not repo_path.exists():
        return (
            False,
            f"Model repository directory does not exist: {repository_path}",
            details,
        )

    details["exists"] = True

    if not repo_path.is_dir():
        return (
            False,
            f"Model repository path is not a directory: {repository_path}",
            details,
        )

    details["is_directory"] = True

    # List models in repository
    try:
        models = []
        for model_dir in repo_path.iterdir():
            if model_dir.is_dir():
                versions = [
                    v.name
                    for v in model_dir.iterdir()
                    if v.is_dir() and v.name.isdigit()
                ]
                if versions:
                    models.append(
                        {
                            "name": model_dir.name,
                            "versions": sorted(versions, key=int),
                            "path": str(model_dir),
                        }
                    )
        details["models"] = sorted(models, key=lambda x: x["name"])
        return True, f"Model repository accessible with {len(models)} model(s)", details
    except Exception as e:
        return False, f"Error reading model repository: {e}", details


def check_gpu_availability() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check GPU availability (for container verification).

    Returns:
        Tuple of (success, message, details_dict)
    """
    details = {"gpu_available": False, "gpu_count": 0, "gpu_info": []}

    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            details["gpu_available"] = True
            details["gpu_count"] = len(lines)
            for line in lines:
                parts = line.split(", ")
                if len(parts) >= 3:
                    details["gpu_info"].append(
                        {
                            "name": parts[0],
                            "memory_total": parts[1],
                            "memory_used": parts[2],
                        }
                    )
            return True, f"GPU available: {len(lines)} GPU(s) detected", details
        else:
            return False, "nvidia-smi not available or no GPUs detected", details

    except FileNotFoundError:
        return False, "nvidia-smi not found (GPU may not be available)", details
    except subprocess.TimeoutExpired:
        return False, "nvidia-smi timeout (GPU check failed)", details
    except Exception as e:
        return False, f"Error checking GPU: {e}", details


class VerifyTensorRTLLMCommand(Command):
    """
    Command to verify TensorRT-LLM setup and migration readiness.

    Performs comprehensive checks to ensure TensorRT-LLM is properly configured
    and can replace the legacy inference-api service. This helps determine when
    it's safe to remove inference-api from docker-compose.yml.
    """

    @classmethod
    def get_name(cls) -> str:
        return "verify-tensorrt-llm"

    @classmethod
    def get_description(cls) -> str:
        return "Verify TensorRT-LLM setup and migration readiness"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--tensorrt-llm-url",
            type=str,
            default=os.getenv("TENSORRT_LLM_URL", "http://tensorrt-llm:8002"),
            help="TensorRT-LLM HTTP API URL (default: http://tensorrt-llm:8002)",
        )
        parser.add_argument(
            "--grpc-port",
            type=int,
            default=int(os.getenv("TENSORRT_LLM_GRPC_PORT", "8000")),
            help="TensorRT-LLM gRPC port (default: 8000)",
        )
        parser.add_argument(
            "--grpc-host",
            type=str,
            default=os.getenv("TENSORRT_LLM_HOST", "tensorrt-llm"),
            help="TensorRT-LLM gRPC host (default: tensorrt-llm)",
        )
        parser.add_argument(
            "--repository-path",
            type=str,
            default=os.getenv(
                "TENSORRT_LLM_MODEL_REPOSITORY", "/home/rlee/models/triton-repository"
            ),
            help="Path to Triton model repository (default: /home/rlee/models/triton-repository)",
        )
        parser.add_argument(
            "--json", action="store_true", help="Output results as JSON"
        )

    def init(self) -> None:
        self.results = {
            "container_connectivity": {},
            "grpc_connectivity": {},
            "model_repository": {},
            "gpu_availability": {},
            "overall_status": "unknown",
            "migration_ready": False,
        }

    def run(self) -> None:
        """Run all verification checks."""
        checks_passed = 0
        total_checks = 4

        # Check 1: Container HTTP API connectivity
        print("Checking TensorRT-LLM container connectivity...")
        success, message, details = check_container_connectivity(
            self.args.tensorrt_llm_url
        )
        self.results["container_connectivity"] = {
            "success": success,
            "message": message,
            **details,
        }
        if success:
            checks_passed += 1
            print(f"  ✓ {message}")
        else:
            print(f"  ✗ {message}")

        # Check 2: gRPC connectivity
        grpc_address = f"{self.args.grpc_host}:{self.args.grpc_port}"
        print(f"\nChecking gRPC connectivity ({grpc_address})...")
        success, message, details = check_grpc_connectivity(grpc_address)
        self.results["grpc_connectivity"] = {
            "success": success,
            "message": message,
            **details,
        }
        if success:
            checks_passed += 1
            print(f"  ✓ {message}")
        else:
            print(f"  ✗ {message}")

        # Check 3: Model repository
        print(f"\nChecking model repository ({self.args.repository_path})...")
        success, message, details = check_model_repository(self.args.repository_path)
        self.results["model_repository"] = {
            "success": success,
            "message": message,
            **details,
        }
        if success:
            checks_passed += 1
            print(f"  ✓ {message}")
        else:
            print(f"  ✗ {message}")

        # Check 4: GPU availability
        print("\nChecking GPU availability...")
        success, message, details = check_gpu_availability()
        self.results["gpu_availability"] = {
            "success": success,
            "message": message,
            **details,
        }
        if success:
            checks_passed += 1
            print(f"  ✓ {message}")
        else:
            print(f"  ✗ {message}")

        # Overall assessment
        self.results["checks_passed"] = checks_passed
        self.results["total_checks"] = total_checks

        # Migration is ready if all critical checks pass
        # (container connectivity and gRPC are critical, repository and GPU are important but may be OK if empty/not available)
        critical_checks_passed = (
            self.results["container_connectivity"]["success"]
            and self.results["grpc_connectivity"]["success"]
        )

        self.results["migration_ready"] = critical_checks_passed
        self.results["overall_status"] = (
            "ready" if critical_checks_passed else "not_ready"
        )

        # Print summary
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)
        print(f"Checks passed: {checks_passed}/{total_checks}")
        print(f"Overall status: {self.results['overall_status'].upper()}")
        print(f"Migration ready: {'YES' if self.results['migration_ready'] else 'NO'}")

        if self.results["migration_ready"]:
            print("\n✓ TensorRT-LLM is ready to replace inference-api service.")
            print(
                "  Safe to remove inference-api from docker-compose.yml (with legacy profile)."
            )
        else:
            print("\n✗ TensorRT-LLM is not ready yet.")
            print("  Do not remove inference-api service until all checks pass.")
            print("\nIssues to resolve:")
            if not self.results["container_connectivity"]["success"]:
                print(
                    f"  - Container connectivity: {self.results['container_connectivity']['message']}"
                )
            if not self.results["grpc_connectivity"]["success"]:
                print(
                    f"  - gRPC connectivity: {self.results['grpc_connectivity']['message']}"
                )
            if not self.results["model_repository"]["success"]:
                print(
                    f"  - Model repository: {self.results['model_repository']['message']}"
                )
            if not self.results["gpu_availability"]["success"]:
                print(
                    f"  - GPU availability: {self.results['gpu_availability']['message']}"
                )

        # Output JSON if requested
        if self.args.json:
            print("\n" + json.dumps(self.results, indent=2))

        # Exit with appropriate code
        sys.exit(0 if self.results["migration_ready"] else 1)

    def cleanup(self) -> None:
        pass
