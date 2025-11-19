"""
Unit tests for setup_triton_repository command.

Tests TritonRepositoryManager and SetupTritonRepositoryCommand classes.
"""
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from essence.commands.setup_triton_repository import (
    SetupTritonRepositoryCommand,
    TritonRepositoryManager,
)


class TestTritonRepositoryManager:
    """Tests for TritonRepositoryManager class."""

    def test_init(self):
        """Test manager initialization."""
        manager = TritonRepositoryManager(repository_path="/test/repo")

        assert str(manager.repository_path) == "/test/repo"

    def test_init_default_path(self):
        """Test manager initialization with default path."""
        manager = TritonRepositoryManager()

        assert "triton-repository" in str(manager.repository_path)

    def test_create_model_structure_success(self):
        """Test successful model structure creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            success, msg = manager.create_model_structure("test-model", "1")

            assert success is True
            assert "created" in msg.lower() or "test-model" in msg

            # Verify directory was created
            model_dir = Path(tmpdir) / "test-model" / "1"
            assert model_dir.exists()
            assert model_dir.is_dir()

            # Verify README was created
            readme = model_dir / "README.md"
            assert readme.exists()
            assert "test-model" in readme.read_text()

    def test_create_model_structure_existing(self):
        """Test creating model structure when directory already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create first time
            success1, msg1 = manager.create_model_structure("test-model", "1")
            assert success1 is True

            # Create again (should succeed with exist_ok=True)
            success2, msg2 = manager.create_model_structure("test-model", "1")
            assert success2 is True

    def test_create_model_structure_readme_not_overwritten(self):
        """Test that existing README is not overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create structure
            manager.create_model_structure("test-model", "1")

            # Modify README
            readme = Path(tmpdir) / "test-model" / "1" / "README.md"
            original_content = readme.read_text()
            readme.write_text("Custom README")

            # Create again
            manager.create_model_structure("test-model", "1")

            # README should still be custom
            assert readme.read_text() == "Custom README"

    def test_validate_model_structure_not_exists(self):
        """Test validation when model directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            is_valid, missing_files, msg = manager.validate_model_structure(
                "nonexistent", "1"
            )

            assert is_valid is False
            assert "not exist" in msg.lower() or "does not exist" in msg.lower()

    def test_validate_model_structure_complete(self):
        """Test validation when model structure is complete."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create structure
            model_dir = Path(tmpdir) / "test-model" / "1"
            model_dir.mkdir(parents=True)

            # Add required files
            (model_dir / "config.pbtxt").write_text("name: test-model")
            (model_dir / "model.engine").write_text("engine data")
            (model_dir / "tokenizer.json").write_text("{}")

            is_valid, missing_files, msg = manager.validate_model_structure(
                "test-model", "1"
            )

            assert is_valid is True
            assert len(missing_files) == 0
            assert "valid" in msg.lower()

    def test_validate_model_structure_missing_config(self):
        """Test validation when config.pbtxt is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create structure without config
            model_dir = Path(tmpdir) / "test-model" / "1"
            model_dir.mkdir(parents=True)
            (model_dir / "model.engine").write_text("engine data")

            is_valid, missing_files, msg = manager.validate_model_structure(
                "test-model", "1"
            )

            assert is_valid is False
            assert "config.pbtxt" in missing_files

    def test_validate_model_structure_missing_engine_warning(self):
        """Test validation when engine files are missing (warning only)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create structure with config but no engine
            model_dir = Path(tmpdir) / "test-model" / "1"
            model_dir.mkdir(parents=True)
            (model_dir / "config.pbtxt").write_text("name: test-model")

            is_valid, missing_files, msg = manager.validate_model_structure(
                "test-model", "1"
            )

            # Should be valid but with warnings
            assert is_valid is True
            assert "warning" in msg.lower() or "engine" in msg.lower()

    def test_validate_model_structure_missing_tokenizer_warning(self):
        """Test validation when tokenizer files are missing (warning only)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create structure with config and engine but no tokenizer
            model_dir = Path(tmpdir) / "test-model" / "1"
            model_dir.mkdir(parents=True)
            (model_dir / "config.pbtxt").write_text("name: test-model")
            (model_dir / "model.engine").write_text("engine data")

            is_valid, missing_files, msg = manager.validate_model_structure(
                "test-model", "1"
            )

            # Should be valid but with warnings
            assert is_valid is True
            assert "warning" in msg.lower() or "tokenizer" in msg.lower()

    def test_list_models_empty_repository(self):
        """Test listing models when repository is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            success, models, msg = manager.list_models()

            assert success is True
            assert len(models) == 0
            assert "found" in msg.lower() or "0" in msg

    def test_list_models_repository_not_exists(self):
        """Test listing models when repository doesn't exist."""
        manager = TritonRepositoryManager(repository_path="/nonexistent/path")

        success, models, msg = manager.list_models()

        assert success is False
        assert len(models) == 0
        assert "not exist" in msg.lower() or "does not exist" in msg.lower()

    def test_list_models_with_models(self):
        """Test listing models when models exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create multiple models
            (Path(tmpdir) / "model1" / "1").mkdir(parents=True)
            (Path(tmpdir) / "model1" / "2").mkdir(parents=True)
            (Path(tmpdir) / "model2" / "1").mkdir(parents=True)
            (Path(tmpdir) / "other").mkdir()  # Not a model (no version dir)

            success, models, msg = manager.list_models()

            assert success is True
            assert len(models) == 2
            assert "found" in msg.lower() or "2" in msg

            # Check model names
            model_names = [m["name"] for m in models]
            assert "model1" in model_names
            assert "model2" in model_names

            # Check versions
            model1 = next(m for m in models if m["name"] == "model1")
            assert "1" in model1["versions"]
            assert "2" in model1["versions"]

    def test_list_models_sorted(self):
        """Test that models are sorted by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TritonRepositoryManager(repository_path=tmpdir)

            # Create models in non-alphabetical order
            (Path(tmpdir) / "zebra" / "1").mkdir(parents=True)
            (Path(tmpdir) / "alpha" / "1").mkdir(parents=True)
            (Path(tmpdir) / "beta" / "1").mkdir(parents=True)

            success, models, msg = manager.list_models()

            assert success is True
            assert models[0]["name"] == "alpha"
            assert models[1]["name"] == "beta"
            assert models[2]["name"] == "zebra"


