"""
Verify NVIDIA NIM (NVIDIA Inference Microservice) setup and connectivity.

This command verifies that a NIM service is properly set up and accessible.
It checks HTTP health endpoint, gRPC connectivity, and optionally tests gRPC protocol compatibility.

Usage:
    poetry run python -m essence verify-nim [--nim-host HOST] [--http-port PORT] [--grpc-port PORT] [--json]

This command performs comprehensive verification:
- Checks if NIM HTTP health endpoint is accessible
- Verifies gRPC endpoint connectivity
- Optionally tests gRPC protocol compatibility (HealthCheck RPC)
- Checks GPU availability (if accessible)
"""
import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Tuple

try:
    import grpc

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from essence.command import Command

logger = logging.getLogger(__name__)


def check_http_health(
    base_url: str, timeout: int = 10
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if NIM HTTP health endpoint is accessible.

    Returns:
        Tuple of (success, message, details_dict)
    """
    if not HTTPX_AVAILABLE:
        return False, "httpx library not available", {"httpx_available": False}

    details = {
        "base_url": base_url,
        "httpx_available": True,
        "accessible": False,
        "status_code": None,
        "response": None,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base_url}/health")
            details["status_code"] = response.status_code
            details["response"] = response.text if response.status_code == 200 else None
            details["accessible"] = response.status_code == 200

            if response.status_code == 200:
                return (
                    True,
                    f"HTTP health endpoint accessible at {base_url}/health",
                    details,
                )
            else:
                return (
                    False,
                    f"HTTP health endpoint returned status {response.status_code}",
                    details,
                )
    except httpx.TimeoutException:
        return False, f"HTTP health endpoint timeout at {base_url}/health", details
    except httpx.ConnectError:
        return (
            False,
            f"HTTP health endpoint not reachable at {base_url}/health",
            details,
        )
    except Exception as e:
        return False, f"Error checking HTTP health: {e}", details


def check_grpc_connectivity(grpc_address: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if NIM gRPC endpoint is accessible.

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


def check_grpc_protocol_compatibility(
    grpc_address: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if NIM gRPC endpoint supports the expected protocol (HealthCheck RPC).

    This verifies that the NIM service uses the same gRPC protocol as TensorRT-LLM,
    which allows june services to use NIM as a drop-in replacement.

    Returns:
        Tuple of (success, message, details_dict)
    """
    if not GRPC_AVAILABLE:
        return False, "gRPC library not available", {"grpc_available": False}

    details = {
        "grpc_address": grpc_address,
        "grpc_available": True,
        "protocol_compatible": False,
        "health_check_supported": False,
    }

    try:
        # Import the gRPC service definition
        try:
            from june_grpc_api.generated import llm_pb2, llm_pb2_grpc
        except ImportError:
            return (
                False,
                "june_grpc_api not available (cannot test protocol compatibility)",
                details,
            )

        # Try to create a channel and call HealthCheck RPC
        channel = grpc.insecure_channel(grpc_address)

        try:
            # Wait for channel to be ready
            grpc.channel_ready_future(channel).result(timeout=5)

            # Try to call HealthCheck RPC
            stub = llm_pb2_grpc.LLMInferenceStub(channel)
            request = llm_pb2.HealthRequest()

            # Call with short timeout
            response = stub.HealthCheck(request, timeout=5)

            details["health_check_supported"] = True
            details["protocol_compatible"] = True
            details["model_name"] = (
                response.model_name if hasattr(response, "model_name") else None
            )
            details["max_context_length"] = (
                response.max_context_length
                if hasattr(response, "max_context_length")
                else None
            )
            details["healthy"] = (
                response.healthy if hasattr(response, "healthy") else None
            )

            channel.close()
            return (
                True,
                f"gRPC protocol compatible - HealthCheck RPC successful",
                details,
            )
        except grpc.RpcError as e:
            channel.close()
            details["rpc_error"] = str(e)
            details["rpc_error_code"] = e.code().name if hasattr(e, "code") else None
            return False, f"gRPC protocol compatibility check failed: {e}", details
        except grpc.FutureTimeoutError:
            channel.close()
            return False, f"gRPC HealthCheck RPC timeout at {grpc_address}", details
        except Exception as e:
            channel.close()
            return False, f"Error checking gRPC protocol compatibility: {e}", details

    except Exception as e:
        return False, f"Failed to check gRPC protocol compatibility: {e}", details


def check_gpu_availability() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if GPU is available (for NIM services that require GPU).

    Returns:
        Tuple of (success, message, details_dict)
    """
    import subprocess

    details = {"gpu_available": False, "gpu_count": 0, "gpu_info": []}

    try:
        # Try to run nvidia-smi
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
            gpu_lines = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            details["gpu_count"] = len(gpu_lines)
            details["gpu_info"] = gpu_lines
            details["gpu_available"] = len(gpu_lines) > 0

            if details["gpu_available"]:
                return (
                    True,
                    f"GPU available ({details['gpu_count']} GPU(s) detected)",
                    details,
                )
            else:
                return False, "No GPUs detected", details
        else:
            return False, f"nvidia-smi failed: {result.stderr}", details

    except FileNotFoundError:
        return False, "nvidia-smi not found (GPU may not be available)", details
    except subprocess.TimeoutExpired:
        return False, "nvidia-smi timeout", details
    except Exception as e:
        return False, f"Error checking GPU availability: {e}", details


class VerifyNIMCommand(Command):
    """
    Command to verify NVIDIA NIM setup and connectivity.

    Performs comprehensive checks to ensure NIM service is properly configured
    and accessible. This helps determine when it's safe to use NIM as a replacement
    for TensorRT-LLM or legacy inference-api service.
    """

    @classmethod
    def get_name(cls) -> str:
        return "verify-nim"

    @classmethod
    def get_description(cls) -> str:
        return "Verify NVIDIA NIM setup and connectivity"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--nim-host",
            type=str,
            default=os.getenv("NIM_HOST", "nim-qwen3"),
            help="NIM service hostname (default: nim-qwen3)",
        )
        parser.add_argument(
            "--http-port",
            type=int,
            default=int(os.getenv("NIM_HTTP_PORT", "8003")),
            help="NIM HTTP port (default: 8003)",
        )
        parser.add_argument(
            "--grpc-port",
            type=int,
            default=int(os.getenv("NIM_GRPC_PORT", "8001")),
            help="NIM gRPC port (default: 8001)",
        )
        parser.add_argument(
            "--check-protocol",
            action="store_true",
            help="Check gRPC protocol compatibility (requires june_grpc_api)",
        )
        parser.add_argument(
            "--json", action="store_true", help="Output results as JSON"
        )

    def init(self) -> None:
        self.results = {
            "http_health": {},
            "grpc_connectivity": {},
            "grpc_protocol": {},
            "gpu_availability": {},
            "overall_status": "unknown",
            "ready": False,
        }

    def run(self) -> None:
        """Run all verification checks."""
        checks_passed = 0
        total_checks = 3  # HTTP, gRPC, GPU (protocol check is optional)

        # Check 1: HTTP health endpoint
        http_url = f"http://{self.args.nim_host}:{self.args.http_port}"
        print(f"Checking NIM HTTP health endpoint ({http_url})...")
        success, message, details = check_http_health(http_url)
        self.results["http_health"] = {
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
        grpc_address = f"{self.args.nim_host}:{self.args.grpc_port}"
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

        # Check 3: gRPC protocol compatibility (optional)
        if self.args.check_protocol:
            print(f"\nChecking gRPC protocol compatibility ({grpc_address})...")
            success, message, details = check_grpc_protocol_compatibility(grpc_address)
            self.results["grpc_protocol"] = {
                "success": success,
                "message": message,
                **details,
            }
            if success:
                print(f"  ✓ {message}")
                if "model_name" in details and details["model_name"]:
                    print(f"    Model: {details['model_name']}")
                if "max_context_length" in details and details["max_context_length"]:
                    print(f"    Max context length: {details['max_context_length']}")
            else:
                print(f"  ✗ {message}")
        else:
            self.results["grpc_protocol"] = {
                "success": None,
                "message": "Skipped (use --check-protocol to enable)",
                "skipped": True,
            }

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

        # NIM is ready if HTTP and gRPC connectivity pass
        # GPU is important but not critical (NIM may work without GPU in some configurations)
        critical_checks_passed = (
            self.results["http_health"]["success"]
            and self.results["grpc_connectivity"]["success"]
        )

        self.results["ready"] = critical_checks_passed
        self.results["overall_status"] = (
            "ready" if critical_checks_passed else "not_ready"
        )

        # Print summary
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)
        print(f"Checks passed: {checks_passed}/{total_checks}")
        print(f"Overall status: {self.results['overall_status'].upper()}")
        print(f"NIM ready: {'YES' if self.results['ready'] else 'NO'}")

        if self.results["ready"]:
            print("\n✓ NIM service is ready and accessible.")
            if self.args.check_protocol and self.results["grpc_protocol"]["success"]:
                print("  ✓ gRPC protocol is compatible with june services.")
                print("  Safe to update june services to use NIM endpoint.")
            else:
                print(
                    "  ⚠ gRPC protocol compatibility not verified (use --check-protocol)."
                )
        else:
            print("\n✗ NIM service is not ready yet.")
            print("  Do not update june services until all checks pass.")
            print("\nIssues to resolve:")
            if not self.results["http_health"]["success"]:
                print(f"  - HTTP health: {self.results['http_health']['message']}")
            if not self.results["grpc_connectivity"]["success"]:
                print(
                    f"  - gRPC connectivity: {self.results['grpc_connectivity']['message']}"
                )
            if not self.results["gpu_availability"]["success"]:
                print(
                    f"  - GPU availability: {self.results['gpu_availability']['message']}"
                )

        # Output JSON if requested
        if self.args.json:
            print("\n" + json.dumps(self.results, indent=2))

        # Exit with appropriate code
        sys.exit(0 if self.results["ready"] else 1)

    def cleanup(self) -> None:
        pass
