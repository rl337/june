"""
Unit tests for manage_tensorrt_llm command.

Tests TensorRTLLMManager and ManageTensorRTLLMCommand classes.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Optional

from essence.commands.manage_tensorrt_llm import (
    TensorRTLLMManager,
    ManageTensorRTLLMCommand,
)


class TestTensorRTLLMManager:
    """Tests for TensorRTLLMManager class."""

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_init(self, mock_client_class):
        """Test manager initialization."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager(base_url="http://test:8002", timeout=60)

        assert manager.base_url == "http://test:8002"
        assert manager.timeout == 60
        assert manager.client == mock_client

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_init_without_httpx(self, mock_client_class):
        """Test manager initialization when httpx is not available."""
        # Mock httpx not being available
        with patch("essence.commands.manage_tensorrt_llm.HTTP_CLIENT_AVAILABLE", False):
            manager = TensorRTLLMManager()

            assert manager.client is None

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_load_model_success(self, mock_client_class):
        """Test successful model loading."""
        mock_client = MagicMock()
        mock_response = Mock(status_code=200, text="OK")
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, msg = manager.load_model("qwen3-30b")

        assert success is True
        assert "loaded successfully" in msg.lower()
        mock_client.post.assert_called_once()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_load_model_failure(self, mock_client_class):
        """Test failed model loading."""
        mock_client = MagicMock()
        mock_response = Mock(status_code=404, text="Model not found")
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, msg = manager.load_model("nonexistent")

        assert success is False
        assert "failed" in msg.lower() or "404" in msg

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_load_model_timeout(self, mock_client_class):
        """Test model loading timeout."""
        import httpx

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, msg = manager.load_model("qwen3-30b")

        assert success is False
        assert "timeout" in msg.lower()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_load_model_connection_error(self, mock_client_class):
        """Test model loading connection error."""
        import httpx

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection failed")
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, msg = manager.load_model("qwen3-30b")

        assert success is False
        assert "connect" in msg.lower() or "connection" in msg.lower()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_unload_model_success(self, mock_client_class):
        """Test successful model unloading."""
        mock_client = MagicMock()
        mock_response = Mock(status_code=200, text="OK")
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, msg = manager.unload_model("qwen3-30b")

        assert success is True
        assert "unloaded successfully" in msg.lower()
        mock_client.post.assert_called_once()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_unload_model_failure(self, mock_client_class):
        """Test failed model unloading."""
        mock_client = MagicMock()
        mock_response = Mock(status_code=404, text="Model not found")
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, msg = manager.unload_model("nonexistent")

        assert success is False
        assert "failed" in msg.lower() or "404" in msg

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_list_models_success(self, mock_client_class):
        """Test successful model listing."""
        mock_client = MagicMock()
        mock_response = Mock(
            status_code=200,
            json=lambda: {
                "models": [
                    {"name": "qwen3-30b", "version": "1", "state": "READY"},
                    {"name": "qwen3-7b", "version": "1", "state": "UNAVAILABLE"},
                ]
            },
        )
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, models, msg = manager.list_models()

        assert success is True
        assert len(models) == 2
        assert "found" in msg.lower()
        assert models[0]["name"] == "qwen3-30b"

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_list_models_empty(self, mock_client_class):
        """Test listing models when repository is empty."""
        mock_client = MagicMock()
        mock_response = Mock(status_code=200, json=lambda: {"models": []})
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, models, msg = manager.list_models()

        assert success is True
        assert len(models) == 0

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_list_models_connection_error(self, mock_client_class):
        """Test model listing connection error."""
        import httpx

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection failed")
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, models, msg = manager.list_models()

        assert success is False
        assert len(models) == 0
        assert "connect" in msg.lower() or "connection" in msg.lower()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_get_model_status_ready(self, mock_client_class):
        """Test getting model status when model is ready."""
        mock_client = MagicMock()
        mock_response = Mock(status_code=200)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, status, msg = manager.get_model_status("qwen3-30b")

        assert success is True
        assert status == "READY"
        assert "ready" in msg.lower()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_get_model_status_unavailable(self, mock_client_class):
        """Test getting model status when model exists but is unavailable."""
        mock_client = MagicMock()
        # First call (ready check) returns 404
        # Second call (list models) returns model in repository
        mock_response_404 = Mock(status_code=404)
        mock_response_list = Mock(
            status_code=200,
            json=lambda: {
                "models": [
                    {"name": "qwen3-30b", "version": "1", "state": "UNAVAILABLE"}
                ]
            },
        )
        mock_client.get.side_effect = [mock_response_404, mock_response_list]
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, status, msg = manager.get_model_status("qwen3-30b")

        assert success is True
        assert status == "UNAVAILABLE"
        assert "not loaded" in msg.lower() or "unavailable" in msg.lower()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_get_model_status_not_found(self, mock_client_class):
        """Test getting model status when model is not found."""
        mock_client = MagicMock()
        # First call (ready check) returns 404
        # Second call (list models) returns empty list
        mock_response_404 = Mock(status_code=404)
        mock_response_list = Mock(status_code=200, json=lambda: {"models": []})
        mock_client.get.side_effect = [mock_response_404, mock_response_list]
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, status, msg = manager.get_model_status("nonexistent")

        assert success is False
        assert status is None
        assert "not found" in msg.lower()

    @patch("essence.commands.manage_tensorrt_llm.httpx.Client")
    def test_get_model_status_connection_error(self, mock_client_class):
        """Test getting model status connection error."""
        import httpx

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection failed")
        mock_client_class.return_value = mock_client

        manager = TensorRTLLMManager()
        success, status, msg = manager.get_model_status("qwen3-30b")

        assert success is False
        assert status is None
        assert "connect" in msg.lower() or "connection" in msg.lower()

    def test_load_model_without_httpx(self):
        """Test load_model when httpx is not available."""
        with patch("essence.commands.manage_tensorrt_llm.HTTP_CLIENT_AVAILABLE", False):
            manager = TensorRTLLMManager()
            success, msg = manager.load_model("qwen3-30b")

            assert success is False
            assert "httpx not available" in msg.lower()

    def test_unload_model_without_httpx(self):
        """Test unload_model when httpx is not available."""
        with patch("essence.commands.manage_tensorrt_llm.HTTP_CLIENT_AVAILABLE", False):
            manager = TensorRTLLMManager()
            success, msg = manager.unload_model("qwen3-30b")

            assert success is False
            assert "httpx not available" in msg.lower()

    def test_list_models_without_httpx(self):
        """Test list_models when httpx is not available."""
        with patch("essence.commands.manage_tensorrt_llm.HTTP_CLIENT_AVAILABLE", False):
            manager = TensorRTLLMManager()
            success, models, msg = manager.list_models()

            assert success is False
            assert len(models) == 0
            assert "httpx not available" in msg.lower()

    def test_get_model_status_without_httpx(self):
        """Test get_model_status when httpx is not available."""
        with patch("essence.commands.manage_tensorrt_llm.HTTP_CLIENT_AVAILABLE", False):
            manager = TensorRTLLMManager()
            success, status, msg = manager.get_model_status("qwen3-30b")

            assert success is False
            assert status is None
            assert "httpx not available" in msg.lower()


