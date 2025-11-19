"""
Unit tests for verify_tensorrt_llm command.

Tests verification functions and VerifyTensorRTLLMCommand class.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from essence.commands.verify_tensorrt_llm import (
    check_container_connectivity,
    check_grpc_connectivity,
    check_model_repository,
    check_gpu_availability,
    VerifyTensorRTLLMCommand,
)


class TestCheckContainerConnectivity:
    """Tests for check_container_connectivity function."""

    @patch("essence.commands.verify_tensorrt_llm.TensorRTLLMManager")
    def test_connectivity_success(self, mock_manager_class):
        """Test successful container connectivity check."""
        mock_manager = MagicMock()
        mock_manager.list_models.return_value = (
            True,
            [{"name": "qwen3-30b", "state": "READY"}],
            "Found 1 model",
        )
        mock_manager_class.return_value = mock_manager

        success, msg, details = check_container_connectivity("http://test:8002")

        assert success is True
        assert "found" in msg.lower() or "1 model" in msg.lower()
        assert details["accessible"] is True
        assert details["models_count"] == 1

    @patch("essence.commands.verify_tensorrt_llm.TensorRTLLMManager")
    def test_connectivity_failure(self, mock_manager_class):
        """Test failed container connectivity check."""
        mock_manager = MagicMock()
        mock_manager.list_models.return_value = (False, [], "Connection failed")
        mock_manager_class.return_value = mock_manager

        success, msg, details = check_container_connectivity("http://test:8002")

        assert success is False
        assert details["accessible"] is False
        assert details["models_count"] == 0


class TestCheckGRPCConnectivity:
    """Tests for check_grpc_connectivity function."""

    @patch("essence.commands.verify_tensorrt_llm.grpc")
    def test_grpc_not_available(self, mock_grpc):
        """Test when gRPC library is not available."""
        with patch("essence.commands.verify_tensorrt_llm.GRPC_AVAILABLE", False):
            success, msg, details = check_grpc_connectivity("test:8000")

            assert success is False
            assert "not available" in msg.lower()
            assert details["grpc_available"] is False

    @patch("essence.commands.verify_tensorrt_llm.grpc")
    def test_grpc_connectivity_success(self, mock_grpc):
        """Test successful gRPC connectivity check."""
        mock_channel = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None  # Success
        mock_grpc.insecure_channel.return_value = mock_channel
        mock_grpc.channel_ready_future.return_value = mock_future

        with patch("essence.commands.verify_tensorrt_llm.GRPC_AVAILABLE", True):
            success, msg, details = check_grpc_connectivity("test:8000")

            assert success is True
            assert "accessible" in msg.lower()
            assert details["connectable"] is True
            mock_channel.close.assert_called_once()

    @patch("essence.commands.verify_tensorrt_llm.grpc")
    def test_grpc_connectivity_timeout(self, mock_grpc):
        """Test gRPC connectivity timeout."""
        mock_channel = MagicMock()
        mock_future = MagicMock()
        # Create FutureTimeoutError exception class
        FutureTimeoutError = type("FutureTimeoutError", (Exception,), {})
        mock_future.result.side_effect = FutureTimeoutError()
        mock_grpc.insecure_channel.return_value = mock_channel
        mock_grpc.channel_ready_future.return_value = mock_future
        mock_grpc.FutureTimeoutError = FutureTimeoutError

        with patch("essence.commands.verify_tensorrt_llm.GRPC_AVAILABLE", True):
            success, msg, details = check_grpc_connectivity("test:8000")

            assert success is False
            assert "timeout" in msg.lower() or "not responding" in msg.lower()
            assert details["connectable"] is False
            mock_channel.close.assert_called_once()

    @patch("essence.commands.verify_tensorrt_llm.grpc")
    def test_grpc_connectivity_error(self, mock_grpc):
        """Test gRPC connectivity error."""
        mock_grpc.insecure_channel.side_effect = Exception("Connection error")

        with patch("essence.commands.verify_tensorrt_llm.GRPC_AVAILABLE", True):
            success, msg, details = check_grpc_connectivity("test:8000")

            assert success is False
            assert "error" in msg.lower() or "failed" in msg.lower()


class TestCheckModelRepository:
    """Tests for check_model_repository function."""

    def test_repository_not_exists(self):
        """Test when repository directory doesn't exist."""
        success, msg, details = check_model_repository("/nonexistent/path")

        assert success is False
        assert "not exist" in msg.lower() or "does not exist" in msg.lower()
        assert details["exists"] is False

    def test_repository_not_directory(self):
        """Test when repository path is not a directory."""
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            tmpfile.write(b"test")
            tmpfile_path = tmpfile.name

        try:
            success, msg, details = check_model_repository(tmpfile_path)

            assert success is False
            assert "not a directory" in msg.lower()
            assert details["exists"] is True
            assert details["is_directory"] is False
        finally:
            Path(tmpfile_path).unlink()

    def test_repository_empty(self):
        """Test when repository is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            success, msg, details = check_model_repository(tmpdir)

            assert success is True
            assert "0 model" in msg.lower() or "accessible" in msg.lower()
            assert len(details["models"]) == 0

    def test_repository_with_models(self):
        """Test when repository has models."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create model structures
            (Path(tmpdir) / "model1" / "1").mkdir(parents=True)
            (Path(tmpdir) / "model2" / "1").mkdir(parents=True)
            (Path(tmpdir) / "model2" / "2").mkdir(parents=True)
            (Path(tmpdir) / "other").mkdir()  # Not a model (no version dir)

            success, msg, details = check_model_repository(tmpdir)

            assert success is True
            assert "2 model" in msg.lower() or "accessible" in msg.lower()
            assert len(details["models"]) == 2
            assert details["models"][0]["name"] == "model1"
            assert details["models"][1]["name"] == "model2"
            assert "1" in details["models"][1]["versions"]
            assert "2" in details["models"][1]["versions"]

    def test_repository_error(self):
        """Test repository check with error."""
        # Create a path that will cause an error when iterating
        with patch("pathlib.Path.iterdir") as mock_iterdir:
            mock_iterdir.side_effect = PermissionError("Permission denied")

            with tempfile.TemporaryDirectory() as tmpdir:
                success, msg, details = check_model_repository(tmpdir)

                assert success is False
                assert "error" in msg.lower()


