import unittest
from unittest.mock import MagicMock, patch, call
import time
from typing import List # Added for agent_logs fallback

from june_agent.agent import Agent
from june_agent.services.in_memory_model_service import InMemoryModelService
from june_agent.task import Task as DomainTask
from june_agent.models_v2.pydantic_models import TaskSchema, TaskCreate


try:
    from june_agent.__main__ import agent_logs, MAX_LOG_ENTRIES
except ImportError:
    agent_logs: List[str] = []
    MAX_LOG_ENTRIES = 100


class TestAgent(unittest.TestCase):

    def setUp(self):
        self.mock_model_service = MagicMock(spec=InMemoryModelService)
        self.agent = Agent(model_service=self.mock_model_service, run_interval_seconds=0.1)

    def tearDown(self):
        if self.agent._running:
            self.agent.stop(wait_for_thread=True)

    def test_agent_initialization(self):
        self.assertFalse(self.agent._running)
        self.assertEqual(self.agent.model_service, self.mock_model_service)

    @patch('june_agent.agent.threading.Thread')
    def test_agent_start_and_stop(self, MockThread):
        mock_thread_instance = MockThread.return_value

        self.agent.start()
        self.assertTrue(self.agent._running)
        MockThread.assert_called_once_with(target=self.agent._loop, daemon=True, name="AgentProcessingLoop")
        mock_thread_instance.start.assert_called_once()

        self.agent.stop(wait_for_thread=True)
        self.assertFalse(self.agent._running)
        mock_thread_instance.join.assert_called_once()

    def test_run_single_cycle_no_tasks(self):
        self.mock_model_service.get_processable_tasks_domain_objects.return_value = []

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()
            self.mock_model_service.save_task_domain_object.assert_not_called()
            mock_log.assert_not_called()

    def test_run_single_cycle_processes_task_no_subtasks(self): # Renamed and adapted
        task1_domain = DomainTask(description="Task 1 no subtasks")
        task1_domain.id = "task1_no_sub"

        def mock_process_phase_for_execution(task_instance): # Simulate assessment leading to execution
            task_instance.status = DomainTask.STATUS_EXECUTING
            task_instance.phase = DomainTask.PHASE_EXECUTION

        task1_domain.process_current_phase = MagicMock(side_effect=lambda: mock_process_phase_for_execution(task1_domain))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task1_domain]

        def mock_save_task(task_obj):
            return MagicMock(spec=TaskSchema, id=task_obj.id, status=task_obj.status, phase=task_obj.phase, error_message=task_obj.error_message)
        self.mock_model_service.save_task_domain_object.side_effect = mock_save_task

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()

        self.mock_model_service.get_processable_tasks_domain_objects.assert_called_once()
        task1_domain.process_current_phase.assert_called_once()
        self.mock_model_service.create_task.assert_not_called()
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task1_domain)

        mock_log.assert_any_call(f"Task {task1_domain.id} processed and saved. New Status: {DomainTask.STATUS_EXECUTING}, New Phase: {DomainTask.PHASE_EXECUTION}")


    def test_run_single_cycle_creates_subtasks_when_suggested(self):
        parent_task_id = "parent_task_for_subtasks"
        parent_initiative_id = "init_for_parent_with_subtasks"

        parent_task_domain = DomainTask(
            description="Parent task that will suggest subtasks",
            task_id=parent_task_id,
            initiative_id=parent_initiative_id
        )

        def mock_process_phase_for_subtasks(task_instance): # Simulate assessment outcome
            task_instance.status = DomainTask.STATUS_PENDING_SUBTASKS
            task_instance.suggested_subtasks = ["Subtask Alpha", "Subtask Beta"]
            task_instance.phase = None

        parent_task_domain.process_current_phase = MagicMock(side_effect=lambda: mock_process_phase_for_subtasks(parent_task_domain))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [parent_task_domain]

        mock_subtask_schema_alpha = MagicMock(spec=TaskSchema, id="sub_alpha_id")
        mock_subtask_schema_beta = MagicMock(spec=TaskSchema, id="sub_beta_id")
        self.mock_model_service.create_task.side_effect = [mock_subtask_schema_alpha, mock_subtask_schema_beta]

        def mock_save_parent(task_obj):
            return MagicMock(spec=TaskSchema, id=task_obj.id, status=task_obj.status, phase=task_obj.phase, error_message=task_obj.error_message)
        self.mock_model_service.save_task_domain_object.side_effect = mock_save_parent

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()

        parent_task_domain.process_current_phase.assert_called_once()
        self.assertEqual(self.mock_model_service.create_task.call_count, 2)
        expected_calls_create_task = [
            call(TaskCreate(description="Subtask Alpha", initiative_id=parent_initiative_id, parent_task_id=parent_task_id), initiative_id=parent_initiative_id),
            call(TaskCreate(description="Subtask Beta", initiative_id=parent_initiative_id, parent_task_id=parent_task_id), initiative_id=parent_initiative_id)
        ]
        self.mock_model_service.create_task.assert_has_calls(expected_calls_create_task, any_order=False)
        self.assertIsNone(parent_task_domain.suggested_subtasks)
        self.mock_model_service.save_task_domain_object.assert_called_once_with(parent_task_domain)
        self.assertEqual(parent_task_domain.status, DomainTask.STATUS_PENDING_SUBTASKS)
        mock_log.assert_any_call(f"Task {parent_task_id} requires subtask breakdown. Suggested subtasks: 2")


    def test_run_single_cycle_subtask_creation_fails_if_parent_lacks_initiative_id(self):
        parent_task_domain = DomainTask(description="Parent no init_id", task_id="parent_no_init")
        parent_task_domain.initiative_id = None

        def mock_process_phase_for_subtasks_no_init(task_instance): # Simulate assessment outcome
            task_instance.status = DomainTask.STATUS_PENDING_SUBTASKS
            task_instance.suggested_subtasks = ["Subtask X"]
            task_instance.phase = None

        parent_task_domain.process_current_phase = MagicMock(side_effect=lambda: mock_process_phase_for_subtasks_no_init(parent_task_domain))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [parent_task_domain]
        self.mock_model_service.save_task_domain_object.return_value = MagicMock(spec=TaskSchema)

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()

        parent_task_domain.process_current_phase.assert_called_once()
        self.mock_model_service.create_task.assert_not_called()
        self.assertEqual(parent_task_domain.status, DomainTask.STATUS_FAILED)
        self.assertIn("Missing initiative_id, cannot create subtask", parent_task_domain.error_message if parent_task_domain.error_message else "")
        self.mock_model_service.save_task_domain_object.assert_called_once_with(parent_task_domain)
        mock_log.assert_any_call(f"Task {parent_task_domain.id} failed. Error: Missing initiative_id; cannot create subtask 'Subtask X'. ...")


    def test_run_single_cycle_task_assessed_direct_completion(self):
        task_domain = DomainTask(description="Task direct complete", task_id="task_direct")

        def mock_process_phase_direct_complete(task_instance): # Simulate assessment outcome
            task_instance.status = DomainTask.STATUS_COMPLETED
            task_instance.result = "Done by AI assessment"
            task_instance.phase = None
            task_instance.suggested_subtasks = None

        task_domain.process_current_phase = MagicMock(side_effect=lambda: mock_process_phase_direct_complete(task_domain))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task_domain]
        self.mock_model_service.save_task_domain_object.return_value = MagicMock(
            spec=TaskSchema, id=task_domain.id, status=task_domain.status, phase=task_domain.phase, error_message=None
        )

        self.agent.run_single_cycle()

        task_domain.process_current_phase.assert_called_once()
        self.mock_model_service.create_task.assert_not_called()
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task_domain)
        self.assertEqual(task_domain.status, DomainTask.STATUS_COMPLETED)


    def test_run_single_cycle_handles_save_failure(self): # Copied, still relevant
        task1_domain = DomainTask(description="Task Save Fail")
        task1_domain.id = "task_fail_save"
        task1_domain.process_current_phase = MagicMock()
        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task1_domain]
        self.mock_model_service.save_task_domain_object.side_effect = Exception("DB Save Error")
        with patch('june_agent.agent.logger.error') as mock_logger_error:
            self.agent.run_single_cycle()
        task1_domain.process_current_phase.assert_called_once()
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task1_domain)
        mock_logger_error.assert_any_call(
            f"Agent: Failed to save task {task1_domain.id} after processing: DB Save Error", exc_info=True
        )

    @patch('june_agent.agent.time.sleep')
    @patch.object(Agent, 'run_single_cycle')
    def test_agent_loop_runs_and_stops(self, mock_run_single_cycle, mock_sleep): # Copied, still relevant
        self.agent.start()
        self.assertTrue(self.agent._running)
        time.sleep(self.agent.run_interval_seconds * 2.5)
        self.agent.stop(wait_for_thread=True)
        self.assertFalse(self.agent._running)
        self.assertTrue(mock_run_single_cycle.call_count > 0)
        self.assertTrue(mock_sleep.call_count > 0)

if __name__ == '__main__':
    unittest.main()
