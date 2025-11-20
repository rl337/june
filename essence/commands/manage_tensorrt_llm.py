"""
TensorRT-LLM model management command - Load/unload models in Triton Inference Server.

Usage:
    poetry run -m essence manage-tensorrt-llm --action load --model qwen3-30b
    poetry run -m essence manage-tensorrt-llm --action unload --model qwen3-30b
    poetry run -m essence manage-tensorrt-llm --action list
    poetry run -m essence manage-tensorrt-llm --action status --model qwen3-30b

This command provides an interface for managing models in the TensorRT-LLM container
(Triton Inference Server). It interacts with Triton's model repository API to:
- Load models into memory
- Unload models from memory
- List available/loaded models
- Check model status

Models must be compiled/prepared and placed in Triton's model repository before
they can be loaded. This command handles the loading/unloading operations only.

For Phase 15 Task 2: Model loading/unloading API implementation.
"""
import argparse
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

try:
    import httpx

    HTTP_CLIENT_AVAILABLE = True
except ImportError:
    HTTP_CLIENT_AVAILABLE = False
    IMPORT_ERROR = None

from essence.command import Command

logger = logging.getLogger(__name__)


def _format_connection_error(base_url: str, error: Exception) -> str:
    """
    Format connection error message with helpful guidance for DNS resolution failures.

    Args:
        base_url: The URL that failed to connect
        error: The connection error exception

    Returns:
        Formatted error message with guidance
    """
    error_str = str(error)
    if (
        "name resolution" in error_str.lower()
        or "temporary failure" in error_str.lower()
    ):
        return (
            f"Cannot connect to TensorRT-LLM at {base_url}: {error}\n"
            f"  Note: If running from host, 'tensorrt-llm' hostname is only resolvable within Docker networks.\n"
            f"  Options: 1) Run from a container on shared-network, 2) Use --tensorrt-llm-url with IP/hostname, 3) Check if service is running"
        )
    else:
        return f"Cannot connect to TensorRT-LLM at {base_url}: {error}"