class TestSetupTritonRepositoryCommand:
    """Tests for SetupTritonRepositoryCommand class."""

    def test_command_name(self):
        """Test command name."""
        assert SetupTritonRepositoryCommand.get_name() == "setup-triton-repository"

    def test_command_description(self):
        """Test command description."""
        desc = SetupTritonRepositoryCommand.get_description()
        assert "triton" in desc.lower() or "repository" in desc.lower()

    def test_add_args(self):
        """Test argument parser configuration."""
        import argparse

        parser = argparse.ArgumentParser()
        SetupTritonRepositoryCommand.add_args(parser)

        # Parse test arguments
        args = parser.parse_args(
            [
                "--action",
                "create",
                "--model",
                "test-model",
                "--version",
                "2",
                "--repository-path",
                "/test/repo",
            ]
        )

        assert args.action == "create"
        assert args.model == "test-model"
        assert args.version == "2"
        assert args.repository_path == "/test/repo"

    def test_add_args_defaults(self):
        """Test argument parser with defaults."""
        import argparse

        parser = argparse.ArgumentParser()
        SetupTritonRepositoryCommand.add_args(parser)

        args = parser.parse_args(["--model", "test-model"])

        assert args.action == "create"  # default
        assert args.version == "1"  # default

    @patch("sys.exit")
    def test_init_missing_model_for_create(self, mock_exit):
        """Test initialization when model is missing for create action."""
        args = Mock()
        args.action = "create"
        args.model = None
        args.version = "1"
        args.repository_path = "/test/repo"

        command = SetupTritonRepositoryCommand(args)
        command.init()

        mock_exit.assert_called_once_with(1)

    @patch("sys.exit")
    def test_init_missing_model_for_validate(self, mock_exit):
        """Test initialization when model is missing for validate action."""
        args = Mock()
        args.action = "validate"
        args.model = None
        args.version = "1"
        args.repository_path = "/test/repo"

        command = SetupTritonRepositoryCommand(args)
        command.init()

        mock_exit.assert_called_once_with(1)

    def test_init_valid(self):
        """Test initialization with valid arguments."""
        args = Mock()
        args.action = "create"
        args.model = "test-model"
        args.version = "1"
        args.repository_path = "/test/repo"

        command = SetupTritonRepositoryCommand(args)
        command.init()

        assert command.manager is not None
        assert str(command.manager.repository_path) == "/test/repo"

    @patch("sys.exit")
    def test_run_create_action_success(self, mock_exit):
        """Test running create action successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            args = Mock()
            args.action = "create"
            args.model = "test-model"
            args.version = "1"
            args.repository_path = tmpdir

            command = SetupTritonRepositoryCommand(args)
            command.init()

            command.run()

            # Should exit with success
            mock_exit.assert_called_with(0)

            # Verify directory was created
            model_dir = Path(tmpdir) / "test-model" / "1"
            assert model_dir.exists()

    @patch("sys.exit")
    def test_run_validate_action_success(self, mock_exit):
        """Test running validate action successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid model structure
            model_dir = Path(tmpdir) / "test-model" / "1"
            model_dir.mkdir(parents=True)
            (model_dir / "config.pbtxt").write_text("name: test-model")
            (model_dir / "model.engine").write_text("engine")
            (model_dir / "tokenizer.json").write_text("{}")

            args = Mock()
            args.action = "validate"
            args.model = "test-model"
            args.version = "1"
            args.repository_path = tmpdir

            command = SetupTritonRepositoryCommand(args)
            command.init()

            command.run()

            mock_exit.assert_called_with(0)

    @patch("sys.exit")
    def test_run_validate_action_failure(self, mock_exit):
        """Test running validate action when validation fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            args = Mock()
            args.action = "validate"
            args.model = "nonexistent"
            args.version = "1"
            args.repository_path = tmpdir

            command = SetupTritonRepositoryCommand(args)
            command.init()

            command.run()

            mock_exit.assert_called_with(1)

    @patch("sys.exit")
    def test_run_list_action_success(self, mock_exit):
        """Test running list action successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some models
            (Path(tmpdir) / "model1" / "1").mkdir(parents=True)
            (Path(tmpdir) / "model2" / "1").mkdir(parents=True)

            args = Mock()
            args.action = "list"
            args.model = None
            args.version = "1"
            args.repository_path = tmpdir

            command = SetupTritonRepositoryCommand(args)
            command.init()

            command.run()

            mock_exit.assert_called_with(0)

    @patch("sys.exit")
    def test_run_list_action_empty(self, mock_exit):
        """Test running list action when repository is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            args = Mock()
            args.action = "list"
            args.model = None
            args.version = "1"
            args.repository_path = tmpdir

            command = SetupTritonRepositoryCommand(args)
            command.init()

            command.run()

            mock_exit.assert_called_with(0)

    def test_cleanup(self):
        """Test cleanup method."""
        args = Mock()
        args.action = "list"
        args.model = None
        args.version = "1"
        args.repository_path = "/test/repo"

        command = SetupTritonRepositoryCommand(args)

        # Should not raise exception
        command.cleanup()
