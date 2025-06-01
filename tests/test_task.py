import unittest
import os
import time # For time.sleep if needed for timestamp checks
from unittest.mock import patch, MagicMock

from june_agent.db import DatabaseManager
from june_agent.initiative import Initiative # Import Initiative
from june_agent.task import Task
from june_agent.request import APIRequest, TogetherAIRequest # For mocking and type checks

TEST_DB_PATH_TASK = 'test_june_agent_task_unittest.db'

class TestTask(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_PATH_TASK):
            os.remove(TEST_DB_PATH_TASK)

    def setUp(self):
        self.db_manager = DatabaseManager(db_path=TEST_DB_PATH_TASK)
        self.db_manager.connect()
        self.db_manager.create_tables()

        # Mock APIRequest for tests that need it
        self.mock_api_request = MagicMock(spec=APIRequest)
        self.mock_api_request.execute.return_value = "Successful API result"

    def _create_initiative(self, init_id, name="Test Initiative"):
        """Helper to create and save an initiative."""
        initiative = Initiative(initiative_id=init_id, name=name, description="Test desc", db_manager=self.db_manager)
        initiative.save()
        return initiative

    def tearDown(self):
        self.db_manager.close()
        if os.path.exists(TEST_DB_PATH_TASK):
            os.remove(TEST_DB_PATH_TASK)

    def test_task_initialization_and_save(self):
        desc = "Test Task Init"
        task = Task(description=desc, db_manager=self.db_manager)

        self.assertIsNotNone(task.id)
        self.assertEqual(task.description, desc)
        self.assertEqual(task.db_manager, self.db_manager)
        self.assertEqual(task.status, Task.STATUS_PENDING)
        self.assertEqual(task.phase, Task.PHASE_ASSESSMENT) # Default phase
        self.assertIsNone(task.initiative_id)
        self.assertIsNone(task.parent_task_id)
        self.assertIsNotNone(task.created_at)
        self.assertIsNotNone(task.updated_at)

        task.save()
        loaded_task = Task.load(task.id, self.db_manager)
        self.assertIsNotNone(loaded_task)
        self.assertEqual(loaded_task.description, desc)
        self.assertEqual(loaded_task.status, Task.STATUS_PENDING)
        self.assertEqual(loaded_task.phase, Task.PHASE_ASSESSMENT)

    def test_add_request(self):
        task = Task(description="Test Add Request", db_manager=self.db_manager)

        # Valid request
        valid_request = TogetherAIRequest() # Using a concrete type
        task.add_request(valid_request)
        self.assertIn(valid_request, task.requests)
        self.assertEqual(len(task.requests), 1)

        # Invalid request (should log warning, not add)
        with patch('june_agent.task.logger.warning') as mock_log_warn:
            invalid_obj = "not a request"
            task.add_request(invalid_obj)
            self.assertEqual(len(task.requests), 1) # Still 1
            mock_log_warn.assert_called_once()

    # --- Test Phase Methods ---
    def test_assess_phase_simple_execution(self):
        task = Task(description="Assess to Execute", db_manager=self.db_manager)
        task.save() # Save initial state

        # Assess phase should add a request and move to execution
        task.assess() # assess() calls save()

        loaded_task = Task.load(task.id, self.db_manager) # Reload to check persisted state
        self.assertEqual(loaded_task.status, Task.STATUS_EXECUTING)
        self.assertEqual(loaded_task.phase, Task.PHASE_EXECUTION)
        self.assertEqual(len(task.requests), 1) # Check in-memory instance used by assess
        self.assertIsInstance(task.requests[0], TogetherAIRequest)

    def test_assess_phase_no_description_fail(self):
        task = Task(description="", db_manager=self.db_manager) # Empty description
        task.save()

        task.assess()

        loaded_task = Task.load(task.id, self.db_manager)
        self.assertEqual(loaded_task.status, Task.STATUS_FAILED)
        self.assertIsNone(loaded_task.phase)
        self.assertEqual(loaded_task.error_message, "Task description is empty, cannot assess.")

    @patch('june_agent.request.TogetherAIRequest.execute') # Patch the actual execute method
    def test_execute_phase_success(self, mock_execute_method):
        mock_execute_method.return_value = "Mocked API Success"

        task = Task(description="Execute Success", db_manager=self.db_manager)
        # Manually set up for execution phase
        task.phase = Task.PHASE_EXECUTION
        task.status = Task.STATUS_EXECUTING
        task.add_request(TogetherAIRequest()) # Add the request that will be mocked
        task.save()

        task.execute() # execute() calls save()

        loaded_task = Task.load(task.id, self.db_manager)
        self.assertEqual(loaded_task.phase, Task.PHASE_RECONCILIATION)
        self.assertEqual(loaded_task.result, "Mocked API Success")
        mock_execute_method.assert_called_once_with(task.description)

    @patch('june_agent.request.TogetherAIRequest.execute')
    def test_execute_phase_api_returns_error_string(self, mock_execute_method):
        mock_execute_method.return_value = "Error: API problem"

        task = Task(description="Execute API Error String", db_manager=self.db_manager)
        task.phase = Task.PHASE_EXECUTION
        task.status = Task.STATUS_EXECUTING
        task.add_request(TogetherAIRequest())
        task.save()

        task.execute()

        loaded_task = Task.load(task.id, self.db_manager)
        self.assertEqual(loaded_task.phase, Task.PHASE_RECONCILIATION)
        self.assertEqual(loaded_task.result, "Error: API problem") # Result stores what API returns
        self.assertEqual(loaded_task.error_message, "Error: API problem") # Error message also captures this

    @patch('june_agent.request.TogetherAIRequest.execute')
    def test_execute_phase_api_raises_exception(self, mock_execute_method):
        exception_msg = "API crashed badly"
        mock_execute_method.side_effect = Exception(exception_msg)

        task = Task(description="Execute API Exception", db_manager=self.db_manager)
        task.phase = Task.PHASE_EXECUTION
        task.status = Task.STATUS_EXECUTING
        task.add_request(TogetherAIRequest())
        task.save()

        task.execute()

        loaded_task = Task.load(task.id, self.db_manager)
        self.assertEqual(loaded_task.phase, Task.PHASE_RECONCILIATION)
        self.assertIsNone(loaded_task.result)
        self.assertIn(exception_msg, loaded_task.error_message)

    def test_execute_phase_no_requests(self):
        task = Task(description="Execute No Requests", db_manager=self.db_manager)
        task.phase = Task.PHASE_EXECUTION
        task.status = Task.STATUS_EXECUTING
        # Deliberately do not add requests
        task.save()

        task.execute()

        loaded_task = Task.load(task.id, self.db_manager)
        self.assertEqual(loaded_task.phase, Task.PHASE_RECONCILIATION)
        # Depending on logic, status might be completed or failed.
        # Current logic: no requests means it moves to reconciliation, which then decides.
        # Let's assume reconciliation will mark it completed if no error/result.
        # This test primarily checks execute() behavior with no requests.
        self.assertIsNone(loaded_task.result)


    def test_reconcile_phase_execution_success(self):
        task = Task(description="Reconcile Success", db_manager=self.db_manager)
        task.phase = Task.PHASE_RECONCILIATION # Set up for reconcile
        task.status = Task.STATUS_EXECUTING # Status before reconcile starts
        task.result = "Execution was successful"
        task.save()

        task.reconcile() # reconcile() calls save()

        loaded_task = Task.load(task.id, self.db_manager)
        self.assertEqual(loaded_task.status, Task.STATUS_COMPLETED)
        self.assertIsNone(loaded_task.phase) # Phase should be cleared

    def test_reconcile_phase_execution_failed(self):
        task = Task(description="Reconcile Failure", db_manager=self.db_manager)
        task.phase = Task.PHASE_RECONCILIATION
        task.status = Task.STATUS_EXECUTING
        task.error_message = "Execution had an error"
        task.save()

        task.reconcile()

        loaded_task = Task.load(task.id, self.db_manager)
        self.assertEqual(loaded_task.status, Task.STATUS_FAILED)
        self.assertIsNone(loaded_task.phase)

    # --- Test Subtask Logic ---
    def test_add_subtask(self):
        # Create the initiative first
        self._create_initiative(init_id="init_123")
        parent_task = Task(description="Parent Task", db_manager=self.db_manager, initiative_id="init_123")
        parent_task.save()

        subtask_desc = "My Subtask"
        # Create subtask - it needs db_manager. Initiative ID will be set by add_subtask.
        subtask = Task(description=subtask_desc, db_manager=self.db_manager)

        parent_task.add_subtask(subtask) # This saves both parent and subtask

        self.assertIn(subtask, parent_task.subtasks)
        self.assertEqual(subtask.parent_task_id, parent_task.id)
        self.assertEqual(subtask.initiative_id, parent_task.initiative_id)

        loaded_parent = Task.load(parent_task.id, self.db_manager)
        loaded_subtask = Task.load(subtask.id, self.db_manager)

        self.assertEqual(loaded_parent.status, Task.STATUS_PENDING_SUBTASKS)
        self.assertIsNone(loaded_parent.phase) # Parent phase pauses

        self.assertIsNotNone(loaded_subtask)
        self.assertEqual(loaded_subtask.parent_task_id, parent_task.id)
        self.assertEqual(loaded_subtask.status, Task.STATUS_PENDING) # Subtask starts pending
        self.assertEqual(loaded_subtask.phase, Task.PHASE_ASSESSMENT)


    def test_load_subtasks(self):
        parent = Task(description="Parent with Subtasks to Load", db_manager=self.db_manager)
        parent.save()

        st1 = Task(description="ST1", db_manager=self.db_manager, parent_task_id=parent.id)
        st1.save()
        st2 = Task(description="ST2", db_manager=self.db_manager, parent_task_id=parent.id)
        st2.save()

        # Create a new parent instance and load subtasks into it
        parent_loader = Task.load(parent.id, self.db_manager)
        parent_loader.load_subtasks()

        self.assertEqual(len(parent_loader.subtasks), 2)
        subtask_ids_loaded = sorted([st.id for st in parent_loader.subtasks])
        expected_ids = sorted([st1.id, st2.id])
        self.assertListEqual(subtask_ids_loaded, expected_ids)

    def test_reconcile_phase_all_subtasks_completed(self):
        self._create_initiative(init_id="init_sub_complete")
        parent = Task(description="Parent - Subtasks Complete", db_manager=self.db_manager, initiative_id="init_sub_complete")
        parent.status = Task.STATUS_PENDING_SUBTASKS # Set status as if it had subtasks
        parent.phase = Task.PHASE_RECONCILIATION # Ready for reconciliation
        parent.save()

        st1 = Task(description="ST1", db_manager=self.db_manager, parent_task_id=parent.id, initiative_id=parent.initiative_id)
        st1.status = Task.STATUS_COMPLETED # Mark as completed
        st1.phase = None
        st1.save()

        st2 = Task(description="ST2", db_manager=self.db_manager, parent_task_id=parent.id, initiative_id=parent.initiative_id)
        st2.status = Task.STATUS_COMPLETED # Mark as completed
        st2.phase = None
        st2.save()

        # Load parent and its subtasks for reconciliation
        parent_to_reconcile = Task.load(parent.id, self.db_manager)
        parent_to_reconcile.load_subtasks() # Load subtasks from DB
        parent_to_reconcile.phase = Task.PHASE_RECONCILIATION # Ensure phase is set for reconcile call
        parent_to_reconcile.status = Task.STATUS_PENDING_SUBTASKS # Ensure status is correct

        parent_to_reconcile.reconcile()

        loaded_parent = Task.load(parent.id, self.db_manager)
        self.assertEqual(loaded_parent.status, Task.STATUS_PENDING) # Should go back to pending
        self.assertEqual(loaded_parent.phase, Task.PHASE_ASSESSMENT) # To re-assess

    def test_reconcile_phase_one_subtask_failed(self):
        self._create_initiative(init_id="init_sub_fail")
        parent = Task(description="Parent - Subtask Fails", db_manager=self.db_manager, initiative_id="init_sub_fail")
        parent.status = Task.STATUS_PENDING_SUBTASKS
        parent.phase = Task.PHASE_RECONCILIATION
        parent.save()

        st1 = Task(description="ST1 good", db_manager=self.db_manager, parent_task_id=parent.id, initiative_id=parent.initiative_id)
        st1.status = Task.STATUS_COMPLETED
        st1.phase = None
        st1.save()

        st2_fail = Task(description="ST2 bad", db_manager=self.db_manager, parent_task_id=parent.id, initiative_id=parent.initiative_id)
        st2_fail.status = Task.STATUS_FAILED # Mark as FAILED
        st2_fail.phase = None
        st2_fail.error_message = "Subtask failed its job"
        st2_fail.save()

        parent_to_reconcile = Task.load(parent.id, self.db_manager)
        parent_to_reconcile.load_subtasks()
        parent_to_reconcile.phase = Task.PHASE_RECONCILIATION
        parent_to_reconcile.status = Task.STATUS_PENDING_SUBTASKS

        parent_to_reconcile.reconcile()

        loaded_parent = Task.load(parent.id, self.db_manager)
        self.assertEqual(loaded_parent.status, Task.STATUS_FAILED)
        self.assertIsNone(loaded_parent.phase)
        self.assertIn("One or more subtasks failed", loaded_parent.error_message)

    def test_reconcile_phase_subtasks_not_all_completed(self):
        parent = Task(description="Parent - Subtasks Pending", db_manager=self.db_manager)
        parent.status = Task.STATUS_PENDING_SUBTASKS
        parent.phase = Task.PHASE_RECONCILIATION
        parent.save()

        st1 = Task(description="ST1 done", db_manager=self.db_manager, parent_task_id=parent.id)
        st1.status = Task.STATUS_COMPLETED
        st1.save()
        st2_pending = Task(description="ST2 still pending", db_manager=self.db_manager, parent_task_id=parent.id)
        st2_pending.status = Task.STATUS_PENDING # Still pending
        st2_pending.save()

        parent_to_reconcile = Task.load(parent.id, self.db_manager)
        parent_to_reconcile.load_subtasks()
        parent_to_reconcile.phase = Task.PHASE_RECONCILIATION
        parent_to_reconcile.status = Task.STATUS_PENDING_SUBTASKS

        parent_to_reconcile.reconcile() # Should not change parent status yet

        loaded_parent = Task.load(parent.id, self.db_manager)
        self.assertEqual(loaded_parent.status, Task.STATUS_PENDING_SUBTASKS) # Remains unchanged
        self.assertEqual(loaded_parent.phase, Task.PHASE_RECONCILIATION) # Phase also remains

    # --- Test process_current_phase ---
    def test_process_current_phase_assessment(self):
        task = Task(description="Process Assessment", db_manager=self.db_manager)
        task.status = Task.STATUS_PENDING
        task.phase = Task.PHASE_ASSESSMENT
        task.save()

        with patch.object(task, 'assess') as mock_assess:
            task.process_current_phase()
            mock_assess.assert_called_once()

    @patch('june_agent.request.TogetherAIRequest.execute')
    def test_process_current_phase_execution(self, mock_api_exec):
        mock_api_exec.return_value = "Processed execution"
        task = Task(description="Process Execution", db_manager=self.db_manager)
        task.status = Task.STATUS_EXECUTING
        task.phase = Task.PHASE_EXECUTION
        task.add_request(TogetherAIRequest()) # Needs a request to execute
        task.save()

        # Using patch.object on the instance's method directly
        with patch.object(task, 'execute') as mock_execute_method_on_task:
            task.process_current_phase()
            mock_execute_method_on_task.assert_called_once()

    def test_process_current_phase_reconciliation(self):
        task = Task(description="Process Reconcile", db_manager=self.db_manager)
        task.status = Task.STATUS_RECONCILING # Or some other status that leads to reconcile
        task.phase = Task.PHASE_RECONCILIATION
        task.result = "Done"
        task.save()

        with patch.object(task, 'reconcile') as mock_reconcile:
            task.process_current_phase()
            mock_reconcile.assert_called_once()

    # --- Test DB specific load methods ---
    def test_load_all_tasks(self):
        Task(description="T1", db_manager=self.db_manager).save()
        Task(description="T2", db_manager=self.db_manager).save()

        all_tasks = Task.load_all(self.db_manager)
        self.assertEqual(len(all_tasks), 2)

    def test_load_all_tasks_for_initiative(self):
        init_id1 = "init_tasks_1"
        init_id2 = "init_tasks_2"
        # Create initiatives before creating tasks that reference them
        self._create_initiative(init_id=init_id1, name="Initiative 1 for Tasks")
        self._create_initiative(init_id=init_id2, name="Initiative 2 for Tasks")

        Task(description="T1_I1", db_manager=self.db_manager, initiative_id=init_id1).save()
        Task(description="T2_I1", db_manager=self.db_manager, initiative_id=init_id1).save()
        Task(description="T1_I2", db_manager=self.db_manager, initiative_id=init_id2).save()

        tasks_for_init1 = Task.load_all(self.db_manager, initiative_id=init_id1)
        self.assertEqual(len(tasks_for_init1), 2)
        for task in tasks_for_init1:
            self.assertEqual(task.initiative_id, init_id1)

        tasks_for_init2 = Task.load_all(self.db_manager, initiative_id=init_id2)
        self.assertEqual(len(tasks_for_init2), 1)


    def test_task_save_idempotency_and_timestamps(self):
        task = Task(description="Timestamp Test", db_manager=self.db_manager)
        task.save()
        original_id = task.id
        original_created_at = task.created_at
        original_updated_at = task.updated_at

        time.sleep(0.01) # Ensure time moves for updated_at

        task.description = "Updated Timestamp Test"
        task.status = Task.STATUS_COMPLETED
        task.phase = None
        task.save() # This should be an UPDATE

        loaded_task = Task.load(original_id, self.db_manager)
        self.assertIsNotNone(loaded_task)
        self.assertEqual(loaded_task.id, original_id)
        self.assertEqual(loaded_task.description, "Updated Timestamp Test")
        self.assertEqual(loaded_task.status, Task.STATUS_COMPLETED)
        self.assertEqual(loaded_task.created_at, original_created_at, "created_at should not change")
        self.assertNotEqual(loaded_task.updated_at, original_updated_at, "updated_at should change")

        # Verify no new record was created
        count_query = "SELECT COUNT(*) FROM tasks WHERE id = ?"
        count_result = self.db_manager.fetch_one(count_query, (original_id,))
        self.assertEqual(count_result[0], 1, "Should only be one task record with this ID.")


if __name__ == '__main__':
    unittest.main()