class TensorRTLLMManager:
    """
    Client for managing TensorRT-LLM models via Triton Inference Server API.

    Interacts with Triton's model repository API to load/unload models dynamically.
    Models must be compiled and placed in the model repository before loading.
    """

    def __init__(self, base_url: str = "http://tensorrt-llm:8002", timeout: int = 300):
        """
        Initialize TensorRT-LLM manager.

        Args:
            base_url: Base URL for Triton Inference Server HTTP API
            timeout: Request timeout in seconds (default: 300 for model loading)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # httpx.Client accepts timeout as a number (seconds) or httpx.Timeout object
        self.client = (
            httpx.Client(timeout=self.timeout) if HTTP_CLIENT_AVAILABLE else None
        )

    def load_model(self, model_name: str) -> Tuple[bool, str]:
        """
        Load a model into Triton Inference Server.

        Args:
            model_name: Name of the model to load (must exist in model repository)

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not HTTP_CLIENT_AVAILABLE:
            return False, "httpx not available - cannot make HTTP requests"

        url = urljoin(self.base_url, f"/v2/repository/models/{model_name}/load")
        try:
            logger.info(f"Loading model '{model_name}' into TensorRT-LLM...")
            response = self.client.post(url)

            if response.status_code == 200:
                logger.info(f"Model '{model_name}' loaded successfully")
                return True, f"Model '{model_name}' loaded successfully"
            else:
                error_msg = f"Failed to load model '{model_name}': {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg

        except httpx.TimeoutException:
            error_msg = (
                f"Timeout loading model '{model_name}' (exceeded {self.timeout}s)"
            )
            logger.error(error_msg)
            return False, error_msg
        except httpx.ConnectError as e:
            error_msg = _format_connection_error(self.base_url, e)
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error loading model '{model_name}': {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def unload_model(self, model_name: str) -> Tuple[bool, str]:
        """
        Unload a model from Triton Inference Server.

        Args:
            model_name: Name of the model to unload

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not HTTP_CLIENT_AVAILABLE:
            return False, "httpx not available - cannot make HTTP requests"

        url = urljoin(self.base_url, f"/v2/repository/models/{model_name}/unload")
        try:
            logger.info(f"Unloading model '{model_name}' from TensorRT-LLM...")
            response = self.client.post(url)

            if response.status_code == 200:
                logger.info(f"Model '{model_name}' unloaded successfully")
                return True, f"Model '{model_name}' unloaded successfully"
            else:
                error_msg = f"Failed to unload model '{model_name}': {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg

        except httpx.TimeoutException:
            error_msg = (
                f"Timeout unloading model '{model_name}' (exceeded {self.timeout}s)"
            )
            logger.error(error_msg)
            return False, error_msg
        except httpx.ConnectError as e:
            error_msg = _format_connection_error(self.base_url, e)
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error unloading model '{model_name}': {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def list_models(self) -> Tuple[bool, List[Dict[str, any]], str]:
        """
        List all models in the repository (available and loaded).

        Returns:
            Tuple of (success: bool, models: List[Dict], message: str)
            Each model dict contains: name, version, state (READY, LOADING, UNAVAILABLE)
        """
        if not HTTP_CLIENT_AVAILABLE:
            return False, [], "httpx not available - cannot make HTTP requests"

        url = urljoin(self.base_url, "/v2/repository/index")
        try:
            logger.info("Listing models in TensorRT-LLM repository...")
            response = self.client.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                logger.info(f"Found {len(models)} model(s) in repository")
                return True, models, f"Found {len(models)} model(s)"
            else:
                error_msg = (
                    f"Failed to list models: {response.status_code} - {response.text}"
                )
                logger.error(error_msg)
                return False, [], error_msg

        except httpx.ConnectError as e:
            error_msg = _format_connection_error(self.base_url, e)
            logger.error(error_msg)
            return False, [], error_msg
        except Exception as e:
            error_msg = f"Error listing models: {e}"
            logger.error(error_msg, exc_info=True)
            return False, [], error_msg

    def get_model_status(self, model_name: str) -> Tuple[bool, Optional[str], str]:
        """
        Get the status of a specific model.

        Args:
            model_name: Name of the model to check

        Returns:
            Tuple of (success: bool, status: Optional[str], message: str)
            Status can be: READY, LOADING, UNAVAILABLE, or None if model not found
        """
        if not HTTP_CLIENT_AVAILABLE:
            return False, None, "httpx not available - cannot make HTTP requests"

        # Check if model is ready
        ready_url = urljoin(self.base_url, f"/v2/models/{model_name}/ready")
        try:
            response = self.client.get(ready_url, timeout=10)

            if response.status_code == 200:
                return True, "READY", f"Model '{model_name}' is ready"
            elif response.status_code == 404:
                # Model might exist but not be loaded - check repository
                success, models, msg = self.list_models()
                if success:
                    model_names = [m.get("name") for m in models]
                    if model_name in model_names:
                        return (
                            True,
                            "UNAVAILABLE",
                            f"Model '{model_name}' exists but is not loaded",
                        )
                    else:
                        return (
                            False,
                            None,
                            f"Model '{model_name}' not found in repository",
                        )
                else:
                    return False, None, f"Cannot check model status: {msg}"
            else:
                return (
                    False,
                    None,
                    f"Failed to check model status: {response.status_code} - {response.text}",
                )

        except httpx.ConnectError as e:
            error_msg = _format_connection_error(self.base_url, e)
            logger.error(error_msg)
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Error checking model status: {e}"
            logger.error(error_msg, exc_info=True)
            return False, None, error_msg


class ManageTensorRTLLMCommand(Command):
    """
    Command for managing TensorRT-LLM models via Triton Inference Server.

    Provides interface for loading/unloading models dynamically, listing available
    models, and checking model status. Models must be compiled and placed in
    Triton's model repository before they can be loaded.

    This implements Phase 15 Task 2: Model loading/unloading API.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "manage-tensorrt-llm"
        """
        return "manage-tensorrt-llm"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Manage TensorRT-LLM models (load/unload/list/status)"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures action (load/unload/list/status), model name, and TensorRT-LLM URL.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--action",
            "-a",
            choices=["load", "unload", "list", "status"],
            required=True,
            help="Action to perform: load, unload, list, or status",
        )
        parser.add_argument(
            "--model",
            "-m",
            type=str,
            help="Model name (required for load/unload/status actions)",
        )
        parser.add_argument(
            "--tensorrt-llm-url",
            type=str,
            default=os.getenv("TENSORRT_LLM_URL", "http://tensorrt-llm:8002"),
            help="TensorRT-LLM HTTP API URL (default: http://tensorrt-llm:8002)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=300,
            help="Request timeout in seconds (default: 300 for model loading)",
        )

    def init(self) -> None:
        """
        Initialize the command.

        Validates arguments and initializes TensorRT-LLM manager client.
        """
        # Validate arguments
        if self.args.action in ["load", "unload", "status"] and not self.args.model:
            logger.error(f"Model name is required for action '{self.args.action}'")
            sys.exit(1)

        # Initialize manager
        self.manager = TensorRTLLMManager(
            base_url=self.args.tensorrt_llm_url, timeout=self.args.timeout
        )
        logger.info(
            f"Initialized TensorRT-LLM manager (URL: {self.args.tensorrt_llm_url})"
        )

    def run(self) -> None:
        """
        Execute the requested action.

        Performs load/unload/list/status operation based on command arguments.
        """
        action = self.args.action

        if action == "load":
            success, message = self.manager.load_model(self.args.model)
            if success:
                print(f"✅ {message}")
                print(f"\n💡 Tip: Check model status with:")
                print(
                    f"   poetry run -m essence manage-tensorrt-llm --action status --model {self.args.model}"
                )
                sys.exit(0)
            else:
                print(f"❌ {message}")
                print(f"\n💡 Troubleshooting tips:")
                print(f"   1. Verify model is ready for loading:")
                print(
                    f"      poetry run -m essence compile-model --model {self.args.model} --check-readiness"
                )
                print(f"   2. Check if TensorRT-LLM service is running:")
                print(f"      poetry run -m essence verify-tensorrt-llm")
                print(f"   3. Verify model files are in repository:")
                print(
                    f"      poetry run -m essence setup-triton-repository --action validate --model {self.args.model}"
                )
                sys.exit(1)

        elif action == "unload":
            success, message = self.manager.unload_model(self.args.model)
            if success:
                print(f"✅ {message}")
                sys.exit(0)
            else:
                print(f"❌ {message}")
                sys.exit(1)

        elif action == "list":
            success, models, message = self.manager.list_models()
            if success:
                print(f"\n📋 {message}\n")
                if models:
                    print("Models in repository:")
                    for model in models:
                        name = model.get("name", "unknown")
                        versions = model.get("versions", [])
                        state = model.get("state", "UNKNOWN")
                        state_icon = (
                            "✅"
                            if state == "READY"
                            else "⏳"
                            if state == "LOADING"
                            else "❌"
                        )
                        print(
                            f"  {state_icon} {name} (versions: {versions}, state: {state})"
                        )
                    print(f"\n💡 Tip: Load a model with:")
                    print(
                        f"   poetry run -m essence manage-tensorrt-llm --action load --model <model_name>"
                    )
                else:
                    print("  (no models found)")
                    print(f"\n💡 Tip: Add models to the repository first:")
                    print(
                        f"   1. Create repository structure: poetry run -m essence setup-triton-repository --action create --model <name>"
                    )
                    print(
                        f"   2. Compile model: poetry run -m essence compile-model --model <name> --generate-template"
                    )
                    print(
                        f"   3. Check readiness: poetry run -m essence compile-model --model <name> --check-readiness"
                    )
                sys.exit(0)
            else:
                print(f"❌ {message}")
                print(f"\n💡 Tip: Check if TensorRT-LLM service is running:")
                print(f"   poetry run -m essence verify-tensorrt-llm")
                sys.exit(1)

        elif action == "status":
            success, status, message = self.manager.get_model_status(self.args.model)
            if success:
                if status == "READY":
                    print(f"✅ {message}")
                    print(f"\n💡 Model is ready for inference!")
                    print(f"   Use gRPC endpoint: tensorrt-llm:8000")
                elif status == "UNAVAILABLE":
                    print(f"⚠️  {message}")
                    print(f"\n💡 Model is not loaded. Load it with:")
                    print(
                        f"   poetry run -m essence manage-tensorrt-llm --action load --model {self.args.model}"
                    )
                else:
                    print(f"❌ {message}")
                    print(f"\n💡 Troubleshooting:")
                    print(
                        f"   1. Check if model files are ready: poetry run -m essence compile-model --model {self.args.model} --check-readiness"
                    )
                    print(
                        f"   2. Verify repository structure: poetry run -m essence setup-triton-repository --action validate --model {self.args.model}"
                    )
                sys.exit(0)
            else:
                print(f"❌ {message}")
                print(f"\n💡 Troubleshooting:")
                print(
                    f"   1. Check if TensorRT-LLM service is accessible: poetry run -m essence verify-tensorrt-llm"
                )
                print(
                    f"   2. Verify model exists in repository: poetry run -m essence manage-tensorrt-llm --action list"
                )
                sys.exit(1)

    def cleanup(self) -> None:
        """
        Clean up resources.

        Closes HTTP client.
        """
        if hasattr(self, "manager") and hasattr(self.manager, "client"):
            self.manager.client.close()
            logger.debug("Closed TensorRT-LLM manager HTTP client")
