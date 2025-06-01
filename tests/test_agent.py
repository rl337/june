import unittest
from unittest.mock import MagicMock, patch, call # call for checking multiple calls with different args
import time # For thread join timeouts and checking time-based logic if any

from june_agent.agent import Agent
from june_agent.services.in_memory_model_service import InMemoryModelService
from june_agent.task import Task as DomainTask # The pure domain object
from june_agent.models_v2.pydantic_models import TaskSchema # For return type of save_task_domain_object

# It's useful to have agent_logs accessible for some tests,
# or mock the Agent._log_activity method.
# If agent.py's fallback for agent_logs is used, we can inspect that.
# For cleaner tests, mock _log_activity.

class TestAgent(unittest.TestCase):

    def setUp(self):
        self.mock_model_service = MagicMock(spec=InMemoryModelService) # Use MagicMock for spec
        self.agent = Agent(model_service=self.mock_model_service, run_interval_seconds=0.1) # Short interval for tests

    def tearDown(self):
        if self.agent._running:
            self.agent.stop(wait_for_thread=True)

    def test_agent_initialization(self):
        self.assertFalse(self.agent._running)
        self.assertEqual(self.agent.model_service, self.mock_model_service)

    @patch('june_agent.agent.threading.Thread') # Patch the Thread class used by Agent
    def test_agent_start_and_stop(self, MockThread):
        mock_thread_instance = MockThread.return_value # Get the instance created by Agent

        self.agent.start()
        self.assertTrue(self.agent._running)
        MockThread.assert_called_once_with(target=self.agent._loop, daemon=True, name="AgentProcessingLoop")
        mock_thread_instance.start.assert_called_once()

        self.agent.stop(wait_for_thread=True)
        self.assertFalse(self.agent._running)
        mock_thread_instance.join.assert_called_once() # Check if join was called

    def test_run_single_cycle_no_tasks(self):
        self.mock_model_service.get_processable_tasks_domain_objects.return_value = []

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()
            # Check that no processing logs were made beyond initial "found 0 tasks" if that's logged.
            # Current Agent._log_activity is called *after* checking if processable_tasks is empty.
            # So, if it's empty, the "Found X tasks" log isn't made.
            # Let's check that save_task_domain_object was not called.
            self.mock_model_service.save_task_domain_object.assert_not_called()
            # And that no "Considering task" log was made
            # Example: mock_log.assert_not_any_call(unittest.mock.ANY(containing="Considering task")) - needs custom matcher

            # Simpler check: count calls to _log_activity. If no tasks, it should be minimal.
            # Based on current agent.py, if no tasks, _log_activity isn't called within run_single_cycle.
            # So, if we don't mock it, agent_logs list would be empty from this cycle.
            # If we mock it, its call_count should be 0.
            mock_log.assert_not_called()


    def test_run_single_cycle_processes_and_saves_tasks(self):
        # Create mock domain tasks
        task1_domain = DomainTask(description="Task 1")
        task1_domain.id = "task1"
        task2_domain = DomainTask(description="Task 2")
        task2_domain.id = "task2"

        # Mock the process_current_phase method on these specific instances
        task1_domain.process_current_phase = MagicMock()
        task2_domain.process_current_phase = MagicMock()

        # Model service returns these tasks
        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task1_domain, task2_domain]

        # Mock save_task_domain_object to return a TaskSchema-like object
        # We need to ensure the returned object has id, status, phase, error_message for logging
        def mock_save_task(task_obj):
            # Simulate that save returns a schema-like object based on the task passed to it
            return MagicMock(
                spec=TaskSchema,
                id=task_obj.id,
                status=task_obj.status,
                phase=task_obj.phase,
                error_message=task_obj.error_message
            )
        self.mock_model_service.save_task_domain_object.side_effect = mock_save_task

        with patch.object(self.agent, '_log_activity') as mock_log:
            self.agent.run_single_cycle()

        # Assertions
        self.mock_model_service.get_processable_tasks_domain_objects.assert_called_once()

        # Check that process_current_phase was called on each task
        task1_domain.process_current_phase.assert_called_once()
        task2_domain.process_current_phase.assert_called_once()

        # Check that save_task_domain_object was called for each task
        self.assertEqual(self.mock_model_service.save_task_domain_object.call_count, 2)
        self.mock_model_service.save_task_domain_object.assert_any_call(task1_domain)
        self.mock_model_service.save_task_domain_object.assert_any_call(task2_domain)

        # Check logging calls (simplified)
        # Found tasks + Considering task1 + Processed task1 + Considering task2 + Processed task2 = 5 calls
        self.assertEqual(mock_log.call_count, 5)
        mock_log.assert_any_call("Agent: Found 2 tasks for processing.")
        mock_log.assert_any_call(f"Considering task: {task1_domain.id} - '{task1_domain.description[:30]}' (Status: {task1_domain.status}, Phase: {task1_domain.phase})")
        mock_log.assert_any_call(f"Task {task1_domain.id} processed and saved. New Status: {task1_domain.status}, New Phase: {task1_domain.phase}")


    def test_run_single_cycle_handles_save_failure(self):
        task1_domain = DomainTask(description="Task Save Fail")
        task1_domain.id = "task_fail_save"
        task1_domain.process_current_phase = MagicMock()

        self.mock_model_service.get_processable_tasks_domain_objects.return_value = [task1_domain]
        self.mock_model_service.save_task_domain_object.side_effect = Exception("DB Save Error")

        with patch.object(self.agent, '_log_activity') as mock_log_activity, \
             patch('june_agent.agent.logger.error') as mock_logger_error: # Patch module logger

            self.agent.run_single_cycle()

        task1_domain.process_current_phase.assert_called_once()
        self.mock_model_service.save_task_domain_object.assert_called_once_with(task1_domain)

        # Check that the error during save was logged via logger.error
        mock_logger_error.assert_any_call(
            f"Agent: Failed to save task {task1_domain.id} after processing: DB Save Error",
            exc_info=True
        )


    @patch('june_agent.agent.time.sleep') # To make the loop run fast for test
    @patch.object(Agent, 'run_single_cycle') # Mock the actual work method
    def test_agent_loop_runs_and_stops(self, mock_run_single_cycle, mock_sleep):
        self.agent.start() # Starts the thread with _loop
        self.assertTrue(self.agent._running)

        # Give the loop a moment to run a few times
        # Check that run_single_cycle was called.
        # This needs careful handling of timing or specific mock assertions.
        # Let's wait for a short time and check call count.

        # Allow loop to run for a very short period
        # The effectiveness of this depends on how quickly the thread starts
        # and how many times run_single_cycle can be called by the mock.
        # The loop has its own time.sleep(0.1) for responsiveness.

        # Wait for a few cycles based on run_interval_seconds
        # Ensure it's called at least once
        time.sleep(self.agent.run_interval_seconds * 2.5) # Wait for ~2 cycles

        self.agent.stop(wait_for_thread=True)
        self.assertFalse(self.agent._running)

        # Assert that run_single_cycle was called multiple times
        self.assertTrue(mock_run_single_cycle.call_count > 0)
        # Assert that time.sleep was called inside the loop (mocked at agent.time.sleep)
        self.assertTrue(mock_sleep.call_count > 0)


if __name__ == '__main__':
    unittest.main()
