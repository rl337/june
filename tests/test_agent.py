import unittest
from unittest.mock import MagicMock, patch, call
import time
import json # For AI response mocking
from typing import List

from june_agent.agent import Agent
from june_agent.services.in_memory_model_service import InMemoryModelService # Spec for mock_model_service
from june_agent.services.model_service_interface import ModelServiceAbc # For type hint
from june_agent.task import Task as DomainTask
from june_agent.models_v2.pydantic_models import TaskSchema, TaskCreate
from june_agent.request_factory import RequestFactory # New import
from june_agent.testing.mocks import MockRequest    # New import
from june_agent.prompts import get_prompt # Needed if tests simulate prompt fetching for clarity

# Fallback for agent_logs if __main__ is not available (e.g. during isolated test runs)
try:
    from june_agent.__main__ import agent_logs, MAX_LOG_ENTRIES
except ImportError:
    agent_logs: List[str] = []
    MAX_LOG_ENTRIES = 100


class TestAgentWithRequestFactory(unittest.TestCase):
    """
    Test suite for the `Agent` class (`june_agent.agent.Agent`).
    Focuses on testing the agent's core processing loop (`run_single_cycle`),
    its lifecycle management (`start`, `stop`), and its interaction with the
    `ModelServiceAbc` and the `RequestFactory`.
    Uses a mocked `ModelServiceAbc` and a `RequestFactory` configured with `MockRequest`
    to isolate agent logic and simulate various scenarios, including AI-driven
    task assessment outcomes like subtask creation.
    """

    def setUp(self):
        """
        Sets up each test by:
        1. Creating a `MagicMock` for `ModelServiceAbc` (`self.mock_model_service`).
        2. Creating a `MockRequest` instance (`self.mock_api_request_instance`) that
           can be configured per test to simulate specific API/AI responses.
        3. Creating a `RequestFactory` (`self.request_factory`) in "custom" mode,
           configured to always return `self.mock_api_request_instance`. This allows
           tests to control the request objects used by tasks during processing.
        4. Initializing the `Agent` instance with the mocked model service and
           the configured request factory. A short run interval is used for tests.
        """
        self.mock_model_service = MagicMock(spec=ModelServiceAbc)

        self.mock_api_request_instance = MockRequest("Default mock response for agent tests")
        self.request_factory = RequestFactory(
            mode="custom",
            custom_factory_fn=lambda: self.mock_api_request_instance
        )

        self.agent = Agent(
            model_service=self.mock_model_service,
            request_factory=self.request_factory,
            run_interval_seconds=0.1
        )

    def tearDown(self):
        """
        Cleans up after each test by stopping the agent if it's running
        and clearing the global `agent_logs` list to prevent state leakage.
        """
        if self.agent._running:
            self.agent.stop(wait_for_thread=True)
        # Clear the global agent_logs list to ensure test isolation for log assertions.
        while agent_logs: agent_logs.pop()


    def test_agent_initialization(self):
        """Tests that the Agent initializes with the correct model service, request factory, and default state."""
        self.assertFalse(self.agent._running, "Agent should not be running initially.")
        self.assertEqual(self.agent.model_service, self.mock_model_service, "Model service not stored correctly.")
        self.assertEqual(self.agent.request_factory, self.request_factory, "Request factory not stored.")


    @patch('june_agent.agent.threading.Thread')
    def test_agent_start_and_stop(self, MockThread):
        """
        Tests the `start()` and `stop()` methods of the Agent.
        Verifies that `start()` creates and starts a new thread for the agent's loop,
        and that `stop()` signals the loop to terminate and joins the thread.
        """
        mock_thread_instance = MockThread.return_value
        self.agent.start()
        self.assertTrue(self.agent._running, "Agent should be running after start().")
        MockThread.assert_called_once_with(target=self.agent._loop, daemon=True, name="AgentProcessingLoop")
        mock_thread_instance.start.assert_called_once()
        self.agent.stop(wait_for_thread=True)
        self.assertFalse(self.agent._running, "Agent should not be running after stop().")
        mock_thread_instance.join.assert_called_once()

    def test_run_single_cycle_no_tasks(self):
        """
        Tests `run_single_cycle()` when the model service returns no processable tasks.
        Ensures no save operations or significant logging occurs.
        """
        self.mock_model_service.get_processable_tasks_domain_objects.return_value = []
        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()
            self.mock_model_service.save_task_domain_object.assert_not_called()
            mock_log.assert_not_called()

    # --- Tests for Agent's handling of new assessment outcomes ---

    def test_run_single_cycle_processes_task_no_subtasks(self):
        """
        Tests `run_single_cycle` for a task that, after processing its current phase
        (e.g., assessment leading to execution), does not result in subtask suggestions.
        Verifies the task is processed (its `process_current_phase` is called with the factory)
        and saved, but no subtasks are created via the model service.
        """
        task1_domain = DomainTask(description="Task 1 no subtasks")
        task1_domain.id = "task1_no_sub"

        def mock_process_phase_for_execution(task_instance: DomainTask, factory: RequestFactory):
            task_instance.status = DomainTask.STATUS_EXECUTING
            task_instance.phase = DomainTask.PHASE_EXECUTION
            task_instance.suggested_subtasks = None # Ensure no subtasks suggested

        task1_domain.process_current_phase = MagicMock(side_effect=lambda factory_arg: mock_process_phase_for_execution(task1_domain, factory_arg))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task1_domain]

        def mock_save_task(task_obj): # Mock for save_task_domain_object
            return MagicMock(spec=TaskSchema, id=task_obj.id, status=task_obj.status, phase=task_obj.phase, error_message=task_obj.error_message)
        self.mock_model_service.save_task_domain_object.side_effect = mock_save_task

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()

        self.mock_model_service.get_processable_tasks_domain_objects.assert_called_once()
        task1_domain.process_current_phase.assert_called_once_with(self.request_factory)
        self.mock_model_service.create_task.assert_not_called()
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task1_domain)

        mock_log.assert_any_call(f"Task {task1_domain.id} processed and saved. New Status: {DomainTask.STATUS_EXECUTING}, New Phase: {DomainTask.PHASE_EXECUTION}")


    @patch('june_agent.task.get_prompt')
    def test_run_single_cycle_creates_subtasks_when_ai_suggests(self, mock_get_prompt):
        """
        Tests `run_single_cycle` when a task's assessment (via `process_current_phase`
        which calls `Task.assess`) results in subtask suggestions.
        Verifies the Agent attempts to create these subtasks using the model service.
        """
        mock_get_prompt.return_value = "Formatted assessment prompt text"

        parent_task_id = "parent_for_subtasks_agent_test"
        parent_initiative_id = "init_for_agent_subtask_test"

        parent_task_domain = DomainTask(
            description="Parent task to be broken down by AI",
            task_id=parent_task_id,
            initiative_id=parent_initiative_id,
            phase=DomainTask.PHASE_ASSESSMENT
        )
        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [parent_task_domain]

        # Configure the mock AI response that Task.assess() will receive via the factory-provided mock request
        ai_subtask_descs = ["AI Suggested Subtask 1", "AI Suggested Subtask 2"]
        ai_assessment_response = {
            "assessment_outcome": "subtask_breakdown",
            "result_payload": ai_subtask_descs,
        }
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_assessment_response))

        mock_subtask_schema_1 = MagicMock(spec=TaskSchema, id="subtask_id_1")
        mock_subtask_schema_2 = MagicMock(spec=TaskSchema, id="subtask_id_2")
        self.mock_model_service.create_task.side_effect = [mock_subtask_schema_1, mock_subtask_schema_2]

        self.mock_model_service.save_task_domain_object.return_value = MagicMock(spec=TaskSchema)

        self.agent.run_single_cycle()

        # Verify Task.assess (via process_current_phase) used the factory-provided mock request
        self.mock_api_request_instance.execute.assert_called_once_with("Formatted assessment prompt text")

        # Verify Agent's reaction: subtask creation
        self.assertEqual(self.mock_model_service.create_task.call_count, 2)
        expected_calls_create_task = [
            call(TaskCreate(description="AI Suggested Subtask 1", initiative_id=parent_initiative_id, parent_task_id=parent_task_id), initiative_id=parent_initiative_id),
            call(TaskCreate(description="AI Suggested Subtask 2", initiative_id=parent_initiative_id, parent_task_id=parent_task_id), initiative_id=parent_initiative_id)
        ]
        self.mock_model_service.create_task.assert_has_calls(expected_calls_create_task, any_order=False)

        # Verify parent task state after its assess() and Agent's processing
        self.assertEqual(parent_task_domain.status, DomainTask.STATUS_PENDING_SUBTASKS)
        self.assertIsNone(parent_task_domain.suggested_subtasks) # Agent should clear it

        self.mock_model_service.save_task_domain_object.assert_called_once_with(parent_task_domain)


    @patch('june_agent.task.get_prompt')
    def test_run_single_cycle_subtask_creation_fails_if_parent_lacks_initiative_id(self, mock_get_prompt):
        """
        Tests that subtask creation is aborted by the Agent, and parent task is marked FAILED,
        if the parent task is missing `initiative_id` after AI assessment suggests subtasks.
        """
        mock_get_prompt.return_value = "Formatted assessment prompt text"
        parent_task_domain = DomainTask(description="Parent no init_id", task_id="parent_no_init", phase=DomainTask.PHASE_ASSESSMENT)
        parent_task_domain.initiative_id = None # Critical: parent lacks initiative_id

        ai_assessment_response = { # AI suggests subtasks
            "assessment_outcome": "subtask_breakdown",
            "result_payload": ["Subtask X"],
        }
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_assessment_response))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [parent_task_domain]
        self.mock_model_service.save_task_domain_object.return_value = MagicMock(spec=TaskSchema)

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()

        self.mock_api_request_instance.execute.assert_called_once()
        self.mock_model_service.create_task.assert_not_called() # Subtask creation should not be attempted

        self.assertEqual(parent_task_domain.status, DomainTask.STATUS_FAILED)
        self.assertIn("Missing initiative_id; cannot create subtask 'Subtask X'.", parent_task_domain.error_message if parent_task_domain.error_message else "")
        self.mock_model_service.save_task_domain_object.assert_called_once_with(parent_task_domain)
        mock_log.assert_any_call(f"Task {parent_task_domain.id} failed. Error: Missing initiative_id; cannot create subtask 'Subtask X'. ...")


    @patch('june_agent.task.get_prompt')
    def test_run_single_cycle_handles_direct_completion_by_ai(self, mock_get_prompt):
        """
        Tests agent behavior when a task is assessed by AI as 'direct_completion'.
        Ensures no subtasks are created and the task is saved with COMPLETED status.
        """
        mock_get_prompt.return_value = "Formatted assessment prompt"
        task_domain = DomainTask(description="Task for AI direct completion", phase=DomainTask.PHASE_ASSESSMENT)

        ai_assessment_response = {
            "assessment_outcome": "direct_completion",
            "result_payload": "AI completed this directly.",
        }
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_assessment_response))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task_domain]
        self.mock_model_service.save_task_domain_object.return_value = MagicMock(spec=TaskSchema)

        self.agent.run_single_cycle()

        self.mock_api_request_instance.execute.assert_called_once()
        self.assertEqual(task_domain.status, DomainTask.STATUS_COMPLETED)
        self.assertEqual(task_domain.result, "AI completed this directly.")
        self.assertIsNone(task_domain.phase)
        self.mock_model_service.create_task.assert_not_called()
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task_domain)

    @patch('june_agent.task.get_prompt')
    def test_run_single_cycle_handles_ai_proceed_to_execution(self, mock_get_prompt):
        """
        Tests agent behavior when a task is assessed by AI as 'proceed_to_execution'.
        Ensures task state is updated for execution and a request is added by `Task.assess`.
        """
        mock_get_prompt.return_value = "Formatted assessment prompt"
        task_domain = DomainTask(description="Task to proceed to execution", phase=DomainTask.PHASE_ASSESSMENT)

        ai_assessment_response = {"assessment_outcome": "proceed_to_execution"}
        self.mock_api_request_instance.execute = MagicMock(return_value=json.dumps(ai_assessment_response))

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task_domain]
        self.mock_model_service.save_task_domain_object.return_value = MagicMock(spec=TaskSchema)

        self.agent.run_single_cycle()

        self.mock_api_request_instance.execute.assert_called_once_with("Formatted assessment prompt")
        self.assertEqual(task_domain.status, DomainTask.STATUS_EXECUTING)
        self.assertEqual(task_domain.phase, DomainTask.PHASE_EXECUTION)
        self.assertEqual(len(task_domain.requests), 1)
        self.assertIsInstance(task_domain.requests[0], MockRequest) # Factory produces this

        self.mock_model_service.create_task.assert_not_called()
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task_domain)


    def test_run_single_cycle_handles_save_failure(self): # Test general save failure
        """Tests agent's error logging if saving a task fails after processing."""
        task1_domain = DomainTask(description="Task Save Fail")
        task1_domain.id = "task_fail_save"
        # Mock process_current_phase to prevent actual AI call, just simulate it ran.
        task1_domain.process_current_phase = MagicMock()

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task1_domain]
        self.mock_model_service.save_task_domain_object.side_effect = Exception("DB Save Error")
        with patch('june_agent.agent.logger.error') as mock_logger_error:
            self.agent.run_single_cycle()
        task1_domain.process_current_phase.assert_called_once_with(self.request_factory) # Check factory passed
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task1_domain)
        mock_logger_error.assert_any_call(
            f"Agent: Failed to save task {task1_domain.id} after processing/subtask creation: DB Save Error", exc_info=True
        )

    @patch('june_agent.agent.time.sleep')
    @patch.object(Agent, 'run_single_cycle')
    def test_agent_loop_runs_and_stops(self, mock_run_single_cycle, mock_sleep): # Tests loop mechanics
        """Tests the agent's main processing loop runs, calls processing, and can be stopped."""
        self.agent.start()
        self.assertTrue(self.agent._running)
        time.sleep(self.agent.run_interval_seconds * 1.5) # Allow a cycle or two
        self.agent.stop(wait_for_thread=True)
        self.assertFalse(self.agent._running)
        self.assertTrue(mock_run_single_cycle.call_count >= 1)
        self.assertTrue(mock_sleep.call_count >= 1)

if __name__ == '__main__':
    unittest.main()
