import unittest
import datetime
import json
from unittest.mock import patch, MagicMock

from june_agent.task import Task as DomainTask
from june_agent.request_factory import RequestFactory # New import
from june_agent.testing.mocks import MockRequest    # New import
from june_agent.request import APIRequest # For type hint if needed
from june_agent.models_v2.pydantic_models import TaskSchema

class TestTaskDomainAssessment(unittest.TestCase):
    """
    Test suite for the `Task` domain object (`june_agent.task.Task`),
    focusing on its AI-driven `assess()` method using a mocked `RequestFactory`
    and `MockRequest`, as well as other in-memory business logic.
    These tests do not involve direct database interactions.
    """

    def setUp(self):
        """
        Sets up each test by creating a shared `MockRequest` instance and a
        `RequestFactory` configured to always return this specific mock instance.
        This allows tests to control the behavior of API requests made by the
        `Task.assess()` or `Task.execute()` methods and to verify interactions
        with the mock request object.
        """
        self.mock_api_request_instance = MockRequest("Default mock response for task tests")

        self.request_factory = RequestFactory(
            mode="custom", # Use "custom" mode to provide a specific mock instance
            custom_factory_fn=lambda: self.mock_api_request_instance
        )

    def test_task_initialization_defaults(self):
        """Tests that a Task initializes with correct default status, phase, and empty suggestion list."""
        task = DomainTask(description="Init Test")
        self.assertEqual(task.status, DomainTask.STATUS_PENDING)
        self.assertEqual(task.phase, DomainTask.PHASE_ASSESSMENT)
        self.assertIsNone(task.suggested_subtasks)

    # --- Tests for the assess() method using RequestFactory ---

    @patch('june_agent.task.get_prompt')
    def test_assess_direct_completion(self, mock_get_prompt):
        """
        Tests `Task.assess()` for the 'direct_completion' outcome from AI.
        Ensures the task's status, phase, and result are correctly updated,
        and that the mock API request (via factory) was called as expected.
        """
        mock_get_prompt.return_value = "Formatted assessment prompt"
        ai_response = {
            "assessment_outcome": "direct_completion",
            "result_payload": "Task successfully completed by AI assessment.",
        }
        # Configure the execute method of the mock_api_request_instance
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_response))

        task = DomainTask(description="Test direct completion")
        task.assess(self.request_factory) # Pass the factory

        mock_get_prompt.assert_called_once_with("assess_task_v1", task_description=task.description)
        self.mock_api_request_instance.execute.assert_called_once_with("Formatted assessment prompt")
        self.assertEqual(task.status, DomainTask.STATUS_COMPLETED)
        self.assertIsNone(task.phase)
        self.assertEqual(task.result, "Task successfully completed by AI assessment.")

    @patch('june_agent.task.get_prompt')
    def test_assess_subtask_breakdown(self, mock_get_prompt):
        """
        Tests `Task.assess()` for the 'subtask_breakdown' outcome.
        Verifies correct status, phase, and population of `suggested_subtasks`.
        """
        mock_get_prompt.return_value = "Formatted prompt"
        subtask_descs = ["Subtask 1 desc", "Subtask 2 desc"]
        ai_response = {"assessment_outcome": "subtask_breakdown", "result_payload": subtask_descs}
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_response))

        task = DomainTask(description="Test subtask breakdown")
        task.assess(self.request_factory)

        self.assertEqual(task.status, DomainTask.STATUS_PENDING_SUBTASKS)
        self.assertIsNone(task.phase)
        self.assertEqual(task.suggested_subtasks, subtask_descs)

    @patch('june_agent.task.get_prompt')
    def test_assess_proceed_to_execution(self, mock_get_prompt):
        """
        Tests `Task.assess()` for the 'proceed_to_execution' outcome.
        Verifies task status, phase, and that `assess` adds an APIRequest
        (the shared mock instance via factory) to `task.requests`.
        """
        mock_get_prompt.return_value = "Formatted prompt for exec"
        ai_response = {"assessment_outcome": "proceed_to_execution", "result_payload": "Standard execution."}
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_response))

        task = DomainTask(description="Test proceed to execution")

        assessment_execute_mock = self.mock_api_request_instance.execute

        task.assess(self.request_factory)

        self.assertEqual(task.status, DomainTask.STATUS_EXECUTING)
        self.assertEqual(task.phase, DomainTask.PHASE_EXECUTION)
        self.assertEqual(len(task.requests), 1)
        self.assertIs(task.requests[0], self.mock_api_request_instance)

        assessment_execute_mock.assert_called_once_with("Formatted prompt for exec")


    @patch('june_agent.task.get_prompt')
    def test_assess_api_request_error_from_factory_request(self, mock_get_prompt):
        """
        Tests `Task.assess()` when the APIRequest (from factory) `execute` method
        returns an error string (e.g., "Error: ...").
        """
        mock_get_prompt.return_value = "Formatted prompt"
        self.mock_api_request_instance.execute = MagicMock(return_value="Error: Factory API connection failed")

        task = DomainTask(description="Test API request error via factory")
        task.assess(self.request_factory)

        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIn("Assessment API request failed: Error: Factory API connection failed", task.error_message)

    @patch('june_agent.task.get_prompt')
    def test_assess_json_decode_error(self, mock_get_prompt):
        """Tests `Task.assess()` when the AI response is not valid JSON."""
        mock_get_prompt.return_value = "Formatted prompt"
        self.mock_api_request_instance.execute = MagicMock(return_value="Invalid JSON {")
        task = DomainTask(description="Test JSON decode error")
        task.assess(self.request_factory)
        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIn("Failed to parse AI assessment response as JSON", task.error_message)


    def test_assess_no_description_fail(self):
        """Tests that `Task.assess()` fails if the task description is empty."""
        task = DomainTask(description="")
        # No factory interaction expected if description is empty, but method requires it.
        task.assess(self.request_factory)
        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertEqual(task.error_message, "Task description is empty, cannot assess.")

    # --- Test execute() method with RequestFactory ---
    def test_execute_logic_success_with_factory(self):
        """
        Tests `Task.execute()` with a pre-populated request list (simulating
        a prior `assess` phase that determined 'proceed_to_execution').
        Verifies correct state transition and result/error handling.
        """
        task = DomainTask(description="Execute Success Domain with Factory")

        task.phase = DomainTask.PHASE_EXECUTION
        task.status = DomainTask.STATUS_EXECUTING

        # This MockRequest simulates the one added by assess() via the factory.
        execution_mock_request = MockRequest("Execution successful result")
        execution_mock_request.execute = MagicMock(return_value="Execution successful result") # Mock its execute
        task.add_request(execution_mock_request)

        # The factory passed to execute() isn't actively used by the current execute() logic
        # if self.requests is already populated, but it's part of the signature.
        task.execute(self.request_factory)

        self.assertEqual(task.phase, DomainTask.PHASE_RECONCILIATION)
        self.assertEqual(task.result, "Execution successful result")
        self.assertIsNone(task.error_message)
        # Verify that the execute method of the specific request object was called.
        execution_mock_request.execute.assert_called_once_with(task.description)


    # --- Keep other existing relevant domain logic tests ---
    # These tests verify other in-memory logic of the Task domain object.
    def test_add_request(self):
        """Tests adding valid and invalid request objects to the task's internal list."""
        task = DomainTask(description="Test Add Request")
        valid_request = MockRequest() # Use MockRequest for test consistency
        task.add_request(valid_request)
        self.assertIn(valid_request, task.requests)

    def test_reconcile_logic_all_subtasks_completed(self):
        """Tests reconcile() logic when all subtasks (in-memory domain objects) are completed."""
        parent = DomainTask(description="Parent - Subtasks Complete Domain")
        parent.status = DomainTask.STATUS_PENDING_SUBTASKS
        parent.phase = DomainTask.PHASE_RECONCILIATION
        st1 = DomainTask(description="ST1", status=DomainTask.STATUS_COMPLETED, phase=None)
        st2 = DomainTask(description="ST2", status=DomainTask.STATUS_COMPLETED, phase=None)
        parent.subtasks = [st1, st2] # Manually set in-memory subtasks
        parent.reconcile() # reconcile itself doesn't use factory
        self.assertEqual(parent.status, DomainTask.STATUS_PENDING)
        self.assertEqual(parent.phase, DomainTask.PHASE_ASSESSMENT)

    def test_to_pydantic_schema(self):
        """Tests conversion of the domain Task object to its Pydantic TaskSchema representation."""
        task = DomainTask(description="Schema Test", initiative_id="init1")
        sub1 = DomainTask(description="Subtask for Schema")
        task.subtasks.append(sub1) # Add in-memory subtask
        schema = task.to_pydantic_schema()
        self.assertIsInstance(schema, TaskSchema)
        self.assertEqual(schema.id, task.id)
        self.assertListEqual(schema.subtask_ids, [sub1.id]) # Check subtask ID representation


    # Adding back a few more error cases for assess for completeness
    @patch('june_agent.task.get_prompt')
    def test_assess_unknown_outcome_from_ai(self, mock_get_prompt):
        """Tests assess() handling of an unknown 'assessment_outcome' from AI."""
        mock_get_prompt.return_value = "Formatted prompt"
        ai_response = {"assessment_outcome": "maybe_later", "result_payload": "Payload"}
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_response))
        task = DomainTask(description="Test unknown outcome")
        task.assess(self.request_factory)
        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIn("Unknown assessment outcome from AI: 'maybe_later'", task.error_message)

    @patch('june_agent.task.get_prompt')
    def test_assess_invalid_subtask_payload(self, mock_get_prompt):
        """Tests assess() handling of invalid payload for 'subtask_breakdown' outcome."""
        mock_get_prompt.return_value = "Formatted prompt"
        ai_response = {
            "assessment_outcome": "subtask_breakdown",
            "result_payload": "This should be a list, not a string.",
        }
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_response))
        task = DomainTask(description="Test invalid subtask payload")
        task.assess(self.request_factory)
        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIn("AI suggested subtask breakdown but payload was invalid", task.error_message)

    def test_assess_get_prompt_fails(self):
        """Tests assess() behavior when `get_prompt` fails to return a prompt string."""
        with patch('june_agent.task.get_prompt', return_value=None) as mock_get_prompt:
            task = DomainTask(description="Test prompt retrieval failure")
            task.assess(self.request_factory) # Pass factory
            mock_get_prompt.assert_called_once()
            self.assertEqual(task.status, DomainTask.STATUS_FAILED)
            self.assertEqual(task.error_message, "Failed to retrieve assessment prompt.")

    @patch('june_agent.task.get_prompt')
    def test_assess_json_extraction_from_wrapped_response(self, mock_get_prompt):
        """Tests assess() ability to extract JSON from a response wrapped in other text."""
        mock_get_prompt.return_value = "Formatted prompt"
        ai_response_payload = {
            "assessment_outcome": "direct_completion",
            "result_payload": "Extracted successfully.",
        }
        wrapped_response = f"```json\n{json.dumps(ai_response_payload)}\n```"
        self.mock_api_request_instance.execute = MagicMock(return_value=wrapped_response)
        task = DomainTask(description="Test JSON extraction")
        task.assess(self.request_factory)
        self.assertEqual(task.status, DomainTask.STATUS_COMPLETED)
        self.assertEqual(task.result, "Extracted successfully.")


if __name__ == '__main__':
    unittest.main()
