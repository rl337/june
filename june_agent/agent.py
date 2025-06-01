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
    agent_logs: List[str] = [] # Fallback global list for agent activity logs.
    MAX_LOG_ENTRIES = 100 # Fallback max log entries.


class Agent:
    """
    The core processing unit of the June agent.
    It runs a background loop to fetch processable tasks from a model service,
    executes their current phase logic (using domain Task objects),
    and saves their updated state back through the model service.
    """
    def __init__(self, model_service: IModelService, run_interval_seconds: int = 10):
        """
        Initializes the Agent.
        Args:
            model_service: An instance of a class implementing IModelService, used for all data operations.
            run_interval_seconds: The time interval (in seconds) between agent processing cycles.
        """
        self.model_service: IModelService = model_service
        self.run_interval_seconds: int = run_interval_seconds
        self._running: bool = False  # Flag to control the agent's processing loop.
        self._thread: Optional[threading.Thread] = None # Holds the background processing thread.
        logger.info("Agent initialized.")

    def _log_activity(self, message: str):
        """
        Logs a message to both the standard logger and a shared list for UI display.
        Args:
            message: The message string to log.
        """
        log_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"

        # Uses the agent_logs list imported from __main__ (or its fallback).
        # This is a simple way to share logs; more robust IPC could be used in complex scenarios.
        agent_logs.append(log_entry)
        if len(agent_logs) > MAX_LOG_ENTRIES:
            agent_logs.pop(0)

        logger.info(message) # Also log to standard logger


    def run_single_cycle(self) -> None:
        """
        Executes a single processing cycle of the agent.
        Fetches processable tasks, advances their phase using domain object logic,
        and saves their updated state back via the model service.
        This method is designed to be called repeatedly by the agent's main loop.
        """
        logger.debug("Agent: Starting single processing cycle.")
        try:
            # Fetch tasks that are ready for processing as domain objects.
            # The service layer is responsible for determining which tasks are "processable".
            processable_tasks: List[DomainTask] = self.model_service.get_processable_tasks_domain_objects()

            if not processable_tasks:
                # logger.debug("Agent: No tasks requiring active processing in this cycle.")
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
                    # If save failed, the task's state in the persistence layer is unchanged.
                    # It will likely be picked up again in the next cycle if still processable.
                    # More sophisticated error handling could mark the task as error-prone temporarily.
                    pass

        except Exception as e:
            # This catches errors in fetching tasks or other unexpected issues within the cycle.
            logger.error(f"Agent: Critical error during processing cycle: {e}", exc_info=True)

    def _loop(self) -> None:
        """
        The main internal loop executed by the agent's background thread.
        Continuously calls `run_single_cycle` at the defined `run_interval_seconds`.
        The loop can be stopped by setting `self._running` to False.
        """
        logger.info("Agent: Background processing loop started.")
        while self._running:
            start_time = time.monotonic()
            try:
                self.run_single_cycle()
            except Exception as e:
                # This is a safeguard against the loop itself crashing due to an error
                # not caught within run_single_cycle().
                logger.error(f"Agent: Unhandled exception in _loop (run_single_cycle), loop continuing: {e}", exc_info=True)

            # Calculate elapsed time and sleep for the remainder of the interval.
            # This ensures cycles start at consistent intervals.
            elapsed_time = time.monotonic() - start_time
            sleep_duration = self.run_interval_seconds - elapsed_time

            # Responsive sleep: check for stop signal periodically.
            if sleep_duration > 0:
                for _ in range(int(sleep_duration / 0.1) +1): # Check roughly every 100ms
                    if not self._running:
                        break
                    time.sleep(min(0.1, sleep_duration - (_ * 0.1) )) # Sleep remaining part of 100ms or less
                    if (_ * 0.1) >= sleep_duration: # Ensure we don't oversleep
                        break
            elif sleep_duration < 0:
                logger.warning(f"Agent: Processing cycle took longer than interval. Elapsed: {elapsed_time:.2f}s, Interval: {self.run_interval_seconds}s")


        logger.info("Agent: Background processing loop stopped.")

    def start(self) -> None:
        """
        Starts the agent's background processing loop in a new daemon thread.
        If the agent is already running, this method does nothing.
        """
        if self._running:
            logger.warning("Agent: Start called but agent is already running.")
            return

        logger.info("Agent: Starting background processing...")
        self._running = True

        # Create and start a new daemon thread for the processing loop.
        # Daemon threads automatically exit when the main program exits.
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AgentProcessingLoop")
        self._thread.start()
        logger.info("Agent: Background processing started successfully.")

    def stop(self, wait_for_thread: bool = True) -> None:
        """
        Stops the agent's background processing loop.
        Args:
            wait_for_thread: If True, waits for the processing thread to finish
                             its current cycle and exit.
        """
        if not self._running:
            logger.warning("Agent: Stop called but agent is not running.")
            return

        logger.info("Agent: Stopping background processing...")
        self._running = False # Signal the loop to stop.

        if self._thread and self._thread.is_alive() and wait_for_thread:
            logger.info("Agent: Waiting for processing thread to complete current cycle...")
            # Wait slightly longer than the run interval to allow a cycle to finish.
            self._thread.join(timeout=self.run_interval_seconds + 2)
            if self._thread.is_alive():
                logger.warning("Agent: Processing thread did not finish in the expected time.")

        self._thread = None # Clear the thread reference.
        logger.info("Agent: Background processing stopped successfully.")
