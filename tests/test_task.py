import unittest
import datetime
from unittest.mock import patch, MagicMock # For mocking APIRequest execute

from june_agent.task import Task # The pure domain Task class
from june_agent.request import APIRequest, TogetherAIRequest
from june_agent.models_v2.pydantic_models import TaskSchema # For testing to_pydantic_schema

class TestTaskDomain(unittest.TestCase):

    def setUp(self):
        # Mock APIRequest for tests that need it during execution phase
        self.mock_api_request_instance = MagicMock(spec=APIRequest)
        self.mock_api_request_instance.execute.return_value = "Successful API result from mock"

    def test_task_initialization_defaults(self):
        desc = "Test Task Domain Init"
        task = Task(description=desc)

        self.assertIsNotNone(task.id)
        self.assertEqual(task.description, desc)
        self.assertEqual(task.status, Task.STATUS_PENDING)
        self.assertEqual(task.phase, Task.PHASE_ASSESSMENT)
        self.assertIsNone(task.initiative_id)
        self.assertIsNone(task.parent_task_id)
        self.assertIsNone(task.result)
        self.assertIsNone(task.error_message)
        self.assertIsInstance(task.created_at, datetime.datetime)
        self.assertIsInstance(task.updated_at, datetime.datetime)
        self.assertEqual(task.requests, [])
        self.assertEqual(task.subtasks, [])

    def test_task_initialization_with_values(self):
        now = datetime.datetime.utcnow()
        task_id = "custom_id_123"
        init_id = "init_abc"
        parent_id = "parent_xyz"

        task = Task(
            description="Custom Values Task",
            task_id=task_id,
            initiative_id=init_id,
            parent_task_id=parent_id,
            status=Task.STATUS_COMPLETED,
            phase=None,
            result="Done deal",
            error_message="No error here",
            created_at=now,
            updated_at=now
        )
        self.assertEqual(task.id, task_id)
        self.assertEqual(task.initiative_id, init_id)
        self.assertEqual(task.parent_task_id, parent_id)
        self.assertEqual(task.status, Task.STATUS_COMPLETED)
        self.assertIsNone(task.phase)
        self.assertEqual(task.result, "Done deal")
        self.assertEqual(task.error_message, "No error here")
        self.assertEqual(task.created_at, now)

    def test_add_request(self):
        task = Task(description="Test Add Request")
        valid_request = TogetherAIRequest()
        task.add_request(valid_request)
        self.assertIn(valid_request, task.requests)

        with patch('june_agent.task.logger.warning') as mock_log_warn:
            task.add_request("not a request") # type: ignore
            self.assertEqual(len(task.requests), 1) # Should not add invalid
            mock_log_warn.assert_called_once()

    # --- Test Phase Method Logic (In-Memory) ---
    def test_assess_logic_simple_execution(self):
        task = Task(description="Assess to Execute")
        original_updated_at = task.updated_at

        task.assess()

        self.assertEqual(task.status, Task.STATUS_EXECUTING)
        self.assertEqual(task.phase, Task.PHASE_EXECUTION)
        self.assertEqual(len(task.requests), 1)
        self.assertIsInstance(task.requests[0], TogetherAIRequest)
        self.assertNotEqual(task.updated_at, original_updated_at)

    def test_assess_logic_no_description_fail(self):
        task = Task(description="")
        task.assess()
        self.assertEqual(task.status, Task.STATUS_FAILED)
        self.assertIsNone(task.phase)
        self.assertEqual(task.error_message, "Task description is empty, cannot assess.")

    @patch('june_agent.request.TogetherAIRequest.execute')
    def test_execute_logic_success(self, mock_execute_method):
        mock_execute_method.return_value = "Mocked API Success for domain"

        task = Task(description="Execute Success Domain")
        task.phase = Task.PHASE_EXECUTION # Setup state
        task.status = Task.STATUS_EXECUTING
        task.add_request(TogetherAIRequest()) # This request's execute will be mocked

        task.execute()

        self.assertEqual(task.phase, Task.PHASE_RECONCILIATION)
        self.assertEqual(task.result, "Mocked API Success for domain")
        self.assertIsNone(task.error_message) # Should be cleared on success
        mock_execute_method.assert_called_once_with(task.description)

    @patch('june_agent.request.TogetherAIRequest.execute')
    def test_execute_logic_api_returns_error_string(self, mock_execute_method):
        mock_execute_method.return_value = "Error: API problem in domain"
        task = Task(description="Execute API Error Domain")
        task.phase = Task.PHASE_EXECUTION
        task.status = Task.STATUS_EXECUTING
        task.add_request(TogetherAIRequest())
        task.execute()
        self.assertEqual(task.phase, Task.PHASE_RECONCILIATION)
        self.assertEqual(task.result, "Error: API problem in domain")
        self.assertEqual(task.error_message, "Error: API problem in domain")

    @patch('june_agent.request.TogetherAIRequest.execute')
    def test_execute_logic_api_raises_exception(self, mock_execute_method):
        exception_msg = "Domain API crashed"
        mock_execute_method.side_effect = Exception(exception_msg)
        task = Task(description="Execute API Exception Domain")
        task.phase = Task.PHASE_EXECUTION
        task.status = Task.STATUS_EXECUTING
        task.add_request(TogetherAIRequest())
        task.execute()
        self.assertEqual(task.phase, Task.PHASE_RECONCILIATION)
        self.assertIsNone(task.result)
        self.assertIn(exception_msg, task.error_message)

    def test_execute_logic_no_requests(self):
        task = Task(description="Execute No Requests Domain")
        task.phase = Task.PHASE_EXECUTION
        task.status = Task.STATUS_EXECUTING
        task.execute()
        self.assertEqual(task.phase, Task.PHASE_RECONCILIATION)
        self.assertIsNone(task.result) # No requests, so no result

    def test_reconcile_logic_execution_success(self):
        task = Task(description="Reconcile Success Domain")
        task.phase = Task.PHASE_RECONCILIATION
        task.status = Task.STATUS_EXECUTING # Status before reconcile starts
        task.result = "Execution was successful"
        task.reconcile()
        self.assertEqual(task.status, Task.STATUS_COMPLETED)
        self.assertIsNone(task.phase)

    def test_reconcile_logic_execution_failed(self):
        task = Task(description="Reconcile Failure Domain")
        task.phase = Task.PHASE_RECONCILIATION
        task.status = Task.STATUS_EXECUTING
        task.error_message = "Execution had an error"
        task.reconcile()
        self.assertEqual(task.status, Task.STATUS_FAILED)
        self.assertIsNone(task.phase)

    # --- Test Subtask Logic (In-Memory) ---
    def test_add_subtask_in_memory(self):
        parent_task = Task(description="Parent Task Domain", initiative_id="init_abc")
        subtask = Task(description="Subtask Domain")

        parent_task.add_subtask(subtask)

        self.assertIn(subtask, parent_task.subtasks)
        self.assertEqual(subtask.parent_task_id, parent_task.id)
        self.assertEqual(subtask.initiative_id, parent_task.initiative_id) # Should inherit
        self.assertEqual(parent_task.status, Task.STATUS_PENDING_SUBTASKS)
        self.assertIsNone(parent_task.phase) # Parent phase pauses

    def test_reconcile_logic_all_subtasks_completed(self):
        parent = Task(description="Parent - Subtasks Complete Domain")
        parent.status = Task.STATUS_PENDING_SUBTASKS
        parent.phase = Task.PHASE_RECONCILIATION

        st1 = Task(description="ST1 Domain", status=Task.STATUS_COMPLETED, phase=None)
        st2 = Task(description="ST2 Domain", status=Task.STATUS_COMPLETED, phase=None)
        parent.subtasks = [st1, st2] # Manually set for test, as ModelService would load them

        parent.reconcile()

        self.assertEqual(parent.status, Task.STATUS_PENDING)
        self.assertEqual(parent.phase, Task.PHASE_ASSESSMENT)
        self.assertIsNone(parent.error_message) # Errors should be cleared
        self.assertIn("Subtasks completed successfully", parent.result)


    def test_reconcile_logic_one_subtask_failed(self):
        parent = Task(description="Parent - Subtask Fails Domain")
        parent.status = Task.STATUS_PENDING_SUBTASKS
        parent.phase = Task.PHASE_RECONCILIATION

        st1 = Task(description="ST1 good", status=Task.STATUS_COMPLETED, phase=None)
        st2_fail = Task(description="ST2 bad", status=Task.STATUS_FAILED, phase=None, error_message="Subtask failure")
        parent.subtasks = [st1, st2_fail]

        parent.reconcile()

        self.assertEqual(parent.status, Task.STATUS_FAILED)
        self.assertIsNone(parent.phase)
        self.assertIn("One or more subtasks failed", parent.error_message)

    def test_reconcile_logic_subtasks_not_all_completed(self):
        parent = Task(description="Parent - Subtasks Pending Domain")
        parent.status = Task.STATUS_PENDING_SUBTASKS
        parent.phase = Task.PHASE_RECONCILIATION

        st1 = Task(description="ST1 done", status=Task.STATUS_COMPLETED, phase=None)
        st2_pending = Task(description="ST2 still pending", status=Task.STATUS_PENDING)
        parent.subtasks = [st1, st2_pending]

        parent.reconcile()

        self.assertEqual(parent.status, Task.STATUS_PENDING_SUBTASKS) # Remains
        self.assertEqual(parent.phase, Task.PHASE_RECONCILIATION) # Remains to be checked again

    # --- Test process_current_phase (In-Memory) ---
    def test_process_current_phase_calls_assess(self):
        task = Task(description="Process Assessment Domain")
        task.phase = Task.PHASE_ASSESSMENT
        with patch.object(task, 'assess') as mock_assess:
            task.process_current_phase()
            mock_assess.assert_called_once()

    def test_process_current_phase_calls_execute(self):
        task = Task(description="Process Execution Domain")
        task.status = Task.STATUS_EXECUTING # Must be in executing status
        task.phase = Task.PHASE_EXECUTION
        task.add_request(TogetherAIRequest()) # Needs a request
        with patch.object(task, 'execute') as mock_execute:
            task.process_current_phase()
            mock_execute.assert_called_once()

    def test_process_current_phase_calls_reconcile(self):
        task = Task(description="Process Reconcile Domain")
        task.phase = Task.PHASE_RECONCILIATION
        with patch.object(task, 'reconcile') as mock_reconcile:
            task.process_current_phase()
            mock_reconcile.assert_called_once()

    def test_process_current_phase_pending_subtasks_no_phase_calls_reconcile(self):
        task = Task(description="Process Pending Subtasks No Phase")
        task.status = Task.STATUS_PENDING_SUBTASKS
        task.phase = None # e.g. after add_subtask
        with patch.object(task, 'reconcile') as mock_reconcile:
            task.process_current_phase()
            mock_reconcile.assert_called_once()
            self.assertEqual(task.phase, Task.PHASE_RECONCILIATION) # Phase should be set

    def test_to_pydantic_schema(self):
        task = Task(description="Schema Test", initiative_id="init1", parent_task_id="parent1")
        task.status = Task.STATUS_COMPLETED
        task.phase = None
        task.result = "Schema result"

        sub1 = Task(description="Subtask for Schema")
        task.subtasks.append(sub1)

        schema = task.to_pydantic_schema()

        self.assertIsInstance(schema, TaskSchema)
        self.assertEqual(schema.id, task.id)
        self.assertEqual(schema.description, "Schema Test")
        self.assertEqual(schema.status, Task.STATUS_COMPLETED)
        self.assertIsNone(schema.phase)
        self.assertEqual(schema.result, "Schema result")
        self.assertEqual(schema.initiative_id, "init1")
        self.assertEqual(schema.parent_task_id, "parent1")
        self.assertEqual(schema.created_at, task.created_at)
        self.assertEqual(schema.updated_at, task.updated_at)
        self.assertListEqual(schema.subtask_ids, [sub1.id])


if __name__ == '__main__':
    unittest.main()
