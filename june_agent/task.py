import uuid
import logging
import datetime
from typing import Optional, List, Any # Any for APIRequest for now

# Pydantic schema for conversion, and constants can be shared if needed.
# from june_agent.models_v2.pydantic_models import TaskSchema

# Request handling (remains the same for now - Task domain object holds these)
# Assuming APIRequest and TogetherAIRequest are simple enough not to need major changes here yet.
# If they also carry persistent state or complex logic, they'd need similar review.
from .request import APIRequest, TogetherAIRequest


logger = logging.getLogger(__name__)

class Task: # Pure Domain Object
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
                 task_id: str | None = None,
                 initiative_id: str | None = None,
                 parent_task_id: str | None = None,
                 status: str = STATUS_PENDING,
                 phase: str | None = PHASE_ASSESSMENT,
                 result: str | None = None,
                 error_message: str | None = None,
                 created_at: Optional[datetime.datetime] = None,
                 updated_at: Optional[datetime.datetime] = None,
                 requests: Optional[List[APIRequest]] = None, # For in-memory requests
                 subtasks: Optional[List['Task']] = None):   # For in-memory subtask domain objects

        self.id: str = task_id if task_id else uuid.uuid4().hex
        self.description: str = description
        self.initiative_id: str | None = initiative_id
        self.parent_task_id: str | None = parent_task_id
        self.status: str = status
        self.phase: str | None = phase
        self.result: str | None = result
        self.error_message: str | None = error_message

        now = datetime.datetime.utcnow()
        self.created_at: datetime.datetime = created_at if created_at else now
        self.updated_at: datetime.datetime = updated_at if updated_at else self.created_at

        self.requests: List[APIRequest] = requests if requests is not None else []
        self.subtasks: List[Task] = subtasks if subtasks is not None else []

        logger.info(f"Domain Task '{self.id}' initialized. Desc: '{self.description[:30]}...'")

    def add_request(self, request_obj: APIRequest) -> None:
        if not isinstance(request_obj, APIRequest):
            logger.warning(f"Attempted to add an invalid request object to task {self.id}.")
            return
        self.requests.append(request_obj)
        logger.info(f"Request added to task {self.id}. Total requests: {len(self.requests)}")

    def add_subtask(self, subtask_domain_obj: 'Task') -> None:
        """Adds a subtask (domain object) to this task's in-memory list.
           Persistence of parent and subtask is handled by the Agent/ModelService.
        """
        if not isinstance(subtask_domain_obj, Task):
            raise TypeError("Subtask must be an instance of Task domain model.")

        subtask_domain_obj.parent_task_id = self.id
        subtask_domain_obj.initiative_id = self.initiative_id

        if subtask_domain_obj not in self.subtasks:
            self.subtasks.append(subtask_domain_obj)
            self.status = self.STATUS_PENDING_SUBTASKS
            self.phase = None
            self.updated_at = datetime.datetime.utcnow()
            logger.info(f"Subtask {subtask_domain_obj.id} added in-memory to task {self.id}. Parent status: {self.status}.")
        else:
            logger.warning(f"Subtask {subtask_domain_obj.id} domain object already in parent's list {self.id}.")

    # --- Phase Methods (modify in-memory state only) ---
    def assess(self) -> None:
        """Modifies state based on assessment. Persistence is external."""
        if self.phase != self.PHASE_ASSESSMENT:
            logger.warning(f"Task {self.id} cannot run assess. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) assessing.")
        self.requests = [] # Clear previous requests for this assessment cycle
        self.updated_at = datetime.datetime.utcnow()

        if not self.description:
            self.status = self.STATUS_FAILED
            self.error_message = "Task description is empty, cannot assess."
            self.phase = None
        else:
            # For now, default behavior: prepare for execution by adding a request
            self.add_request(TogetherAIRequest()) # In-memory addition
            self.phase = self.PHASE_EXECUTION
            self.status = self.STATUS_EXECUTING
        logger.info(f"Task {self.id} (domain) assessment outcome: Status='{self.status}', Phase='{self.phase}'")


    def execute(self) -> None:
        """Modifies state based on execution. Persistence is external."""
        if self.phase != self.PHASE_EXECUTION:
            logger.warning(f"Task {self.id} cannot run execute. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) executing.")
        self.status = self.STATUS_EXECUTING # Ensure status is executing
        self.updated_at = datetime.datetime.utcnow()

        if not self.requests:
            logger.warning(f"Task {self.id} has no requests for execution. Moving to reconciliation.")
            self.phase = self.PHASE_RECONCILIATION
            # No result/error set here from execution itself
            return # Agent/ModelService will save this state change

        current_request = self.requests[0]
        try:
            api_result = current_request.execute(self.description)
            self.result = api_result
            if isinstance(api_result, str) and api_result.lower().startswith("error:"):
                self.error_message = api_result
            else: # Clear previous error if current execution is successful
                self.error_message = None
        except Exception as e:
            self.error_message = f"Unexpected error during execution: {str(e)}"
            self.result = None

        self.phase = self.PHASE_RECONCILIATION


    def reconcile(self) -> None: # Takes list of its subtask domain objects if needed for PENDING_SUBTASKS
        """Modifies state based on reconciliation. Persistence is external.
           The self.subtasks list must be up-to-date (populated by Agent/ModelService)
           before calling this method if status is PENDING_SUBTASKS.
        """
        if self.phase != self.PHASE_RECONCILIATION:
            logger.warning(f"Task {self.id} cannot run reconcile. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) reconciling. Current subtasks in list: {len(self.subtasks)}")
        self.updated_at = datetime.datetime.utcnow()

        initial_status_for_reconcile = self.status

        if initial_status_for_reconcile == self.STATUS_PENDING_SUBTASKS:
            all_subtasks_completed = True
            failed_subtask = False

            if not self.subtasks:
                logger.warning(f"Task {self.id} is {self.STATUS_PENDING_SUBTASKS} but has no subtasks in its list for reconciliation.")
                # This implies subtasks might have been deleted or never created properly.
                # Defaulting to re-assess the parent as if subtask phase is over.
                self.status = self.STATUS_PENDING
                self.phase = self.PHASE_ASSESSMENT
                # No error_message set here, assuming this is a "subtasks done" path
            else:
                for subtask_domain in self.subtasks:
                    if subtask_domain.status != self.STATUS_COMPLETED:
                        all_subtasks_completed = False
                    if subtask_domain.status == self.STATUS_FAILED:
                        failed_subtask = True
                        break

                if failed_subtask:
                    self.status = self.STATUS_FAILED
                    self.error_message = self.error_message or "One or more subtasks failed." # Preserve existing error if any
                    self.phase = None
                elif all_subtasks_completed:
                    self.status = self.STATUS_PENDING
                    self.phase = self.PHASE_ASSESSMENT
                    self.result = self.result or "Subtasks completed successfully." # Aggregate result
                    self.error_message = None # Clear error if subtasks succeeded
                else: # Not all subtasks done, so parent remains PENDING_SUBTASKS
                    self.status = self.STATUS_PENDING_SUBTASKS # Explicitly ensure it stays
                    self.phase = self.PHASE_RECONCILIATION # Stays in reconciliation to be checked again
                    return # No final state change yet for parent beyond subtask check

        # Standard reconciliation if not PENDING_SUBTASKS, or if subtask processing led to a new state
        # Only proceed if status wasn't set by subtask logic above to a final state or PENDING
        if self.status not in [self.STATUS_FAILED, self.STATUS_PENDING, self.STATUS_PENDING_SUBTASKS]:
            if self.error_message: # Error from execute phase
                self.status = self.STATUS_FAILED
            elif self.result is not None: # Success from execute phase
                self.status = self.STATUS_COMPLETED
            else: # No error, no result (e.g. from execute phase with no requests, or task just created)
                  # This path is tricky. If it was just created and went PENDING -> ASSESSMENT -> (no requests) -> RECONCILIATION
                  # then it should probably be COMPLETED.
                if initial_status_for_reconcile == self.STATUS_EXECUTING : # Came from execution
                    self.status = self.STATUS_COMPLETED
                # If it's in some other state and lands here, it's less clear.
                # Defaulting to completed for now if no error.
                # self.status = self.STATUS_COMPLETED

        # Clear phase if task reached a terminal status (Completed/Failed)
        # and is not returning to Assessment
        if (self.status == self.STATUS_COMPLETED or self.status == self.STATUS_FAILED) and self.phase != self.PHASE_ASSESSMENT:
            self.phase = None


    def process_current_phase(self) -> None: # No db session needed
        """Processes the current phase of the task by calling internal phase methods.
           Modifies state in-memory. Persistence is handled by caller (Agent/ModelService).
        """
        logger.debug(f"Task {self.id} (domain) processing phase '{self.phase}' (Status: '{self.status}')")

        current_phase_before_call = self.phase
        current_status_before_call = self.status

        if self.phase == self.PHASE_ASSESSMENT:
            self.assess()
        elif self.phase == self.PHASE_EXECUTION:
            if self.status == self.STATUS_PENDING_SUBTASKS: # Should have been outcome of assess
                logger.info(f"Task {self.id} is {self.STATUS_PENDING_SUBTASKS}. Switching to reconcile phase.")
                self.phase = self.PHASE_RECONCILIATION
                # Agent will save this change and then call process_current_phase again.
                # Or, directly call reconcile if the pattern is single call, multiple internal transitions.
                self.reconcile() # Let reconcile handle PENDING_SUBTASKS
            else:
                self.execute()
        elif self.phase == self.PHASE_RECONCILIATION:
            self.reconcile()
        # This case is if status is PENDING_SUBTASKS and phase became None from add_subtask
        elif self.status == self.STATUS_PENDING_SUBTASKS and not self.phase:
            logger.info(f"Task {self.id} is {self.STATUS_PENDING_SUBTASKS} with no phase. Setting to reconcile.")
            self.phase = self.PHASE_RECONCILIATION
            self.reconcile() # Call reconcile to check subtasks
        else:
            logger.info(f"Task {self.id} (domain) status '{self.status}', phase '{self.phase}'. No specific action in process_current_phase.")

        if self.phase != current_phase_before_call or self.status != current_status_before_call:
             self.updated_at = datetime.datetime.utcnow()


    def to_pydantic_schema(self) -> 'TaskSchema': # No db session needed
        """Converts this domain Task to its Pydantic TaskSchema representation."""
        # Need to import TaskSchema if not already.
        from june_agent.models_v2.pydantic_models import TaskSchema

        # Ensure subtasks are just IDs for the schema
        sub_ids = [st.id for st in self.subtasks] if self.subtasks else []

        return TaskSchema(
            id=self.id,
            description=self.description,
            status=self.status,
            phase=self.phase,
            result=self.result,
            error_message=self.error_message,
            initiative_id=self.initiative_id,
            parent_task_id=self.parent_task_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            subtask_ids=sub_ids # Populated from in-memory domain subtask objects
        )
