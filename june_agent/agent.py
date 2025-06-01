import logging
import threading
import time
from typing import List, Optional

from june_agent.services.model_service_interface import IModelService
from june_agent.task import Task as DomainTask # The pure domain object

logger = logging.getLogger(__name__)

# Attempt to import agent_logs and MAX_LOG_ENTRIES from __main__
# This creates a dependency that might need to be refactored later
# if agent_logs are to be managed by the Agent instance itself.
try:
    from june_agent.__main__ import agent_logs, MAX_LOG_ENTRIES
except ImportError:
    # Fallback if __main__ is not structured as expected or during tests
    logger.warning("Could not import agent_logs from __main__. Using local fallback for Agent logs.")
    agent_logs: List[str] = []
    MAX_LOG_ENTRIES = 100


class Agent:
    def __init__(self, model_service: IModelService, run_interval_seconds: int = 10):
        self.model_service: IModelService = model_service
        self.run_interval_seconds: int = run_interval_seconds
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        logger.info("Agent initialized.")

    def _log_activity(self, message: str):
        """Helper to add entries to the agent_logs list."""
        log_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"

        # Use the imported (or fallback) agent_logs
        agent_logs.append(log_entry)
        if len(agent_logs) > MAX_LOG_ENTRIES:
            agent_logs.pop(0)

        logger.info(message) # Also log to standard logger


    def run_single_cycle(self) -> None:
        """
        Executes a single processing cycle of the agent.
        Fetches processable tasks, advances their phase, and saves changes.
        """
        logger.debug("Agent: Starting single processing cycle.")
        try:
            # Get domain task objects that need processing
            processable_tasks: List[DomainTask] = self.model_service.get_processable_tasks_domain_objects()

            if not processable_tasks:
                # logger.debug("Agent: No tasks found requiring active processing in this cycle.")
                return

            self._log_activity(f"Agent: Found {len(processable_tasks)} tasks for processing.")

            for task in processable_tasks:
                task_id_for_log = task.id
                original_status_for_log = task.status
                original_phase_for_log = task.phase

                self._log_activity(f"Considering task: {task_id_for_log} - '{task.description[:30]}' (Status: {original_status_for_log}, Phase: {original_phase_for_log})")

                # Process the current phase (modifies task in-memory)
                task.process_current_phase()

                # Persist changes using the model service
                try:
                    # save_task_domain_object should handle both create and update based on existence
                    updated_task_schema = self.model_service.save_task_domain_object(task)
                    self._log_activity(
                        f"Task {updated_task_schema.id} processed and saved. "
                        f"New Status: {updated_task_schema.status}, New Phase: {updated_task_schema.phase}"
                    )
                    if updated_task_schema.status == DomainTask.STATUS_FAILED: # Use DomainTask for constants
                        self._log_activity(f"Task {updated_task_schema.id} failed. Error: {str(updated_task_schema.error_message)[:100]}...")
                except Exception as e:
                    logger.error(f"Agent: Failed to save task {task_id_for_log} after processing: {e}", exc_info=True)
                    # Task state might be inconsistent in DB if save failed after in-memory change.
                    # The task will likely be picked up again if its state in DB is still 'processable'.

        except Exception as e:
            logger.error(f"Agent: Critical error in processing cycle: {e}", exc_info=True)

    def _loop(self) -> None:
        """The main internal loop executed by the agent's thread."""
        logger.info("Agent: Background processing loop started.")
        while self._running:
            try:
                self.run_single_cycle()
            except Exception as e:
                # Catch all exceptions within the run_single_cycle call itself if any slip through,
                # to prevent the loop from crashing.
                logger.error(f"Agent: Unhandled exception in run_single_cycle, loop continuing: {e}", exc_info=True)

            # Wait for the run interval or until stop is requested.
            # This uses a loop with a shorter sleep to make stop() more responsive.
            for _ in range(int(self.run_interval_seconds * 10)): # Check every 100ms, ensure int for range
                if not self._running:
                    break
                time.sleep(0.1)
        logger.info("Agent: Background processing loop stopped.")

    def start(self) -> None:
        """Starts the agent's background processing loop in a new thread."""
        if self._running:
            logger.warning("Agent: Start called but agent is already running.")
            return

        logger.info("Agent: Starting...")
        self._running = True

        self._thread = threading.Thread(target=self._loop, daemon=True, name="AgentProcessingLoop")
        self._thread.start()
        logger.info("Agent: Started successfully.")

    def stop(self, wait_for_thread: bool = True) -> None:
        """Stops the agent's background processing loop."""
        if not self._running:
            logger.warning("Agent: Stop called but agent is not running.")
            return

        logger.info("Agent: Stopping...")
        self._running = False # Signal the loop to stop
        if self._thread and self._thread.is_alive() and wait_for_thread:
            logger.info("Agent: Waiting for processing thread to finish...")
            self._thread.join(timeout=self.run_interval_seconds + 2) # Wait a bit longer than interval
            if self._thread.is_alive():
                logger.warning("Agent: Processing thread did not finish in time.")
        self._thread = None
        logger.info("Agent: Stopped successfully.")
