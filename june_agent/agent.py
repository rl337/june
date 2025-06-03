import logging
import threading
import time
from typing import List, Optional

from june_agent.services.model_service_interface import ModelServiceAbc
from june_agent.task import Task as DomainTask
# Import TaskCreate for creating subtasks
from june_agent.models_v2.pydantic_models import TaskCreate, TaskSchema
from june_agent.request_factory import RequestFactory # Import RequestFactory

logger = logging.getLogger(__name__)

try:
    from june_agent.__main__ import agent_logs, MAX_LOG_ENTRIES
except ImportError:
    logger.warning("Could not import agent_logs from __main__. Using local fallback for Agent logs.")
    agent_logs: List[str] = []
    MAX_LOG_ENTRIES = 100


class Agent:
    """
    The core processing unit of the June agent.
    It runs a background loop to fetch processable tasks from a model service,
    executes their current phase logic (using domain Task objects),
    and saves their updated state back through the model service.
    It also handles creation of subtasks if suggested by task assessment.
    A `RequestFactory` is used to create `APIRequest` instances for tasks.
    """
    def __init__(self,
                 model_service: ModelServiceAbc,
                 request_factory: RequestFactory,
                 run_interval_seconds: int = 10):
        """
        Initializes the Agent.

        Args:
            model_service: An instance of a class implementing `ModelServiceAbc`,
                           used for all data persistence and retrieval operations.
            request_factory: An instance of `RequestFactory`, used by tasks to obtain
                             `APIRequest` objects for external API calls (e.g., to AI models).
            run_interval_seconds: The time interval (in seconds) between the start
                                  of each agent processing cycle.
        """
        self.model_service: ModelServiceAbc = model_service
        self.request_factory: RequestFactory = request_factory
        self.run_interval_seconds: int = run_interval_seconds
        self._running: bool = False  # Controls the execution of the agent's main loop.
        self._thread: Optional[threading.Thread] = None # Stores the agent's background processing thread.
        logger.info(f"Agent initialized with ModelService: {type(model_service).__name__} and RequestFactory: {type(request_factory).__name__}.")

    def _log_activity(self, message: str) -> None:
        """
        Logs a message to the standard Python logger and appends it to a shared
        `agent_logs` list (intended for UI display). Manages log list size.

        Args:
            message: The message to log.
        """
        log_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"

        # This relies on agent_logs being a globally accessible list (imported or fallback).
        # Consider making agent_logs an instance variable or passed in if more encapsulation is desired.
        agent_logs.append(log_entry)
        if len(agent_logs) > MAX_LOG_ENTRIES:
            agent_logs.pop(0) # Keep the list size bounded.

        logger.info(message)


    def run_single_cycle(self) -> None:
        """
        Executes one full processing cycle of the agent. This involves:
        1. Fetching all tasks deemed "processable" from the model service.
        2. For each processable task (domain object):
           a. Instructing the task to process its current phase (e.g., assess, execute, reconcile).
              The `RequestFactory` is passed to the task for this purpose.
           b. If the task's assessment results in suggested subtasks:
              i. The agent creates these subtasks via the model service.
              ii. The parent task's `suggested_subtasks` list is cleared.
           c. Saving the updated state of the original task (and any newly created subtasks,
              which are saved by the model service during their creation) back to persistence.
        Includes error handling for each step to make the cycle resilient.
        """
        logger.debug("Agent: Starting single processing cycle.")
        try:
            # 1. Fetch processable tasks as domain objects.
            # The model service is responsible for the query logic to find these.
            processable_tasks: List[DomainTask] = self.model_service.get_processable_tasks_domain_objects()

            if not processable_tasks:
                # logger.debug("Agent: No tasks found requiring active processing in this cycle.") # Can be noisy
                return

            self._log_activity(f"Agent: Found {len(processable_tasks)} tasks for processing.")

            for task in processable_tasks:
                task_id_for_log = task.id
                original_status_for_log = task.status
                original_phase_for_log = task.phase

                self._log_activity(
                    f"Considering task: {task_id_for_log} - '{task.description[:30]}' "
                    f"(Status: {original_status_for_log}, Phase: {original_phase_for_log})"
                )

                # Pass request_factory to process_current_phase, which will pass it to assess/execute
                task.process_current_phase(self.request_factory)

                # After processing, check if assessment resulted in subtask suggestions
                if task.status == DomainTask.STATUS_PENDING_SUBTASKS and task.suggested_subtasks:
                    self._log_activity(
                        f"Task {task.id} requires subtask breakdown. "
                        f"Suggested subtasks: {len(task.suggested_subtasks)}"
                    )
                return

            self._log_activity(f"Agent: Found {len(processable_tasks)} tasks for processing.")

            for task in processable_tasks: # Iterate over DomainTask instances
                task_id_for_log = task.id
                original_status_for_log = task.status
                original_phase_for_log = task.phase

                self._log_activity(
                    f"Considering task: {task_id_for_log} - '{task.description[:30]}' "
                    f"(Status: {original_status_for_log}, Phase: {original_phase_for_log})"
                )

                # 2a. Instruct the task to process its current phase.
                # This call modifies the task object in-memory.
                # The RequestFactory is passed for the task to create APIRequest objects if needed (e.g., in assess or execute).
                task.process_current_phase(self.request_factory)

                # 2b. Handle subtask creation if assessment suggested it.
                if task.status == DomainTask.STATUS_PENDING_SUBTASKS and task.suggested_subtasks:
                    self._log_activity(
                        f"Task {task.id} requires subtask breakdown by AI assessment. "
                        f"Number of suggested subtasks: {len(task.suggested_subtasks)}"
                    )

                    for sub_desc in task.suggested_subtasks:
                        if not task.initiative_id: # Should always have initiative_id if it's a persisted task.
                            logger.error(
                                f"Parent task {task.id} is missing initiative_id. "
                                f"Cannot create subtask with description: '{sub_desc}'. "
                                "Parent task will be marked as FAILED."
                            )
                            task.status = DomainTask.STATUS_FAILED
                            task.error_message = (task.error_message or "") + \
                                                 f"Missing initiative_id; cannot create subtask '{sub_desc}'. "
                            break # Stop trying to create more subtasks for this failed parent.

                        # Prepare data for the new subtask using Pydantic model for validation.
                        subtask_create_dto = TaskCreate(
                            description=sub_desc,
                            initiative_id=task.initiative_id, # Subtasks inherit initiative from parent.
                            parent_task_id=task.id,          # Link to this parent task.
                            # Default status/phase (e.g., pending/assessment) are set by TaskCreate
                            # or later by the ORM if not specified in TaskCreate.
                        )
                        try:
                            # Use the model service to create the subtask in persistence.
                            created_sub_schema = self.model_service.create_task(
                                subtask_create_dto,
                                initiative_id=task.initiative_id # Passed separately to service method.
                            )
                            self._log_activity(f"Successfully created subtask {created_sub_schema.id} ('{sub_desc[:30]}...') for parent {task.id}.")
                        except Exception as e_sub:
                            logger.error(f"Failed to create subtask '{sub_desc}' for parent {task.id} via model service: {e_sub}", exc_info=True)
                            # Append error to parent task's error message.
                            task.error_message = (task.error_message or "") + \
                                                 f"Failed to create subtask '{sub_desc}'. "
                            # Depending on desired robustness, could mark parent as FAILED here,
                            # or allow it to be saved as PENDING_SUBTASKS with an error message,
                            # for potential retry or manual review. For now, just log and append error.

                    task.suggested_subtasks = None # Clear suggestions after processing.

                # 2c. Save the updated task (parent task) state.
                try:
                    updated_task_schema = self.model_service.save_task_domain_object(task)
                    self._log_activity(
                        f"Task {updated_task_schema.id} processed and saved. "
                        f"New Status: {updated_task_schema.status}, New Phase: {updated_task_schema.phase}"
                    )
                    if updated_task_schema.status == DomainTask.STATUS_FAILED:
                        self._log_activity(
                            f"Task {updated_task_schema.id} failed. Error: {str(updated_task_schema.error_message)[:100]}..."
                        )
                except Exception as e:
                    logger.error(f"Agent: Failed to save task {task_id_for_log} after processing/subtask creation: {e}", exc_info=True)
                    # Task state in persistence might be stale if save fails.
                    # It will likely be picked up again in the next cycle if its persisted state is still 'processable'.
                    pass # Continue to the next task.

        except Exception as e:
            logger.error(f"Agent: Critical error occurred in processing cycle: {e}", exc_info=True)

    def _loop(self) -> None:
        """
        The main internal loop that drives the agent's operations.
        It periodically calls `run_single_cycle()` and includes logic for
        responsive stopping and consistent cycle intervals.
        """
        logger.info("Agent: Background processing loop started.")
        while self._running:
            start_time = time.monotonic() # For precise interval timing.
            try:
                self.run_single_cycle()
            except Exception as e:
                # Safeguard: Catch any unexpected errors from run_single_cycle to prevent the loop itself from crashing.
                logger.error(f"Agent: Unhandled critical exception in _loop (during run_single_cycle), loop will continue: {e}", exc_info=True)

            elapsed_time = time.monotonic() - start_time
            sleep_duration = self.run_interval_seconds - elapsed_time

            if sleep_duration > 0:
                # Sleep responsively: break sleep into smaller chunks to check `_running` flag.
                # This allows the agent to stop more quickly if requested.
                for _ in range(int(sleep_duration / 0.1) +1): # Check roughly every 100ms
                    if not self._running: break # Exit sleep early if stop signal received.

                    # Calculate remaining sleep for this sub-interval to avoid oversleeping
                    # if sleep_duration is not a perfect multiple of 0.1.
                    time_slept_this_cycle = _ * 0.1
                    remaining_sub_sleep = min(0.1, sleep_duration - time_slept_this_cycle)

                    if remaining_sub_sleep <=0: break # Avoid negative or zero sleep.
                    time.sleep(current_loop_sleep)
                    if time_slept_this_cycle + current_loop_sleep >= sleep_duration: break
            elif sleep_duration < 0:
                # Log if a cycle takes longer than the configured interval.
                logger.warning(f"Agent: Processing cycle duration ({elapsed_time:.2f}s) exceeded run interval ({self.run_interval_seconds}s).")
        logger.info("Agent: Background processing loop stopped.")

    def start(self) -> None:
        """
        Starts the agent's background processing loop in a new daemon thread.
        If the agent is already running, this method logs a warning and returns.
        """
        if self._running:
            logger.warning("Agent: Start called, but agent is already running.")
            return

        logger.info("Agent: Starting background processing...")
        self._running = True

        # Daemon threads automatically exit when the main program (e.g., Flask server) exits.
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AgentProcessingLoop")
        self._thread.start()
        logger.info("Agent: Background processing started successfully.")

    def stop(self, wait_for_thread: bool = True) -> None:
        """
        Signals the agent's background processing loop to stop and optionally waits
        for the thread to complete its current cycle and exit.

        Args:
            wait_for_thread: If True (default), this method will block until the
                             agent's processing thread has joined, or a timeout occurs.
        """
        if not self._running:
            logger.warning("Agent: Stop called, but agent is not currently running.")
            return

        logger.info("Agent: Stopping background processing...")
        self._running = False # Set flag to signal the _loop to terminate.

        if self._thread and self._thread.is_alive() and wait_for_thread:
            logger.info("Agent: Waiting for processing thread to complete current cycle...")
            # Wait for the thread to finish, with a timeout slightly longer than the run interval.
            self._thread.join(timeout=self.run_interval_seconds + 2)
            if self._thread.is_alive():
                logger.warning("Agent: Processing thread did not finish in the expected time after stop signal.")

        self._thread = None # Clear the thread reference once stopped or if join timed out.
        logger.info("Agent: Background processing stopped successfully.")