class TestManageTensorRTLLMCommand:
    """Tests for ManageTensorRTLLMCommand class."""

    def test_command_name(self):
        """Test command name."""
        assert ManageTensorRTLLMCommand.get_name() == "manage-tensorrt-llm"

    def test_command_description(self):
        """Test command description."""
        desc = ManageTensorRTLLMCommand.get_description()
        assert "manage" in desc.lower() or "tensorrt" in desc.lower()

    def test_add_args(self):
        """Test argument parser configuration."""
        import argparse

        parser = argparse.ArgumentParser()
        ManageTensorRTLLMCommand.add_args(parser)

        # Parse test arguments
        args = parser.parse_args(
            [
                "--action",
                "load",
                "--model",
                "qwen3-30b",
                "--tensorrt-llm-url",
                "http://test:8002",
                "--timeout",
                "60",
            ]
        )

        assert args.action == "load"
        assert args.model == "qwen3-30b"
        assert args.tensorrt_llm_url == "http://test:8002"
        assert args.timeout == 60

    @patch("essence.commands.manage_tensorrt_llm.TensorRTLLMManager")
    def test_init_valid(self, mock_manager_class):
        """Test command initialization with valid arguments."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        args = Mock()
        args.action = "load"
        args.model = "qwen3-30b"
        args.tensorrt_llm_url = "http://test:8002"
        args.timeout = 60

        command = ManageTensorRTLLMCommand(args)

        # Should not raise exception
        command.init()

        mock_manager_class.assert_called_once_with(
            base_url="http://test:8002", timeout=60
        )

    @patch("sys.exit")
    def test_init_missing_model(self, mock_exit):
        """Test command initialization when model is missing for load action."""
        args = Mock()
        args.action = "load"
        args.model = None

        command = ManageTensorRTLLMCommand(args)

        command.init()

        mock_exit.assert_called_once_with(1)

    @patch("essence.commands.manage_tensorrt_llm.TensorRTLLMManager")
    @patch("sys.exit")
    def test_run_load_action(self, mock_exit, mock_manager_class):
        """Test running load action."""
        mock_manager = MagicMock()
        mock_manager.load_model.return_value = (True, "Model loaded")
        mock_manager_class.return_value = mock_manager

        args = Mock()
        args.action = "load"
        args.model = "qwen3-30b"
        args.tensorrt_llm_url = "http://test:8002"
        args.timeout = 60

        command = ManageTensorRTLLMCommand(args)
        command.manager = mock_manager

        command.run()

        mock_manager.load_model.assert_called_once_with("qwen3-30b")
        mock_exit.assert_called_once_with(0)

    @patch("essence.commands.manage_tensorrt_llm.TensorRTLLMManager")
    @patch("sys.exit")
    def test_run_unload_action(self, mock_exit, mock_manager_class):
        """Test running unload action."""
        mock_manager = MagicMock()
        mock_manager.unload_model.return_value = (True, "Model unloaded")
        mock_manager_class.return_value = mock_manager

        args = Mock()
        args.action = "unload"
        args.model = "qwen3-30b"
        args.tensorrt_llm_url = "http://test:8002"
        args.timeout = 60

        command = ManageTensorRTLLMCommand(args)
        command.manager = mock_manager

        command.run()

        mock_manager.unload_model.assert_called_once_with("qwen3-30b")
        mock_exit.assert_called_once_with(0)

    @patch("essence.commands.manage_tensorrt_llm.TensorRTLLMManager")
    @patch("sys.exit")
    def test_run_list_action(self, mock_exit, mock_manager_class):
        """Test running list action."""
        mock_manager = MagicMock()
        mock_manager.list_models.return_value = (
            True,
            [{"name": "qwen3-30b", "state": "READY"}],
            "Found 1 model",
        )
        mock_manager_class.return_value = mock_manager

        args = Mock()
        args.action = "list"
        args.model = None
        args.tensorrt_llm_url = "http://test:8002"
        args.timeout = 60

        command = ManageTensorRTLLMCommand(args)
        command.manager = mock_manager

        command.run()

        mock_manager.list_models.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch("essence.commands.manage_tensorrt_llm.TensorRTLLMManager")
    @patch("sys.exit")
    def test_run_status_action(self, mock_exit, mock_manager_class):
        """Test running status action."""
        mock_manager = MagicMock()
        mock_manager.get_model_status.return_value = (True, "READY", "Model is ready")
        mock_manager_class.return_value = mock_manager

        args = Mock()
        args.action = "status"
        args.model = "qwen3-30b"
        args.tensorrt_llm_url = "http://test:8002"
        args.timeout = 60

        command = ManageTensorRTLLMCommand(args)
        command.manager = mock_manager

        command.run()

        mock_manager.get_model_status.assert_called_once_with("qwen3-30b")
        mock_exit.assert_called_once_with(0)
