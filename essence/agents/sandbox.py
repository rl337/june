"""
Sandbox Management for Benchmark Evaluation

Provides isolated Docker container-based sandboxes for running benchmark tasks.
Each task runs in a fresh container with full activity logging and reviewability.
"""
import logging
import json
import subprocess
import time
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime
import docker
from docker.errors import DockerException

from essence.agents.coding_agent import CodingAgent

logger = logging.getLogger(__name__)


@dataclass
class SandboxMetrics:
    """Metrics collected from sandbox execution."""
    task_id: str
    start_time: float
    end_time: Optional[float] = None
    commands_executed: int = 0
    files_created: int = 0
    files_modified: int = 0
    total_cpu_time: float = 0.0
    peak_memory_mb: float = 0.0
    disk_io_bytes: int = 0
    network_requests: int = 0
    iterations: int = 0
    success: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @property
    def duration_seconds(self) -> float:
        """Get execution duration in seconds."""
        if self.end_time is None:
            return 0.0
        return self.end_time - self.start_time


@dataclass
class CommandLog:
    """Log entry for a command execution."""
    timestamp: float
    command: str
    working_directory: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class Sandbox:
    """
    Isolated Docker container sandbox for running benchmark tasks.
    
    Each sandbox:
    - Runs in a fresh Docker container
    - Has its own workspace volume
    - Logs all commands and file operations
    - Captures filesystem snapshots before/after
    - Enforces resource limits
    - Persists state for review after completion
    """
    
    def __init__(
        self,
        task_id: str,
        base_image: str = "python:3.11-slim",
        workspace_dir: Optional[Path] = None,
        max_memory: str = "2g",
        max_cpu: str = "1.0",
        network_disabled: bool = True,
    ):
        """
        Initialize sandbox.
        
        Args:
            task_id: Unique identifier for this task
            base_image: Docker base image to use
            workspace_dir: Host directory for workspace (defaults to /tmp/sandboxes/{task_id})
            max_memory: Maximum memory limit (e.g., "2g")
            max_cpu: Maximum CPU limit (e.g., "1.0")
            network_disabled: Whether to disable network access
        """
        self.task_id = task_id
        self.base_image = base_image
        self.max_memory = max_memory
        self.max_cpu = max_cpu
        self.network_disabled = network_disabled
        
        # Setup workspace directory
        if workspace_dir is None:
            workspace_dir = Path(f"/tmp/sandboxes/{task_id}")
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Docker client
        try:
            self.docker_client = docker.from_env()
        except DockerException as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise RuntimeError("Docker is not available") from e
        
        # Metrics and logs
        self.metrics = SandboxMetrics(
            task_id=task_id,
            start_time=time.time(),
        )
        self.command_logs: List[CommandLog] = []
        self.container: Optional[docker.models.containers.Container] = None
        self.container_name = f"june-sandbox-{task_id}"
        
        # Coding agent (will be initialized in container)
        self.coding_agent: Optional[CodingAgent] = None
        
        logger.info(f"Initialized sandbox {task_id} with workspace: {self.workspace_dir}")
    
    def create_container(self) -> None:
        """Create Docker container for this sandbox."""
        if self.container is not None:
            logger.warning(f"Container {self.container_name} already exists")
            return
        
        try:
            # Remove existing container if it exists
            try:
                old_container = self.docker_client.containers.get(self.container_name)
                old_container.remove(force=True)
            except docker.errors.NotFound:
                pass
            
            # Create container
            self.container = self.docker_client.containers.create(
                image=self.base_image,
                name=self.container_name,
                volumes={
                    str(self.workspace_dir): {
                        "bind": "/workspace",
                        "mode": "rw"
                    }
                },
                working_dir="/workspace",
                mem_limit=self.max_memory,
                cpu_quota=int(float(self.max_cpu) * 100000),  # Convert to microseconds
                cpu_period=100000,
                network_disabled=self.network_disabled,
                detach=True,
                tty=True,
                stdin_open=True,
                command="tail -f /dev/null",  # Keep container running
            )
            
            logger.info(f"Created container {self.container_name}")
        except DockerException as e:
            logger.error(f"Failed to create container: {e}")
            raise RuntimeError(f"Failed to create sandbox container: {e}") from e
    
    def start(self) -> None:
        """Start the sandbox container."""
        if self.container is None:
            self.create_container()
        
        if self.container.status != "running":
            self.container.start()
            logger.info(f"Started container {self.container_name}")
    
    def stop(self) -> None:
        """Stop the sandbox container."""
        if self.container is None:
            return
        
        if self.container.status == "running":
            self.container.stop(timeout=10)
            logger.info(f"Stopped container {self.container_name}")
        
        self.metrics.end_time = time.time()
    
    def remove(self) -> None:
        """Remove the sandbox container."""
        if self.container is None:
            return
        
        try:
            if self.container.status == "running":
                self.container.stop(timeout=10)
            self.container.remove(force=True)
            logger.info(f"Removed container {self.container_name}")
        except DockerException as e:
            logger.warning(f"Failed to remove container: {e}")
        finally:
            self.container = None
    
    def execute_command(
        self,
        command: str,
        working_directory: str = "/workspace",
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Execute a command in the sandbox container.
        
        Args:
            command: Command to execute
            working_directory: Working directory in container
            timeout: Command timeout in seconds
            
        Returns:
            Dictionary with stdout, stderr, returncode, duration
        """
        if self.container is None:
            raise RuntimeError("Container not created. Call start() first.")
        
        if self.container.status != "running":
            self.start()
        
        start_time = time.time()
        
        try:
            # Execute command in container
            exec_result = self.container.exec_run(
                command,
                workdir=working_directory,
                stdout=True,
                stderr=True,
                demux=True,  # Separate stdout and stderr
            )
            
            duration = time.time() - start_time
            
            # Parse result
            if exec_result.output is not None:
                if isinstance(exec_result.output, tuple):
                    stdout_bytes, stderr_bytes = exec_result.output
                    stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                    stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
                else:
                    stdout = exec_result.output.decode("utf-8", errors="replace")
                    stderr = ""
            else:
                stdout = ""
                stderr = ""
            
            returncode = exec_result.exit_code
            
            # Log command
            command_log = CommandLog(
                timestamp=start_time,
                command=command,
                working_directory=working_directory,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
            )
            self.command_logs.append(command_log)
            self.metrics.commands_executed += 1
            
            return {
                "stdout": stdout,
                "stderr": stderr,
                "returncode": returncode,
                "duration_seconds": duration,
            }
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Error executing command '{command}': {e}")
            
            # Log failed command
            command_log = CommandLog(
                timestamp=start_time,
                command=command,
                working_directory=working_directory,
                returncode=-1,
                stdout="",
                stderr=error_msg,
                duration_seconds=duration,
            )
            self.command_logs.append(command_log)
            self.metrics.commands_executed += 1
            
            return {
                "stdout": "",
                "stderr": error_msg,
                "returncode": -1,
                "duration_seconds": duration,
                "error": error_msg,
            }
    
    def snapshot_filesystem(self, snapshot_name: str) -> Path:
        """
        Create a snapshot of the container filesystem.
        
        Args:
            snapshot_name: Name for the snapshot
            
        Returns:
            Path to snapshot directory
        """
        snapshot_dir = self.workspace_dir / "snapshots" / snapshot_name
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy workspace files to snapshot
        workspace_in_container = "/workspace"
        
        try:
            # Create tar archive of container filesystem
            tar_stream, _ = self.container.get_archive(workspace_in_container)
            
            # Save to snapshot directory
            tar_path = snapshot_dir / "filesystem.tar"
            with open(tar_path, "wb") as f:
                for chunk in tar_stream:
                    f.write(chunk)
            
            logger.info(f"Created filesystem snapshot: {snapshot_dir}")
            return snapshot_dir
            
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            # Fallback: copy from host workspace
            if self.workspace_dir.exists():
                shutil.copytree(self.workspace_dir, snapshot_dir, dirs_exist_ok=True)
            return snapshot_dir
    
    def save_metadata(self) -> Path:
        """
        Save sandbox metadata (metrics, logs, etc.) to workspace.
        
        Returns:
            Path to metadata file
        """
        metadata = {
            "task_id": self.task_id,
            "metrics": self.metrics.to_dict(),
            "command_logs": [log.to_dict() for log in self.command_logs],
            "container_name": self.container_name if self.container else None,
            "workspace_dir": str(self.workspace_dir),
        }
        
        metadata_path = self.workspace_dir / "sandbox_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved sandbox metadata: {metadata_path}")
        return metadata_path
    
    def cleanup(self, keep_snapshot: bool = True) -> None:
        """
        Clean up sandbox, optionally keeping snapshot.
        
        Args:
            keep_snapshot: Whether to keep filesystem snapshot
        """
        # Save final snapshot
        if keep_snapshot:
            self.snapshot_filesystem("final")
            self.save_metadata()
        
        # Remove container
        self.remove()
        
        logger.info(f"Cleaned up sandbox {self.task_id}")
