import unittest
from unittest.mock import patch, mock_open
import os
import configparser # For creating mock config data

# Module to be tested
from june_agent import prompts
from typing import List # For agent_logs fallback in prompts.py if __main__ not found

# Store original path and templates for restoration if needed, or reload module
_original_prompts_file_path = prompts._PROMPTS_FILE_PATH
_original_prompt_templates_dict = prompts._PROMPT_TEMPLATES.copy()


class TestPrompts(unittest.TestCase):
    """
    Test suite for the prompt management system in `june_agent.prompts`.
    It covers loading prompts from files, retrieving formatted prompts,
    and handling various error conditions.
    """

    def tearDown(self):
        """
        Resets the state of the `prompts` module after each test.
        This is crucial because `prompts.py` uses global variables for caching
        loaded templates and relies on module-level initialization.
        This method ensures test isolation by clearing the cache and forcing
        re-initialization from the original default prompts file.
        """
        prompts._PROMPTS_FILE_PATH = _original_prompts_file_path
        prompts._PROMPT_TEMPLATES.clear()
        # Force re-initialization from the original file path.
        prompts._initialize_prompts()


    def test_get_prompt_success(self):
        """
        Tests successful retrieval and formatting of a prompt when placeholders are correctly provided.
        Uses a manually set prompt template for isolation from file loading in this specific test.
        """
        prompts._PROMPT_TEMPLATES.clear() # Isolate from file-loaded prompts for this test
        prompts._PROMPT_TEMPLATES["test_assess_id"] = {
            "id": "test_assess_id",
            "description": "A test prompt.",
            "template": "Task: {task_description}, Detail: {detail}"
        }

        formatted = prompts.get_prompt("test_assess_id", task_description="Write code", detail="Python")
        self.assertEqual(formatted, "Task: Write code, Detail: Python")

    def test_get_prompt_non_existent_id(self):
        """Tests that requesting a non-existent prompt ID returns None and logs a warning."""
        prompts._PROMPT_TEMPLATES.clear() # Ensure no fallback to other loaded prompts

        with patch.object(prompts.logger, 'warning') as mock_log_warn:
            formatted = prompts.get_prompt("non_existent_prompt_id")
            self.assertIsNone(formatted)
            mock_log_warn.assert_called_with("Prompt template with ID 'non_existent_prompt_id' not found.")

    def test_get_prompt_missing_placeholder_in_kwargs(self):
        """
        Tests that `get_prompt` returns None and logs an error if formatting fails
        due to a missing placeholder in the provided keyword arguments.
        """
        prompts._PROMPT_TEMPLATES.clear()
        prompts._PROMPT_TEMPLATES["test_placeholder_id"] = {
            "id": "test_placeholder_id",
            "description": "Test placeholder.",
            "template": "Hello {name}, welcome to {place}."
        }

        with patch.object(prompts.logger, 'error') as mock_log_error:
            formatted = prompts.get_prompt("test_placeholder_id", name="June") # 'place' is missing
            self.assertIsNone(formatted)
            mock_log_error.assert_called_once()
            args, _ = mock_log_error.call_args
            self.assertIn("Error formatting prompt 'test_placeholder_id'", args[0])
            self.assertIn("Missing placeholder key 'place'", args[0])


    @patch('june_agent.prompts.open', new_callable=mock_open)
    def test_load_prompts_from_file_valid_content(self, mock_file_open):
        """
        Tests the internal `_load_prompts_from_file` function with valid mock file content.
        Ensures prompts are parsed correctly into the expected dictionary structure.
        """
        mock_properties_content = """
[Prompts]
test_p1_id = prompt_one
test_p1_description = This is prompt one.
test_p1_template = Template for {name}.

test_p2_id = prompt_two
test_p2_description = This is prompt two.
test_p2_template = Another template for {value}.
"""
        # Configure the mock_open to return our mock content
        mock_file_open.return_value.read.return_value = mock_properties_content
        # If ConfigParser.read_file is used with a file object:
        mock_file_obj = mock_open(read_data=mock_properties_content)
        mock_file_open.return_value = mock_file_obj.return_value

        loaded = prompts._load_prompts_from_file("dummy/path/to/mock_prompts.properties")

        self.assertIn("prompt_one", loaded)
        self.assertEqual(loaded["prompt_one"]["template"], "Template for {name}.")
        self.assertEqual(loaded["prompt_one"]["description"], "This is prompt one.")

        self.assertIn("prompt_two", loaded)
        self.assertEqual(loaded["prompt_two"]["template"], "Another template for {value}.")


    @patch('june_agent.prompts.open', new_callable=mock_open)
    def test_load_prompts_missing_template_field(self, mock_file_open):
        """
        Tests that `_load_prompts_from_file` skips prompt definitions that are
        missing the essential '_template' field and logs a warning.
        """
        mock_properties_content = """
[Prompts]
test_incomplete_id = incomplete_prompt
test_incomplete_description = This prompt is missing its template.
# test_incomplete_template = ... (intentionally missing)
"""
        mock_file_open.return_value.read.return_value = mock_properties_content
        mock_file_obj = mock_open(read_data=mock_properties_content)
        mock_file_open.return_value = mock_file_obj.return_value

        with patch.object(prompts.logger, 'warning') as mock_log_warn:
            loaded = prompts._load_prompts_from_file("dummy/path.properties")
            self.assertNotIn("incomplete_prompt", loaded)
            mock_log_warn.assert_any_call(
                "Prompt definition for 'incomplete_prompt' is missing a '_template' field in dummy/path.properties. Skipping."
            )

    @patch('june_agent.prompts.open', side_effect=FileNotFoundError("Mock file not found"))
    def test_load_prompts_file_not_found(self, mock_file_open_error):
        """
        Tests that `_load_prompts_from_file` (via `_initialize_prompts`) handles
        a FileNotFoundError by logging an error and resulting in an empty prompt cache.
        """
        with patch.object(prompts.logger, 'error') as mock_log_error:
            # Call _initialize_prompts which internally calls _load_prompts_from_file
            # This ensures the logging within _initialize_prompts is also covered if it fails.
            prompts._PROMPT_TEMPLATES.clear() # Ensure it tries to load
            prompts._initialize_prompts()
            self.assertEqual(prompts._PROMPT_TEMPLATES, {}) # Should be empty
            # Check that the error from _load_prompts_from_file was logged
            mock_log_error.assert_any_call(f"Prompts file not found: {prompts._PROMPTS_FILE_PATH}")
            # And that _initialize_prompts logged its own error
            mock_log_error.assert_any_call("No prompts were loaded. Prompt system may not function correctly.")


    def test_initialize_prompts_populates_global_dict_from_actual_file(self):
        # This test relies on the actual default_prompts.properties file
        # and its content. It tests the module's initialization side-effect.
        # We need to ensure the module is reloaded for a clean test of its import-time logic.
        import importlib

        # Store original _PROMPT_TEMPLATES, then reload, then check, then restore.
        # This is a bit complex due to Python's module caching.
        # A simpler way for this specific test is to ensure the global is cleared
        # and then _initialize_prompts is called, which is what tearDown now does.

        # Assuming tearDown restores to original loaded state from file.
        # This test then verifies that the original loading worked.
        self.assertTrue(len(prompts._PROMPT_TEMPLATES) > 0, "Prompts should be loaded by default.")
        self.assertIn("assess_task_v1", prompts._PROMPT_TEMPLATES)
        self.assertEqual(prompts._PROMPT_TEMPLATES["assess_task_v1"]["id"], "assess_task_v1")
        self.assertIn("Task Description:", prompts._PROMPT_TEMPLATES["assess_task_v1"]["template"])


if __name__ == '__main__':
    unittest.main()