class TestCheckGPUAvailability:
    """Tests for check_gpu_availability function."""

    @patch("subprocess.run")
    def test_gpu_available(self, mock_run):
        """Test when GPU is available."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="NVIDIA RTX 4090, 24576 MiB, 10000 MiB\nNVIDIA RTX 4090, 24576 MiB, 10000 MiB",
        )

        success, msg, details = check_gpu_availability()

        assert success is True
        assert "gpu" in msg.lower() or "available" in msg.lower()
        assert details["gpu_available"] is True
        assert details["gpu_count"] == 2

    @patch("subprocess.run")
    def test_gpu_not_found(self, mock_run):
        """Test when GPU is not found."""
        mock_run.side_effect = FileNotFoundError()

        success, msg, details = check_gpu_availability()

        assert success is False
        assert "not found" in msg.lower() or "not available" in msg.lower()
        assert details["gpu_available"] is False

    @patch("subprocess.run")
    def test_gpu_timeout(self, mock_run):
        """Test when GPU check times out."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("nvidia-smi", 5)

        success, msg, details = check_gpu_availability()

        assert success is False
        assert "timeout" in msg.lower()
        assert details["gpu_available"] is False

    @patch("subprocess.run")
    def test_gpu_error(self, mock_run):
        """Test when GPU check has an error."""
        mock_run.side_effect = Exception("Unknown error")

        success, msg, details = check_gpu_availability()

        assert success is False
        assert "error" in msg.lower()
        assert details["gpu_available"] is False


