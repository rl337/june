"""
Review sandbox command - Inspect sandbox snapshots from benchmark evaluations.

Usage:
    poetry run python -m essence review-sandbox <sandbox_snapshot_dir>
    poetry run python -m essence review-sandbox <output_dir> <task_id>
"""
import argparse
import json
import logging
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from essence.command import Command

logger = logging.getLogger(__name__)


def format_timestamp(timestamp: float) -> str:
    """Format Unix timestamp to readable string."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_duration(seconds: float) -> str:
    """Format duration in seconds to readable string."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}min"
    else:
        return f"{seconds/3600:.1f}hr"


def print_section(title: str, width: int = 60) -> None:
    """Print a section header."""
    print("\n" + "=" * width)
    print(title)
    print("=" * width)


def print_metadata(metadata: Dict[str, Any]) -> None:
    """Print sandbox metadata."""
    print_section("Metadata")

    print(f"Task ID: {metadata.get('task_id', 'N/A')}")
    print(f"Container Name: {metadata.get('container_name', 'N/A')}")
    print(f"Workspace Directory: {metadata.get('workspace_dir', 'N/A')}")

    metrics = metadata.get("metrics", {})
    if metrics:
        print("\n--- Metrics ---")
        print(f"Start Time: {format_timestamp(metrics.get('start_time', 0))}")
        if metrics.get("end_time"):
            print(f"End Time: {format_timestamp(metrics.get('end_time', 0))}")
            duration = metrics.get("end_time", 0) - metrics.get("start_time", 0)
            print(f"Duration: {format_duration(duration)}")
        print(f"Commands Executed: {metrics.get('commands_executed', 0)}")
        print(f"Files Created: {metrics.get('files_created', 0)}")
        print(f"Files Modified: {metrics.get('files_modified', 0)}")
        print(f"Total CPU Time: {format_duration(metrics.get('total_cpu_time', 0))}")
        print(f"Peak Memory: {metrics.get('peak_memory_mb', 0):.2f} MB")
        print(f"Disk I/O: {metrics.get('disk_io_bytes', 0) / 1024 / 1024:.2f} MB")
        print(f"Network Requests: {metrics.get('network_requests', 0)}")
        print(f"Iterations: {metrics.get('iterations', 0)}")
        print(f"Success: {metrics.get('success', False)}")
        if metrics.get("error_message"):
            print(f"Error: {metrics.get('error_message')}")


def print_command_logs(command_logs: List[Dict[str, Any]]) -> None:
    """Print command execution timeline."""
    print_section("Command Execution Timeline")

    if not command_logs:
        print("No commands executed.")
        return

    print(f"Total commands: {len(command_logs)}\n")

    for i, log in enumerate(command_logs, 1):
        print(f"[{i}] {format_timestamp(log.get('timestamp', 0))}")
        print(f"    Command: {log.get('command', 'N/A')}")
        print(f"    Working Directory: {log.get('working_directory', 'N/A')}")
        print(f"    Return Code: {log.get('returncode', 'N/A')}")
        print(f"    Duration: {format_duration(log.get('duration_seconds', 0))}")

        stdout = log.get("stdout", "")
        if stdout:
            # Show first few lines of stdout
            lines = stdout.split("\n")[:5]
            print(f"    Stdout:")
            for line in lines:
                print(f"      {line}")
            stdout_lines = stdout.split("\n")
            if len(stdout_lines) > 5:
                print(f"      ... ({len(stdout_lines) - 5} more lines)")

        stderr = log.get("stderr", "")
        if stderr:
            # Show first few lines of stderr
            lines = stderr.split("\n")[:5]
            print(f"    Stderr:")
            for line in lines:
                print(f"      {line}")
            if len(stderr.split("\n")) > 5:
                print(f"      ... ({len(stderr.split('\n')) - 5} more lines)")

        print()


def print_filesystem_tree(snapshot_dir: Path) -> None:
    """Print filesystem tree from snapshot."""
    print_section("File System Tree")

    # Look for filesystem.tar
    tar_path = snapshot_dir / "filesystem.tar"
    if not tar_path.exists():
        # Look in snapshots subdirectory
        snapshots_dir = snapshot_dir / "snapshots" / "final"
        tar_path = snapshots_dir / "filesystem.tar"

    if tar_path.exists():
        try:
            with tarfile.open(tar_path, "r") as tar:
                members = tar.getmembers()
                print(f"Total files/directories: {len(members)}\n")

                # Show file tree (first 50 entries)
                for member in members[:50]:
                    file_type = "DIR" if member.isdir() else "FILE"
                    size = f"{member.size} bytes" if member.size else ""
                    print(f"  [{file_type:4}] {member.name} {size}")

                if len(members) > 50:
                    print(f"\n  ... ({len(members) - 50} more entries)")
        except Exception as e:
            print(f"Error reading filesystem.tar: {e}")
    else:
        # Try to list files directly in snapshot directory
        if snapshot_dir.exists():
            files = list(snapshot_dir.rglob("*"))
            print(f"Total files: {len(files)}\n")
            for file_path in files[:50]:
                if file_path.is_file():
                    size = file_path.stat().st_size
                    rel_path = file_path.relative_to(snapshot_dir)
                    print(f"  [FILE] {rel_path} ({size} bytes)")

            if len(files) > 50:
                print(f"\n  ... ({len(files) - 50} more files)")
        else:
            print("No filesystem snapshot found.")


