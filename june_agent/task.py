import uuid
import logging
from .request import APIRequest, TogetherAIRequest # Relative import
from june_agent.db import DatabaseManager # Absolute import for db

# Configure logging for this module
logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')


class Task:
    """
    Represents a task to be processed by the agent, with phases and subtask capabilities.
    """
    # Define task statuses and phases as class attributes for clarity and consistency
    STATUS_PENDING = "pending"
    STATUS_ASSESSING = "assessing"
    STATUS_PENDING_SUBTASKS = "pending_subtasks"
    STATUS_EXECUTING = "executing"
    STATUS_RECONCILING = "reconciling"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    PHASE_ASSESSMENT = "assessment"
    PHASE_EXECUTION = "execution"
    PHASE_RECONCILIATION = "reconciliation"

    def __init__(self,
                 description: str,
                 db_manager: DatabaseManager,
                 task_id: str | None = None,
                 initiative_id: str | None = None,
                 parent_task_id: str | None = None,
                 status: str = STATUS_PENDING,
                 phase: str | None = PHASE_ASSESSMENT, # Default to assessment phase
                 result: str | None = None,
                 created_at: str | None = None,
                 updated_at: str | None = None):
        """
        Initializes a new Task.
        Args:
            description (str): The description of the task.
            db_manager (DatabaseManager): Instance of the database manager.
            task_id (str, optional): Existing task ID. Defaults to None (new UUID).
            initiative_id (str, optional): ID of the parent initiative. Defaults to None.
            parent_task_id (str, optional): ID of the parent task if this is a subtask. Defaults to None.
            status (str, optional): Current status. Defaults to "pending".
            phase (str, optional): Current phase. Defaults to "assessment".
            result (str, optional): Result of the task execution. Defaults to None.
            created_at (str, optional): Creation timestamp. Defaults to current time.
            updated_at (str, optional): Last update timestamp. Defaults to current time.
        """
        self.id: str = task_id if task_id else uuid.uuid4().hex
        self.description: str = description
        self.db_manager: DatabaseManager = db_manager # Store db_manager instance

        self.initiative_id: str | None = initiative_id
        self.parent_task_id: str | None = parent_task_id

        self.status: str = status
        self.phase: str | None = phase
        self.result: str | None = result
        self.error_message: str | None = None # Keep error message field

        current_time = self.db_manager.get_current_timestamp()
        self.created_at: str = created_at if created_at else current_time
        self.updated_at: str = updated_at if updated_at else current_time

        self.requests: list[APIRequest] = [] # For API calls during execution phase
        self.subtasks: list[Task] = [] # In-memory list of subtask objects

        logger.info(f"Task {'created' if not task_id else 'loaded'} with ID: {self.id}, Description: '{self.description[:50]}...'")

    def add_request(self, request_obj: APIRequest) -> None:
        if not isinstance(request_obj, APIRequest):
            logger.warning(f"Attempted to add an invalid request object to task {self.id}.")
            return
        self.requests.append(request_obj)
        logger.info(f"Request added to task {self.id}. Total requests: {len(self.requests)}")

    def add_subtask(self, subtask) -> None: # subtask is a Task object
        """Adds a subtask to this task and saves the subtask."""
        if not isinstance(subtask, Task):
            logger.error(f"Invalid object type provided to add_subtask for task {self.id}. Expected Task.")
            raise TypeError("Subtask must be an instance of Task.")

        subtask.parent_task_id = self.id
        subtask.initiative_id = self.initiative_id # Subtasks belong to the same initiative
        if subtask not in self.subtasks:
            self.subtasks.append(subtask)
            # When a subtask is added, the parent task's status might change
            self.status = self.STATUS_PENDING_SUBTASKS
            self.phase = None # Parent task pauses its phase progression
            self.updated_at = self.db_manager.get_current_timestamp()
            self.save() # Save parent task status change
            subtask.save() # Save the new subtask
            logger.info(f"Subtask {subtask.id} added to task {self.id}. Parent status: {self.status}.")
        else:
            logger.warning(f"Subtask {subtask.id} already present in task {self.id}.")


    # --- Phase Methods ---
    def assess(self) -> None:
        """
        Assessment phase: Determine if task is completable, needs subtasks, or fails.
        If completable directly, it prepares the necessary API requests.
        """
        if self.phase != self.PHASE_ASSESSMENT:
            logger.warning(f"Task {self.id} cannot run assess phase. Current phase: {self.phase}")
            return

        logger.info(f"Task {self.id} entering assessment phase.")

        # Clear any pre-existing requests for this task instance from a previous attempt,
        # ensuring assessment starts fresh for request population.
        self.requests = []

        # Placeholder Logic (to be expanded):
        # 1. Analyze self.description.
        # 2. If simple, prepare requests and move to execution.
        # 3. If complex, create subtasks (logic for this would go here).
        # 4. If impossible, set to failed.

        if not self.description: # Basic check
            self.status = self.STATUS_FAILED
            self.error_message = "Task description is empty, cannot assess."
            self.phase = None # No further phase
            logger.error(f"Task {self.id} failed assessment: {self.error_message}")
        else:
            # Simulate assessment determining the task is simple and can proceed to execution.
            # This is where APIRequests would be defined based on the assessment.
            # For now, add a default TogetherAIRequest.

            logger.info(f"Task {self.id} assessment: Adding default TogetherAIRequest.")
            self.add_request(TogetherAIRequest()) # Use the existing add_request method

            logger.info(f"Task {self.id} assessment complete. Moving to execution phase with {len(self.requests)} request(s).")
            self.phase = self.PHASE_EXECUTION
            self.status = self.STATUS_EXECUTING

        self.updated_at = self.db_manager.get_current_timestamp()
        self.save()

    def execute(self) -> None:
        """
        Execution phase: Process API requests.
        This is a placeholder for actual execution logic.
        """
        if self.phase != self.PHASE_EXECUTION:
            logger.warning(f"Task {self.id} cannot run execute phase. Current phase: {self.phase}")
            return

        logger.info(f"Task {self.id} entering execution phase.")
        self.status = self.STATUS_EXECUTING

        if not self.requests:
            logger.warning(f"Task {self.id} has no requests to process for execution. Moving to reconciliation.")
            self.phase = self.PHASE_RECONCILIATION
            # self.status = self.STATUS_COMPLETED # Or failed, depending on whether requests were expected
            self.updated_at = self.db_manager.get_current_timestamp()
            self.save()
            return

        # Simplified: process first request, similar to original logic
        current_request = self.requests[0]
        try:
            logger.info(f"Executing request for task {self.id}: '{self.description[:50]}...'")
            api_result = current_request.execute(self.description) # Assuming execute takes task description
            self.result = api_result

            if api_result and isinstance(api_result, str) and api_result.lower().startswith("error:"):
                self.error_message = api_result
                # Status will be set in reconciliation
                logger.error(f"Task {self.id} execution encountered an error: {self.error_message}")
            else:
                logger.info(f"Task {self.id} execution successful. Result: '{str(self.result)[:100]}...'")

        except Exception as e:
            logger.error(f"Unexpected error during task {self.id} execution: {e}", exc_info=True)
            self.error_message = f"Unexpected error during execution: {e}"
            self.result = None

        self.phase = self.PHASE_RECONCILIATION
        self.updated_at = self.db_manager.get_current_timestamp()
        self.save()


    def reconcile(self) -> None:
        """
        Reconciliation phase: Determine final status based on execution results or subtask completion.
        """
        if self.phase != self.PHASE_RECONCILIATION:
            logger.warning(f"Task {self.id} cannot run reconcile phase. Current phase: {self.phase}")
            return

        logger.info(f"Task {self.id} entering reconciliation phase.")

        # Check subtasks first if any were pending
        if self.status == self.STATUS_PENDING_SUBTASKS:
            all_subtasks_completed = True
            failed_subtask = False
            if not self.subtasks: # If it was pending subtasks but has none, something is wrong or they were cleared.
                 # This case might need specific handling. Assume for now subtasks list is accurate.
                 # If subtasks were loaded from DB, this list should be populated.
                 self.load_subtasks() # Try to load them if not already in memory

            for subtask in self.subtasks:
                if subtask.status != self.STATUS_COMPLETED:
                    all_subtasks_completed = False
                if subtask.status == self.STATUS_FAILED:
                    failed_subtask = True
                    break # One failed subtask can fail the parent

            if failed_subtask:
                self.status = self.STATUS_FAILED
                self.error_message = "One or more subtasks failed."
                logger.error(f"Task {self.id} failed due to subtask failure.")
            elif all_subtasks_completed:
                logger.info(f"All subtasks for task {self.id} completed. Re-assessing parent task.")
                self.status = self.STATUS_PENDING # Back to pending
                self.phase = self.PHASE_ASSESSMENT # Re-assess after subtasks are done
            else:
                # Not all subtasks are done, remains in pending_subtasks. Reconciliation will run again later.
                logger.info(f"Task {self.id}: Not all subtasks completed. Reconciliation will defer.")
                self.updated_at = self.db_manager.get_current_timestamp()
                self.save()
                return # Exit early, do not proceed to final status setting

        # If not dealing with subtasks, or subtasks completed and re-assessed to direct completion
        elif self.error_message: # Check if execution phase recorded an error
            self.status = self.STATUS_FAILED
            logger.error(f"Task {self.id} failed during execution. Error: {self.error_message}")
        elif self.result is not None: # Check if execution produced a result
            self.status = self.STATUS_COMPLETED
            logger.info(f"Task {self.id} completed successfully.")
        else:
            # No error, no result, but execution was supposed to happen. This could be an issue.
            # Or, it could be a task that completes without a specific textual result (e.g. a control task)
            # For now, assume if no error, it's completed. This might need refinement.
            self.status = self.STATUS_COMPLETED
            logger.info(f"Task {self.id} reconciled as completed (no specific result, no error).")


        self.phase = None # Task processing cycle is complete (either success or fail)
        self.updated_at = self.db_manager.get_current_timestamp()
        self.save()

    def process_current_phase(self) -> None:
        """Processes the current phase of the task."""
        logger.debug(f"Processing current phase '{self.phase}' for task {self.id} with status '{self.status}'")
        if self.phase == self.PHASE_ASSESSMENT:
            self.assess()
        elif self.phase == self.PHASE_EXECUTION:
            # Before execution, ensure subtasks are handled if that was the assessment outcome
            if self.status == self.STATUS_PENDING_SUBTASKS:
                logger.info(f"Task {self.id} has pending subtasks. Cannot execute directly. Subtasks must complete first.")
                self.reconcile() # Check subtask status
                return
            self.execute()
        elif self.phase == self.PHASE_RECONCILIATION:
            self.reconcile()
        elif self.status == self.STATUS_PENDING_SUBTASKS and not self.phase:
            # If subtasks were processed, and parent is waiting, it should go to reconciliation
            # to check subtask status.
            logger.info(f"Task {self.id} is pending subtasks. Triggering reconciliation to check subtask status.")
            self.phase = self.PHASE_RECONCILIATION
            self.save() # Persist phase change before calling reconcile
            self.reconcile()
        else:
            logger.info(f"Task {self.id} is in status '{self.status}' and phase '{self.phase}'. No specific action taken by process_current_phase.")


    # --- Database Interaction ---
    def save(self) -> None:
        """Saves the task to the database."""
        query_select = "SELECT id, created_at FROM tasks WHERE id = ?"
        existing_row = self.db_manager.fetch_one(query_select, (self.id,))

        current_time = self.db_manager.get_current_timestamp()
        self.updated_at = current_time

        if existing_row:
            # Preserve original created_at
            self.created_at = existing_row['created_at']

            query_update = """
            UPDATE tasks SET
                initiative_id = ?, parent_task_id = ?, description = ?,
                status = ?, phase = ?, result = ?, updated_at = ?
            WHERE id = ?
            """
            update_data = (
                self.initiative_id, self.parent_task_id, self.description,
                self.status, self.phase, self.result, self.updated_at,
                self.id
            )
            try:
                self.db_manager.execute_query(query_update, update_data)
                logger.info(f"Task {self.id} updated in the database.")
            except Exception as e:
                logger.error(f"Failed to update task {self.id}: {e}", exc_info=True)
        else:
            # For new tasks, created_at is set if not provided, or uses current_time if it was None
            if not self.created_at: # Should have been set in __init__
                 self.created_at = current_time

            query_insert = """
            INSERT INTO tasks (id, initiative_id, parent_task_id, description, status, phase, result, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            insert_data = (
                self.id, self.initiative_id, self.parent_task_id, self.description,
                self.status, self.phase, self.result, self.created_at, self.updated_at
            )
            try:
                self.db_manager.execute_query(query_insert, insert_data)
                logger.info(f"Task {self.id} saved to the database.")
            except Exception as e:
                logger.error(f"Failed to save new task {self.id}: {e}", exc_info=True)

    @classmethod
    def load(cls, task_id: str, db_manager: DatabaseManager):
        """Loads a task from the database by its ID."""
        query = "SELECT * FROM tasks WHERE id = ?"
        row = db_manager.fetch_one(query, (task_id,))
        if row:
            task = cls(description=row['description'], db_manager=db_manager, task_id=row['id'],
                       initiative_id=row['initiative_id'], parent_task_id=row['parent_task_id'],
                       status=row['status'], phase=row['phase'], result=row['result'],
                       created_at=row['created_at'], updated_at=row['updated_at'])
            # Subtasks and requests are not loaded by default to avoid deep object graphs.
            # They can be loaded on demand.
            logger.info(f"Task {task_id} loaded from database.")
            return task
        else:
            logger.warning(f"Task with ID {task_id} not found in the database.")
            return None

    def load_subtasks(self) -> None:
        """Loads subtasks for this task from the database."""
        if not self.id:
            logger.error("Cannot load subtasks for a task without an ID.")
            return
        query = "SELECT id FROM tasks WHERE parent_task_id = ?"
        rows = self.db_manager.fetch_all(query, (self.id,))
        self.subtasks = [] # Clear existing in-memory subtasks before loading
        for row in rows:
            subtask = Task.load(row['id'], self.db_manager)
            if subtask:
                self.subtasks.append(subtask)
        logger.info(f"Loaded {len(self.subtasks)} subtasks for task {self.id}.")


    def to_dict(self) -> dict:
        """Returns a dictionary representation of the task."""
        return {
            'id': self.id,
            'description': self.description,
            'initiative_id': self.initiative_id,
            'parent_task_id': self.parent_task_id,
            'status': self.status,
            'phase': self.phase,
            'result': self.result,
            'error_message': self.error_message,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'num_requests': len(self.requests),
            'num_subtasks': len(self.subtasks), # Number of in-memory subtasks
            'subtask_ids': [st.id for st in self.subtasks] # IDs of in-memory subtasks
        }

    @classmethod
    def load_all(cls, db_manager: DatabaseManager, initiative_id: str | None = None):
        """
        Loads all tasks from the database, optionally filtered by initiative_id.
        Orders by creation time.
        """
        tasks = []
        if initiative_id:
            query = "SELECT id FROM tasks WHERE initiative_id = ? ORDER BY created_at ASC"
            rows = db_manager.fetch_all(query, (initiative_id,))
        else:
            query = "SELECT id FROM tasks ORDER BY created_at ASC"
            rows = db_manager.fetch_all(query)

        for row in rows:
            task = cls.load(row['id'], db_manager)
            if task:
                tasks.append(task)
        logger.info(f"Loaded {len(tasks)} tasks {'for initiative ' + initiative_id if initiative_id else 'in total'}.")
        return tasks

if __name__ == '__main__':
    # Basic test block for the new Task class functionality
    logger.info("Running basic test for Task class...")
    db_path_task_test = 'test_task_june_agent.db'
    db_manager_task_test = DatabaseManager(db_path=db_path_task_test)

    # Mock APIRequest for testing if needed
    class MockAPIRequest(APIRequest):
        def __init__(self, api_key: str = "test_key", model_name: str = "test_model"):
            super().__init__(api_key=api_key, model_name=model_name)

        def execute(self, prompt: str) -> str:
            logger.info(f"MockAPIRequest executed with prompt: {prompt}")
            if "fail" in prompt.lower():
                return "Error: Mock failure requested"
            return f"Mock result for: {prompt}"

    try:
        db_manager_task_test.connect()
        db_manager_task_test.create_tables() # Ensure tables exist

        # 1. Create and save a main task
        main_task_desc = "Main task for testing phases"
        main_task = Task(description=main_task_desc, db_manager=db_manager_task_test)
        main_task.save()
        logger.info(f"Saved main task: {main_task.to_dict()}")

        # 2. Load the task
        loaded_main_task = Task.load(task_id=main_task.id, db_manager=db_manager_task_test)
        assert loaded_main_task is not None
        assert loaded_main_task.description == main_task_desc
        logger.info(f"Loaded main task: {loaded_main_task.to_dict()}")

        # 3. Test Assessment Phase
        logger.info("--- Testing Assessment Phase ---")
        loaded_main_task.assess() # Should move to execution by default (placeholder logic)
        assert loaded_main_task.phase == Task.PHASE_EXECUTION
        logger.info(f"After assess: {loaded_main_task.to_dict()}")

        # 4. Test Execution Phase (with a mock request)
        logger.info("--- Testing Execution Phase ---")
        mock_req = MockAPIRequest()
        loaded_main_task.add_request(mock_req)
        loaded_main_task.execute() # Should process request and move to reconciliation
        assert loaded_main_task.phase == Task.PHASE_RECONCILIATION
        assert loaded_main_task.result is not None
        logger.info(f"After execute: {loaded_main_task.to_dict()}")

        # 5. Test Reconciliation Phase
        logger.info("--- Testing Reconciliation Phase ---")
        loaded_main_task.reconcile() # Should complete the task
        assert loaded_main_task.status == Task.STATUS_COMPLETED
        assert loaded_main_task.phase is None
        logger.info(f"After reconcile: {loaded_main_task.to_dict()}")

        # 6. Test Task with Subtasks
        logger.info("--- Testing Task with Subtasks ---")
        parent_task_desc = "Parent task with subtasks"
        parent_task = Task(description=parent_task_desc, db_manager=db_manager_task_test)
        parent_task.save()
        logger.info(f"Saved parent task: {parent_task.to_dict()}")

        subtask1_desc = "Subtask 1"
        # Ensure initiative_id is passed if tasks are linked to initiatives
        subtask1 = Task(description=subtask1_desc, db_manager=db_manager_task_test, initiative_id=parent_task.initiative_id)

        # Use add_subtask method for proper linking and status updates
        parent_task.add_subtask(subtask1)
        # add_subtask now saves both parent and subtask

        logger.info(f"Parent task after adding subtask: {parent_task.to_dict()}")
        logger.info(f"Subtask1: {subtask1.to_dict()}")
        assert parent_task.status == Task.STATUS_PENDING_SUBTASKS
        assert subtask1.parent_task_id == parent_task.id

        # Simulate subtask1 completion
        # Load subtask1 to modify it as a separate instance
        loaded_subtask1 = Task.load(subtask1.id, db_manager_task_test)
        assert loaded_subtask1 is not None
        loaded_subtask1.status = Task.STATUS_COMPLETED
        loaded_subtask1.phase = None # Completed tasks have no active phase
        loaded_subtask1.result = "Subtask 1 completed successfully"
        loaded_subtask1.save()
        logger.info(f"Subtask1 after completion: {loaded_subtask1.to_dict()}")

        # Load parent task again to get fresh state for reconciliation
        reloaded_parent_task = Task.load(parent_task.id, db_manager_task_test)
        assert reloaded_parent_task is not None
        # load_subtasks needs to be called to populate the .subtasks list in the reloaded_parent_task object
        reloaded_parent_task.load_subtasks()

        logger.info(f"Reloaded parent task before reconcile (subtasks): {reloaded_parent_task.to_dict()}")
        # Parent should be in PENDING_SUBTASKS, reconcile should pick it up
        assert reloaded_parent_task.status == Task.STATUS_PENDING_SUBTASKS

        # Manually set phase to RECONCILIATION to direct the test flow for process_current_phase,
        # or call reconcile() directly if that's the intended test.
        # If process_current_phase is called and status is PENDING_SUBTASKS, it should auto-set to RECONCILIATION.
        reloaded_parent_task.process_current_phase()

        assert reloaded_parent_task.status == Task.STATUS_PENDING # Should go back to pending
        assert reloaded_parent_task.phase == Task.PHASE_ASSESSMENT # To re-assess after subtasks
        logger.info(f"Parent task after subtask completion and reconciliation: {reloaded_parent_task.to_dict()}")

    except Exception as e:
        logger.error(f"Error during Task class test: {e}", exc_info=True)
    finally:
        db_manager_task_test.close()
        # import os
        # os.remove(db_path_task_test) # Clean up
        # logger.info(f"Test database {db_path_task_test} removed.")
