import unittest
import datetime
import json # For creating mock AI JSON responses
from unittest.mock import patch, MagicMock

from june_agent.task import Task as DomainTask
from june_agent.request import APIRequest, TogetherAIRequest # TogetherAIRequest is instantiated in assess
from june_agent.models_v2.pydantic_models import TaskSchema # For testing to_pydantic_schema

class TestTaskDomainAssessment(unittest.TestCase):

    def setUp(self):
        # This mock might be used by other methods like execute, but assess creates its own request object.
        # We will patch 'june_agent.task.TogetherAIRequest' where assess uses it.
        pass

    def test_task_initialization_defaults(self):
        task = DomainTask(description="Init Test")
        self.assertEqual(task.status, DomainTask.STATUS_PENDING)
        self.assertEqual(task.phase, DomainTask.PHASE_ASSESSMENT)
        self.assertIsNone(task.suggested_subtasks)

    # --- Tests for the new assess() method ---

    @patch('june_agent.task.get_prompt') # Mocks get_prompt within task.py
    @patch('june_agent.task.TogetherAIRequest.execute') # Mocks execute on instances of TogetherAIRequest
    def test_assess_direct_completion(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted assessment prompt"
        ai_response = {
            "assessment_outcome": "direct_completion",
            "result_payload": "Task successfully completed by AI assessment.",
            "reasoning": "AI determined it can do this now."
        }
        mock_execute.return_value = json.dumps(ai_response)

        task = DomainTask(description="Test direct completion")
        task.assess()

        mock_get_prompt.assert_called_once_with("assess_task_v1", task_description=task.description)
        mock_execute.assert_called_once_with("Formatted assessment prompt")
        self.assertEqual(task.status, DomainTask.STATUS_COMPLETED)
        self.assertIsNone(task.phase)
        self.assertEqual(task.result, "Task successfully completed by AI assessment.")
        self.assertIsNone(task.error_message)
        self.assertIsNone(task.suggested_subtasks)

    @patch('june_agent.task.get_prompt')
    @patch('june_agent.task.TogetherAIRequest.execute')
    def test_assess_subtask_breakdown(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted prompt"
        subtask_descs = ["Subtask 1 desc", "Subtask 2 desc"]
        ai_response = {
            "assessment_outcome": "subtask_breakdown",
            "result_payload": subtask_descs,
            "reasoning": "Task is complex."
        }
        mock_execute.return_value = json.dumps(ai_response)

        task = DomainTask(description="Test subtask breakdown")
        task.assess()

        self.assertEqual(task.status, DomainTask.STATUS_PENDING_SUBTASKS)
        self.assertIsNone(task.phase) # Phase is None when PENDING_SUBTASKS
        self.assertEqual(task.suggested_subtasks, subtask_descs)
        self.assertIsNone(task.result)
        self.assertIsNone(task.error_message)

    @patch('june_agent.task.get_prompt')
    @patch('june_agent.task.TogetherAIRequest.execute')
    def test_assess_cannot_complete(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted prompt"
        ai_response = {
            "assessment_outcome": "cannot_complete",
            "result_payload": "Reason for not completing.",
            "reasoning": "AI cannot do this."
        }
        mock_execute.return_value = json.dumps(ai_response)

        task = DomainTask(description="Test cannot complete")
        task.assess()

        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIsNone(task.phase)
        self.assertEqual(task.error_message, "Reason for not completing.")
        self.assertIsNone(task.result)

    @patch('june_agent.task.get_prompt')
    @patch('june_agent.task.TogetherAIRequest.execute')
    def test_assess_api_request_error_from_execute(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted prompt"
        mock_execute.return_value = "Error: API connection failed" # Error from APIRequest layer

        task = DomainTask(description="Test API request error")
        task.assess()

        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIsNone(task.phase)
        self.assertIn("Assessment API request failed: Error: API connection failed", task.error_message)

    @patch('june_agent.task.get_prompt')
    @patch('june_agent.task.TogetherAIRequest.execute')
    def test_assess_json_decode_error(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted prompt"
        mock_execute.return_value = "This is not valid JSON { definitely not"

        task = DomainTask(description="Test JSON decode error")
        task.assess()

        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIsNone(task.phase)
        self.assertIn("Failed to parse AI assessment response as JSON", task.error_message)

    @patch('june_agent.task.get_prompt')
    @patch('june_agent.task.TogetherAIRequest.execute')
    def test_assess_unknown_outcome_from_ai(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted prompt"
        ai_response = {"assessment_outcome": "maybe_later", "result_payload": "Payload"}
        mock_execute.return_value = json.dumps(ai_response)

        task = DomainTask(description="Test unknown outcome")
        task.assess()

        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIsNone(task.phase)
        self.assertIn("Unknown assessment outcome from AI: 'maybe_later'", task.error_message)

    @patch('june_agent.task.get_prompt')
    @patch('june_agent.task.TogetherAIRequest.execute')
    def test_assess_invalid_subtask_payload(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted prompt"
        ai_response = {
            "assessment_outcome": "subtask_breakdown",
            "result_payload": "This should be a list, not a string.", # Invalid payload
            "reasoning": "Incorrect payload type."
        }
        mock_execute.return_value = json.dumps(ai_response)

        task = DomainTask(description="Test invalid subtask payload")
        task.assess()

        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIsNone(task.phase)
        self.assertIn("AI suggested subtask breakdown but payload was invalid", task.error_message)

    def test_assess_no_description_fail(self): # This test remains relevant
        task = DomainTask(description="")
        task.assess()
        self.assertEqual(task.status, DomainTask.STATUS_FAILED)
        self.assertIsNone(task.phase)
        self.assertEqual(task.error_message, "Task description is empty, cannot assess.")

    def test_assess_get_prompt_fails(self):
        with patch('june_agent.task.get_prompt', return_value=None) as mock_get_prompt:
            task = DomainTask(description="Test prompt retrieval failure")
            task.assess()
            mock_get_prompt.assert_called_once()
            self.assertEqual(task.status, DomainTask.STATUS_FAILED)
            self.assertIsNone(task.phase)
            self.assertEqual(task.error_message, "Failed to retrieve assessment prompt.")

    @patch('june_agent.task.get_prompt')
    @patch('june_agent.task.TogetherAIRequest.execute')
    def test_assess_json_extraction_from_wrapped_response(self, mock_execute, mock_get_prompt):
        mock_get_prompt.return_value = "Formatted prompt"
        ai_response_payload = {
            "assessment_outcome": "direct_completion",
            "result_payload": "Extracted successfully.",
            "reasoning": "AI determined it can do this now."
        }
        # Simulate AI wrapping JSON in text
        wrapped_response = f"Some introductory text from AI.\n```json\n{json.dumps(ai_response_payload)}\n```\nSome concluding text."
        mock_execute.return_value = wrapped_response

        task = DomainTask(description="Test JSON extraction")
        task.assess()

        self.assertEqual(task.status, DomainTask.STATUS_COMPLETED)
        self.assertEqual(task.result, "Extracted successfully.")


    # --- Other Domain Logic Tests (largely unchanged from previous pure domain refactor) ---
    # (Keeping a few representative ones, assuming others are similar and were correct)

    def test_add_request(self): # Copied from previous version, still relevant
        task = DomainTask(description="Test Add Request")
        valid_request = TogetherAIRequest()
        task.add_request(valid_request)
        self.assertIn(valid_request, task.requests)
        with patch('june_agent.task.logger.warning') as mock_log_warn:
            task.add_request("not a request") # type: ignore
            self.assertEqual(len(task.requests), 1)
            mock_log_warn.assert_called_once()

    @patch('june_agent.task.TogetherAIRequest.execute') # Patching where it's used
    def test_execute_logic_success(self, mock_execute_method):
        mock_execute_method.return_value = "Mocked API Success for domain execution"
        task = DomainTask(description="Execute Success Domain")
        task.phase = DomainTask.PHASE_EXECUTION
        task.status = DomainTask.STATUS_EXECUTING
        # For execute to run, assess() must have added a request, or one must be added manually.
        # If assess() is not called, add one here for execute() to use.
        task.add_request(TogetherAIRequest()) # Instance whose execute is mocked

        task.execute()

        self.assertEqual(task.phase, DomainTask.PHASE_RECONCILIATION)
        self.assertEqual(task.result, "Mocked API Success for domain execution")
        self.assertIsNone(task.error_message)
        mock_execute_method.assert_called_once_with(task.description)


    def test_reconcile_logic_all_subtasks_completed(self): # Copied, still relevant
        parent = DomainTask(description="Parent - Subtasks Complete Domain")
        parent.status = DomainTask.STATUS_PENDING_SUBTASKS
        parent.phase = DomainTask.PHASE_RECONCILIATION
        st1 = DomainTask(description="ST1", status=DomainTask.STATUS_COMPLETED, phase=None)
        st2 = DomainTask(description="ST2", status=DomainTask.STATUS_COMPLETED, phase=None)
        parent.subtasks = [st1, st2]
        parent.reconcile()
        self.assertEqual(parent.status, DomainTask.STATUS_PENDING)
        self.assertEqual(parent.phase, DomainTask.PHASE_ASSESSMENT)

    def test_to_pydantic_schema(self): # Copied, still relevant
        task = DomainTask(description="Schema Test", initiative_id="init1")
        sub1 = DomainTask(description="Subtask for Schema")
        task.subtasks.append(sub1)
        schema = task.to_pydantic_schema()
        self.assertIsInstance(schema, TaskSchema)
        self.assertEqual(schema.id, task.id)
        self.assertListEqual(schema.subtask_ids, [sub1.id])


if __name__ == '__main__':
    unittest.main()