def print_efficiency_metrics(metadata: Dict[str, Any]) -> None:
    """Print efficiency metrics."""
    print_section("Efficiency Metrics")

    metrics = metadata.get("metrics", {})
    if not metrics:
        print("No metrics available.")
        return

    # Calculate efficiency score components
    commands = metrics.get("commands_executed", 0)
    files_created = metrics.get("files_created", 0)
    files_modified = metrics.get("files_modified", 0)
    duration = (
        metrics.get("end_time", 0) - metrics.get("start_time", 0)
        if metrics.get("end_time")
        else 0
    )
    iterations = metrics.get("iterations", 0)
    memory_mb = metrics.get("peak_memory_mb", 0)
    cpu_time = metrics.get("total_cpu_time", 0)

    print("--- Resource Usage ---")
    print(f"Execution Time: {format_duration(duration)}")
    print(f"CPU Time: {format_duration(cpu_time)}")
    print(f"Peak Memory: {memory_mb:.2f} MB")
    print(f"Disk I/O: {metrics.get('disk_io_bytes', 0) / 1024 / 1024:.2f} MB")

    print("\n--- Activity Metrics ---")
    print(f"Commands Executed: {commands}")
    print(f"Files Created: {files_created}")
    print(f"Files Modified: {files_modified}")
    print(f"Iterations: {iterations}")

    print("\n--- Efficiency Indicators ---")
    if duration > 0:
        print(f"Commands per second: {commands / duration:.2f}")
        print(f"Files per second: {(files_created + files_modified) / duration:.2f}")
    if commands > 0:
        print(f"Average time per command: {format_duration(duration / commands)}")
    if iterations > 0:
        print(f"Average time per iteration: {format_duration(duration / iterations)}")

    success = metrics.get("success", False)
    print(f"\nTask Success: {'✓' if success else '✗'}")


def find_sandbox_snapshot(output_dir: Path, task_id: str) -> Optional[Path]:
    """Find sandbox snapshot directory given output dir and task ID."""
    # Check in sandboxes subdirectory
    sandbox_dir = output_dir / "sandboxes" / f"{task_id}_snapshot"
    if sandbox_dir.exists():
        return sandbox_dir

    # Check in dataset subdirectories
    for dataset_dir in output_dir.iterdir():
        if dataset_dir.is_dir():
            sandbox_dir = dataset_dir / "sandboxes" / f"{task_id}_snapshot"
            if sandbox_dir.exists():
                return sandbox_dir

    return None


class ReviewSandboxCommand(Command):
    """
    Command for reviewing sandbox snapshots from benchmark evaluations.

    Provides a tool for inspecting sandbox snapshots created during benchmark
    task execution. Displays metadata, command logs, filesystem structure,
    and efficiency metrics for debugging and analysis of coding agent behavior.

    Supports both direct path specification and task ID lookup within output
    directories. Can output results in human-readable or JSON format.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "review-sandbox"
        """
        return "review-sandbox"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Review sandbox snapshot from benchmark evaluation"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures sandbox snapshot path, optional task ID lookup, and output format.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "path",
            help="Path to sandbox snapshot directory or output directory",
        )
        parser.add_argument(
            "task_id",
            nargs="?",
            help="Task ID (if path is output directory)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output as JSON",
        )

    def init(self) -> None:
        """
        Initialize review sandbox command.

        No initialization is needed for this read-only tool. The command
        operates directly on filesystem paths without requiring service setup.
        """
        # No initialization needed for this tool
        pass

    def run(self) -> None:
        """
        Run the review sandbox tool.

        Loads sandbox snapshot metadata and displays comprehensive information
        including task details, command execution logs, filesystem structure,
        and efficiency metrics. Supports both human-readable and JSON output formats.

        Exits:
            sys.exit(1): If sandbox snapshot or metadata file is not found
        """
        snapshot_dir = Path(self.args.path)

        # If task_id is provided, treat path as output directory
        if self.args.task_id:
            found = find_sandbox_snapshot(snapshot_dir, self.args.task_id)
            if found:
                snapshot_dir = found
            else:
                logger.error(
                    f"Sandbox snapshot not found for task {self.args.task_id} in {self.args.path}"
                )
                sys.exit(1)

        if not snapshot_dir.exists():
            logger.error(f"Sandbox snapshot directory not found: {snapshot_dir}")
            sys.exit(1)

        # Load metadata
        metadata_file = snapshot_dir / "sandbox_metadata.json"
        if not metadata_file.exists():
            # Try in parent directory
            metadata_file = snapshot_dir.parent / "sandbox_metadata.json"

        if not metadata_file.exists():
            logger.error(f"Metadata file not found in {snapshot_dir}")
            logger.error("Expected: sandbox_metadata.json")
            sys.exit(1)

        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        if self.args.json:
            # Output as JSON
            print(json.dumps(metadata, indent=2))
        else:
            # Print formatted output
            print(f"\n{'='*60}")
            print(f"Sandbox Review: {metadata.get('task_id', 'N/A')}")
            print(f"{'='*60}")

            print_metadata(metadata)

            command_logs = metadata.get("command_logs", [])
            if command_logs:
                print_command_logs(command_logs)

            print_filesystem_tree(snapshot_dir)

            print_efficiency_metrics(metadata)

            print(f"\n{'='*60}")
            print(f"Review complete. Sandbox data at: {snapshot_dir}")
            print(f"{'='*60}\n")

    def cleanup(self) -> None:
        """
        Clean up review sandbox command.

        No cleanup is needed for this read-only tool. The command only reads
        filesystem data and does not maintain any persistent resources.
        """
        # No cleanup needed for this tool
        pass