class TestVerifyTensorRTLLMCommand:
    """Tests for VerifyTensorRTLLMCommand class."""

    def test_command_name(self):
        """Test command name."""
        assert VerifyTensorRTLLMCommand.get_name() == "verify-tensorrt-llm"

    def test_command_description(self):
        """Test command description."""
        desc = VerifyTensorRTLLMCommand.get_description()
        assert "verify" in desc.lower() or "tensorrt" in desc.lower()

    def test_add_args(self):
        """Test argument parser configuration."""
        import argparse

        parser = argparse.ArgumentParser()
        VerifyTensorRTLLMCommand.add_args(parser)

        # Parse test arguments
        args = parser.parse_args(
            [
                "--tensorrt-llm-url",
                "http://test:8002",
                "--grpc-port",
                "9000",
                "--grpc-host",
                "test-host",
                "--repository-path",
                "/test/repo",
                "--json",
            ]
        )

        assert args.tensorrt_llm_url == "http://test:8002"
        assert args.grpc_port == 9000
        assert args.grpc_host == "test-host"
        assert args.repository_path == "/test/repo"
        assert args.json is True

    def test_init(self):
        """Test command initialization."""
        args = Mock()
        args.tensorrt_llm_url = "http://test:8002"
        args.grpc_port = 8000
        args.grpc_host = "test"
        args.repository_path = "/test/repo"
        args.json = False

        command = VerifyTensorRTLLMCommand(args)
        command.init()

        assert "container_connectivity" in command.results
        assert "grpc_connectivity" in command.results
        assert "model_repository" in command.results
        assert "gpu_availability" in command.results
        assert command.results["overall_status"] == "unknown"
        assert command.results["migration_ready"] is False

    @patch("essence.commands.verify_tensorrt_llm.check_container_connectivity")
    @patch("essence.commands.verify_tensorrt_llm.check_grpc_connectivity")
    @patch("essence.commands.verify_tensorrt_llm.check_model_repository")
    @patch("essence.commands.verify_tensorrt_llm.check_gpu_availability")
    @patch("sys.exit")
    def test_run_all_checks_pass(
        self, mock_exit, mock_gpu, mock_repo, mock_grpc, mock_container
    ):
        """Test running verification when all checks pass."""
        mock_container.return_value = (True, "Connected", {"accessible": True})
        mock_grpc.return_value = (True, "gRPC accessible", {"connectable": True})
        mock_repo.return_value = (True, "Repository OK", {"models": []})
        mock_gpu.return_value = (True, "GPU available", {"gpu_available": True})

        args = Mock()
        args.tensorrt_llm_url = "http://test:8002"
        args.grpc_port = 8000
        args.grpc_host = "test"
        args.repository_path = "/test/repo"
        args.json = False

        command = VerifyTensorRTLLMCommand(args)
        command.init()
        command.run()

        assert command.results["migration_ready"] is True
        assert command.results["overall_status"] == "ready"
        assert command.results["checks_passed"] == 4
        mock_exit.assert_called_once_with(0)

    @patch("essence.commands.verify_tensorrt_llm.check_container_connectivity")
    @patch("essence.commands.verify_tensorrt_llm.check_grpc_connectivity")
    @patch("essence.commands.verify_tensorrt_llm.check_model_repository")
    @patch("essence.commands.verify_tensorrt_llm.check_gpu_availability")
    @patch("sys.exit")
    def test_run_critical_checks_fail(
        self, mock_exit, mock_gpu, mock_repo, mock_grpc, mock_container
    ):
        """Test running verification when critical checks fail."""
        mock_container.return_value = (
            False,
            "Connection failed",
            {"accessible": False},
        )
        mock_grpc.return_value = (False, "gRPC failed", {"connectable": False})
        mock_repo.return_value = (True, "Repository OK", {"models": []})
        mock_gpu.return_value = (True, "GPU available", {"gpu_available": True})

        args = Mock()
        args.tensorrt_llm_url = "http://test:8002"
        args.grpc_port = 8000
        args.grpc_host = "test"
        args.repository_path = "/test/repo"
        args.json = False

        command = VerifyTensorRTLLMCommand(args)
        command.init()
        command.run()

        assert command.results["migration_ready"] is False
        assert command.results["overall_status"] == "not_ready"
        assert command.results["checks_passed"] == 2
        mock_exit.assert_called_once_with(1)

    @patch("essence.commands.verify_tensorrt_llm.check_container_connectivity")
    @patch("essence.commands.verify_tensorrt_llm.check_grpc_connectivity")
    @patch("essence.commands.verify_tensorrt_llm.check_model_repository")
    @patch("essence.commands.verify_tensorrt_llm.check_gpu_availability")
    @patch("sys.exit")
    @patch("json.dumps")
    def test_run_json_output(
        self, mock_json_dumps, mock_exit, mock_gpu, mock_repo, mock_grpc, mock_container
    ):
        """Test running verification with JSON output."""
        mock_container.return_value = (True, "Connected", {"accessible": True})
        mock_grpc.return_value = (True, "gRPC accessible", {"connectable": True})
        mock_repo.return_value = (True, "Repository OK", {"models": []})
        mock_gpu.return_value = (True, "GPU available", {"gpu_available": True})
        mock_json_dumps.return_value = '{"test": "json"}'

        args = Mock()
        args.tensorrt_llm_url = "http://test:8002"
        args.grpc_port = 8000
        args.grpc_host = "test"
        args.repository_path = "/test/repo"
        args.json = True

        command = VerifyTensorRTLLMCommand(args)
        command.init()
        command.run()

        mock_json_dumps.assert_called_once()
        mock_exit.assert_called_once_with(0)

    def test_cleanup(self):
        """Test cleanup method."""
        args = Mock()
        args.tensorrt_llm_url = "http://test:8002"
        args.grpc_port = 8000
        args.grpc_host = "test"
        args.repository_path = "/test/repo"
        args.json = False

        command = VerifyTensorRTLLMCommand(args)

        # Should not raise exception
        command.cleanup()
