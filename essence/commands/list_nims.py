"""
Command to list available NVIDIA NIM containers for DGX Spark.

This command queries NGC catalog and NIM services to discover available models,
their sizes, and compatibility information.
"""
import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

import httpx

from essence.command import Command

logger = logging.getLogger(__name__)


class ListNIMsCommand(Command):
    """List available NVIDIA NIM containers for DGX Spark."""

    @classmethod
    def get_name(cls) -> str:
        return "list-nims"

    @classmethod
    def get_description(cls) -> str:
        return "List available NVIDIA NIM containers for DGX Spark with model sizes and compatibility"

    @classmethod
    def add_args(cls, parser: Any) -> None:
        parser.add_argument(
            "--format",
            choices=["json", "table", "markdown"],
            default="table",
            help="Output format (default: table)",
        )
        parser.add_argument(
            "--filter",
            choices=["llm", "stt", "tts", "all"],
            default="all",
            help="Filter by model type (default: all)",
        )
        parser.add_argument(
            "--dgx-spark-only",
            action="store_true",
            help="Only show DGX Spark compatible models",
        )
        parser.add_argument(
            "--include-sizes",
            action="store_true",
            help="Include model size information (requires Docker image inspection)",
        )
        parser.add_argument(
            "--ngc-api-key",
            help="NGC API key (default: from NGC_API_KEY env var)",
        )

    def init(self) -> None:
        """Initialize command."""
        self.ngc_api_key = self.args.ngc_api_key or os.getenv("NGC_API_KEY")
        if not self.ngc_api_key:
            logger.warning(
                "NGC_API_KEY not set. Some features may be limited. "
                "Set NGC_API_KEY environment variable or use --ngc-api-key"
            )

    def run(self) -> None:
        """List available NIMs."""
        nims = []

        # Try to get list from NGC catalog API
        try:
            nims.extend(self._query_ngc_catalog())
        except Exception as e:
            logger.warning(f"Failed to query NGC catalog: {e}")

        # Try to get list from list-model-profiles command
        try:
            nims.extend(self._query_list_model_profiles())
        except Exception as e:
            logger.warning(f"Failed to query list-model-profiles: {e}")

        # Try to query running NIM services
        try:
            nims.extend(self._query_nim_services())
        except Exception as e:
            logger.warning(f"Failed to query NIM services: {e}")

        # Filter results
        nims = self._filter_nims(nims)

        # Output results
        self._output_results(nims)

    def _query_ngc_catalog(self) -> List[Dict[str, Any]]:
        """Query NGC catalog API for NIM containers."""
        nims = []

        # Known DGX Spark NIMs from release notes (NIM 1.14.0)
        known_dgx_spark_nims = [
            {
                "name": "Qwen3-32B",
                "image": "nvcr.io/nim/qwen/qwen3-32b-dgx-spark:1.0.0",
                "type": "llm",
                "dgx_spark": True,
                "size": None,  # Will be filled if --include-sizes
                "description": "Qwen3-32B NIM for DGX Spark (ARM64 compatible)",
                "catalog_url": "https://catalog.ngc.nvidia.com/orgs/nim/teams/qwen/containers/qwen3-32b-dgx-spark",
            },
            {
                "name": "Llama-3.1-8B-Instruct",
                "image": "nvcr.io/nim/llama/llama-3.1-8b-instruct-dgx-spark:latest",
                "type": "llm",
                "dgx_spark": True,
                "size": None,
                "description": "Llama-3.1-8B-Instruct NIM for DGX Spark (ARM64 compatible)",
                "catalog_url": "https://catalog.ngc.nvidia.com/orgs/nim/teams/llama/containers/llama-3.1-8b-instruct-dgx-spark",
            },
            {
                "name": "Nemotron-Nano-9B-v2",
                "image": "nvcr.io/nim/nemotron/nemotron-nano-9b-v2-dgx-spark:latest",
                "type": "llm",
                "dgx_spark": True,
                "size": None,
                "description": "NVIDIA Nemotron Nano 9B v2 NIM for DGX Spark (ARM64 compatible)",
                "catalog_url": "https://catalog.ngc.nvidia.com/orgs/nim/teams/nemotron/containers/nemotron-nano-9b-v2-dgx-spark",
            },
        ]

        # Try to query Docker registry for nvcr.io/nim images
        if self.ngc_api_key:
            try:
                # Try to query Docker registry API for available tags
                # Note: Docker registry API requires authentication
                nims.extend(self._query_docker_registry())
            except Exception as e:
                logger.debug(f"Docker registry query failed: {e}")

        # Add known NIMs
        nims.extend(known_dgx_spark_nims)

        return nims

    def _query_docker_registry(self) -> List[Dict[str, Any]]:
        """Query Docker registry (nvcr.io) for available NIM images."""
        nims = []

        if not self.ngc_api_key:
            return nims

        # Docker registry API endpoints for nvcr.io
        # Note: This is a simplified approach - actual registry API may differ
        registry_base = "https://nvcr.io/v2"
        nim_orgs = ["nim/qwen", "nim/llama", "nim/nemotron", "nim/riva"]

        for org in nim_orgs:
            try:
                # Try to get catalog of repositories
                # Docker registry v2 API: GET /v2/_catalog
                # For specific org: GET /v2/{org}/_catalog
                headers = {
                    "Authorization": f"Bearer {self.ngc_api_key}",
                    "Accept": "application/json",
                }

                # Try to get repository list
                url = f"{registry_base}/{org}/_catalog"
                response = httpx.get(url, headers=headers, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    if "repositories" in data:
                        for repo in data["repositories"]:
                            # Check if it's a DGX Spark variant
                            if "dgx-spark" in repo.lower():
                                nims.append(
                                    {
                                        "name": repo.split("/")[-1],
                                        "image": f"nvcr.io/{org}/{repo}:latest",
                                        "type": self._infer_model_type(repo),
                                        "dgx_spark": True,
                                        "size": None,
                                        "description": f"Discovered from Docker registry: {repo}",
                                    }
                                )
            except Exception as e:
                logger.debug(f"Could not query registry for {org}: {e}")

        return nims

    def _query_list_model_profiles(self) -> List[Dict[str, Any]]:
        """Query list-model-profiles command."""
        nims = []

        if not self.ngc_api_key:
            return nims

        try:
            # Try to run list-model-profiles command
            env = os.environ.copy()
            env["NGC_API_KEY"] = self.ngc_api_key

            result = subprocess.run(
                ["list-model-profiles", "-e", f"NGC_API_KEY={self.ngc_api_key}"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )

            if result.returncode == 0:
                # Parse output (format may vary)
                logger.info("list-model-profiles command executed successfully")
                # TODO: Parse output to extract model information
            else:
                logger.debug(
                    f"list-model-profiles command failed: {result.stderr}"
                )
        except FileNotFoundError:
            logger.debug("list-model-profiles command not found")
        except Exception as e:
            logger.debug(f"Error running list-model-profiles: {e}")

        return nims

    def _query_nim_services(self) -> List[Dict[str, Any]]:
        """Query running NIM services for available models."""
        nims = []

        # Check for running NIM services
        nim_services = [
            ("nim-qwen3", "8003", "8001"),
            ("nim-stt", "8004", "8002"),
            ("nim-tts", "8006", "8005"),
        ]

        for service_name, http_port, grpc_port in nim_services:
            try:
                # Try to query /v1/models endpoint
                response = httpx.get(
                    f"http://{service_name}:{http_port}/v1/models",
                    timeout=5,
                )
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data:
                        for model in data["data"]:
                            nims.append(
                                {
                                    "name": model.get("id", service_name),
                                    "image": f"{service_name}:latest",
                                    "type": self._infer_model_type(service_name),
                                    "dgx_spark": True,  # Assume if running, it's compatible
                                    "size": None,
                                    "description": f"Running NIM service: {service_name}",
                                    "status": "running",
                                }
                            )
            except Exception as e:
                logger.debug(f"Could not query {service_name}: {e}")

        return nims

    def _infer_model_type(self, service_name: str) -> str:
        """Infer model type from service name."""
        if "qwen" in service_name or "llama" in service_name or "nemotron" in service_name:
            return "llm"
        elif "stt" in service_name or "asr" in service_name:
            return "stt"
        elif "tts" in service_name:
            return "tts"
        return "unknown"

    def _filter_nims(self, nims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter NIMs based on arguments."""
        filtered = []

        for nim in nims:
            # Filter by type
            if self.args.filter != "all" and nim.get("type") != self.args.filter:
                continue

            # Filter by DGX Spark compatibility
            if self.args.dgx_spark_only and not nim.get("dgx_spark", False):
                continue

            # Get image size if requested
            if self.args.include_sizes:
                nim["size"] = self._get_image_size(nim.get("image"))

            filtered.append(nim)

        return filtered

    def _get_image_size(self, image: Optional[str]) -> Optional[str]:
        """Get Docker image size."""
        if not image:
            return None

        try:
            # First check if image exists locally
            result = subprocess.run(
                ["docker", "image", "inspect", image, "--format", "{{.Size}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                size_bytes = int(result.stdout.strip())
                # Convert to human-readable format
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if size_bytes < 1024.0:
                        return f"{size_bytes:.2f} {unit}"
                    size_bytes /= 1024.0
                return f"{size_bytes:.2f} PB"
            else:
                # Image not pulled - try to get size from registry manifest
                return self._get_image_size_from_registry(image)
        except Exception as e:
            logger.debug(f"Could not get image size for {image}: {e}")

        return None

    def _get_image_size_from_registry(self, image: str) -> Optional[str]:
        """Get image size from Docker registry manifest."""
        if not self.ngc_api_key:
            return "Not pulled"

        try:
            # Parse image name
            if ":" in image:
                repo, tag = image.rsplit(":", 1)
            else:
                repo, tag = image, "latest"

            # Remove nvcr.io prefix if present
            if repo.startswith("nvcr.io/"):
                repo = repo[8:]

            # Docker registry v2 API: GET /v2/{name}/manifests/{reference}
            registry_base = "https://nvcr.io/v2"
            url = f"{registry_base}/{repo}/manifests/{tag}"

            headers = {
                "Authorization": f"Bearer {self.ngc_api_key}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            }

            response = httpx.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                manifest = response.json()
                if "config" in manifest and "size" in manifest["config"]:
                    size_bytes = manifest["config"]["size"]
                    # Also sum layer sizes if available
                    if "layers" in manifest:
                        total_size = sum(layer.get("size", 0) for layer in manifest["layers"])
                        if total_size > 0:
                            size_bytes = total_size

                    # Convert to human-readable format
                    for unit in ["B", "KB", "MB", "GB", "TB"]:
                        if size_bytes < 1024.0:
                            return f"{size_bytes:.2f} {unit}"
                        size_bytes /= 1024.0
                    return f"{size_bytes:.2f} PB"
        except Exception as e:
            logger.debug(f"Could not get image size from registry for {image}: {e}")

        return "Not pulled"

    def _output_results(self, nims: List[Dict[str, Any]]) -> None:
        """Output results in requested format."""
        if self.args.format == "json":
            print(json.dumps(nims, indent=2))
        elif self.args.format == "markdown":
            self._output_markdown(nims)
        else:  # table
            self._output_table(nims)

    def _output_table(self, nims: List[Dict[str, Any]]) -> None:
        """Output results as a table."""
        if not nims:
            print("No NIMs found matching criteria.")
            return

        # Print header
        print(f"\n{'Name':<35} {'Type':<8} {'DGX Spark':<12} {'Size':<15} {'Status':<10} {'Description':<40}")
        print("-" * 130)

        # Print rows
        for nim in nims:
            name = nim.get("name", "Unknown")[:33]
            model_type = nim.get("type", "unknown")
            dgx_spark = "✅ Yes" if nim.get("dgx_spark") else "❌ No"
            size = nim.get("size", "Unknown") or "Unknown"
            status = nim.get("status", "available")
            description = nim.get("description", "")[:38]

            print(f"{name:<35} {model_type:<8} {dgx_spark:<12} {size:<15} {status:<10} {description:<40}")

        print(f"\nTotal: {len(nims)} NIM(s) found")
        print("\nNote: Use --include-sizes to get Docker image sizes (requires images to be pulled)")
        print("Note: Use --dgx-spark-only to filter for ARM64-compatible models only")

    def _output_markdown(self, nims: List[Dict[str, Any]]) -> None:
        """Output results as markdown."""
        if not nims:
            print("No NIMs found matching criteria.")
            return

        print("# Available NIMs for DGX Spark\n")
        print("| Name | Type | DGX Spark | Size | Status | Description | Catalog |")
        print("|------|------|-----------|------|--------|-------------|---------|")

        for nim in nims:
            name = nim.get("name", "Unknown")
            model_type = nim.get("type", "unknown")
            dgx_spark = "✅" if nim.get("dgx_spark") else "❌"
            size = nim.get("size", "Unknown") or "Unknown"
            status = nim.get("status", "available")
            description = nim.get("description", "")
            catalog_url = nim.get("catalog_url", "")
            catalog_link = f"[View]({catalog_url})" if catalog_url else ""

            print(f"| {name} | {model_type} | {dgx_spark} | {size} | {status} | {description} | {catalog_link} |")

        print(f"\n**Total:** {len(nims)} NIM(s) found")
        print("\n> Use `--include-sizes` to get Docker image sizes (requires images to be pulled)")
        print("> Use `--dgx-spark-only` to filter for ARM64-compatible models only")

    def cleanup(self) -> None:
        """Cleanup resources."""
        pass

