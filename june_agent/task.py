import uuid
import logging
import datetime
import json # For parsing AI model's JSON response
from typing import Optional, List, Any

from .request import APIRequest, TogetherAIRequest
from june_agent.prompts import get_prompt # Import the new prompt system

logger = logging.getLogger(__name__)

class Task: # Pure Domain Object
    """
    Represents a domain Task object with its properties and in-memory business logic.
    This class is responsible for managing the state of a task (e.g., description, status, phase)
    and defining the transitions between states/phases (assess, execute, reconcile).
    It does not handle persistence directly; that is the responsibility of a ModelService.
    """
    # --- Task Status Constants ---
    STATUS_PENDING = "pending"          # Task is new or waiting for subtasks/re-assessment.
    STATUS_ASSESSING = "assessing"      # Task is being analyzed for complexity or next steps.
    STATUS_PENDING_SUBTASKS = "pending_subtasks"
    STATUS_EXECUTING = "executing"        # Task is actively being worked on (e.g., API call).
    STATUS_RECONCILING = "reconciling"    # Task execution/subtasks finished, determining final status.
    STATUS_COMPLETED = "completed"        # Task finished successfully.
    STATUS_FAILED = "failed"            # Task could not be completed.

    # --- Task Phase Constants ---
    # Phases represent stages within certain statuses (primarily PENDING_EXECUTION or EXECUTING).
    PHASE_ASSESSMENT = "assessment"        # Analyzing task requirements, planning execution.
    PHASE_EXECUTION = "execution"          # Performing the core work of the task.
    PHASE_RECONCILIATION = "reconciliation"  # Finalizing results and status after execution/subtasks.

    def __init__(self,
                 description: str,
                 task_id: str | None = None, # Optional: auto-generates if None
                 initiative_id: str | None = None,
                 parent_task_id: str | None = None,
                 status: str = STATUS_PENDING,      # Initial status
                 phase: str | None = PHASE_ASSESSMENT, # Initial phase
                 result: str | None = None,             # Result of successful execution
                 error_message: str | None = None,      # Error details if failed
                 created_at: Optional[datetime.datetime] = None, # Timestamp of creation
                 updated_at: Optional[datetime.datetime] = None, # Timestamp of last update
                 requests: Optional[List[APIRequest]] = None,    # APIRequests for this task
                 subtasks: Optional[List['Task']] = None):       # List of domain subtask objects
        """
        Initializes a Task domain object.

        Args:
            description: Textual description of the task.
            task_id: Optional unique ID for the task. Auto-generated if None.
            initiative_id: Optional ID of the initiative this task belongs to.
            parent_task_id: Optional ID of the parent task if this is a subtask.
            status: Initial status of the task.
            phase: Initial phase of the task.
            result: Pre-set result, if any.
            error_message: Pre-set error message, if any.
            created_at: Optional creation timestamp (defaults to now UTC).
            updated_at: Optional update timestamp (defaults to created_at or now UTC).
            requests: Optional list of APIRequest objects associated with this task.
            subtasks: Optional list of child Task domain objects.
        """
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

        self.requests: List[APIRequest] = requests if requests is not None else [] # In-memory list of API requests for execution.
        self.subtasks: List[Task] = subtasks if subtasks is not None else []     # In-memory list of sub-Task domain objects.

        # For storing subtask descriptions suggested by AI assessment
        self.suggested_subtasks: Optional[List[str]] = None

        logger.info(f"Domain Task '{self.id}' initialized. Desc: '{self.description[:30]}...'")

    def add_request(self, request_obj: APIRequest) -> None:
        """Adds an APIRequest object to the task's internal list of requests."""
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
        """
        Assesses the task by querying an AI model for the best course of action.
        Updates task state based on the AI's structured JSON response.
        Persistence of these changes is handled externally.
        """
        if self.phase != self.PHASE_ASSESSMENT:
            logger.warning(f"Task {self.id} cannot run assess. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) assessing using AI model.")
        self.requests = [] # Clear any prior execution requests
        self.suggested_subtasks = None # Clear previous suggestions
        self.result = None # Clear previous result
        self.error_message = None # Clear previous error
        self.updated_at = datetime.datetime.utcnow()

        if not self.description:
            self.status = self.STATUS_FAILED
            self.error_message = "Task description is empty, cannot assess."
            self.phase = None
            logger.error(f"Task {self.id} (domain) assessment failed: {self.error_message}")
            return

        prompt_text = get_prompt("assess_task_v1", task_description=self.description)
        if not prompt_text:
            self.status = self.STATUS_FAILED
            self.error_message = "Failed to retrieve assessment prompt."
            self.phase = None
            logger.error(f"Task {self.id} (domain) assessment failed: {self.error_message}")
            return

        # For now, using TogetherAIRequest as the default for assessment.
        # This could be made configurable or use a different request type.
        assessment_request = TogetherAIRequest()

        try:
            raw_ai_response = assessment_request.execute(prompt_text)

            if raw_ai_response and raw_ai_response.lower().startswith("error:"):
                # Error came from the APIRequest execution itself (e.g., connection error)
                self.status = self.STATUS_FAILED
                self.error_message = f"Assessment API request failed: {raw_ai_response}"
                self.phase = None
                logger.error(f"Task {self.id} (domain) assessment error: {self.error_message}")
                return

            # Attempt to parse the AI's response as JSON
            try:
                # The AI is instructed to return JSON, but it might be wrapped or have issues.
                # Basic cleanup: find JSON block if wrapped.
                json_start = raw_ai_response.find('{')
                json_end = raw_ai_response.rfind('}') + 1
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_str = raw_ai_response[json_start:json_end]
                    assessment_data = json.loads(json_str)
                else:
                    raise json.JSONDecodeError("No JSON object found in response", raw_ai_response, 0)

            except json.JSONDecodeError as e:
                self.status = self.STATUS_FAILED
                self.error_message = f"Failed to parse AI assessment response as JSON: {e}. Response: {raw_ai_response[:200]}..."
                self.phase = None
                logger.error(f"Task {self.id} (domain) assessment error: {self.error_message}")
                return

            # Process the structured assessment data
            outcome = assessment_data.get("assessment_outcome")
            payload = assessment_data.get("result_payload")
            # reasoning = assessment_data.get("reasoning", "") # Can be logged or stored if needed

            if outcome == "direct_completion":
                self.status = self.STATUS_COMPLETED # Assessment led to direct completion
                self.result = str(payload) if payload is not None else "Completed directly by assessment."
                self.phase = None # Terminal state
                logger.info(f"Task {self.id} assessed as 'direct_completion'. Result: {self.result}")
            elif outcome == "subtask_breakdown":
                if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
                    self.status = self.STATUS_PENDING_SUBTASKS
                    self.suggested_subtasks = payload
                    self.phase = None # Agent will handle subtask creation, then task might reconcile or re-assess
                    logger.info(f"Task {self.id} assessed for 'subtask_breakdown'. Suggested: {len(payload)} subtasks.")
                else:
                    self.status = self.STATUS_FAILED
                    self.error_message = "AI suggested subtask breakdown but payload was invalid."
                    self.phase = None
                    logger.error(f"Task {self.id} (domain) assessment error: {self.error_message} Payload: {payload}")
            elif outcome == "cannot_complete":
                self.status = self.STATUS_FAILED
                self.error_message = str(payload) if payload is not None else "AI assessed task as not completable."
                self.phase = None # Terminal state
                logger.info(f"Task {self.id} assessed as 'cannot_complete'. Reason: {self.error_message}")
            else: # Unknown outcome
                self.status = self.STATUS_FAILED
                self.error_message = f"Unknown assessment outcome from AI: '{outcome}'. Full response: {assessment_data}"
                self.phase = None
                logger.error(f"Task {self.id} (domain) assessment error: {self.error_message}")

        except Exception as e: # Catch any other unexpected error during assessment API call
            self.status = self.STATUS_FAILED
            self.error_message = f"Unexpected error during AI assessment call: {str(e)}"
            self.phase = None
            logger.error(f"Task {self.id} (domain) assessment critical error: {self.error_message}", exc_info=True)

        logger.info(f"Task {self.id} (domain) assessment final outcome: Status='{self.status}', Phase='{self.phase}'")


    def execute(self) -> None: # Logic for execution if assessment leads here
        """
        Executes the task based on its current requests (in-memory).
        This typically involves making an API call (simulated here if requests are mocks).
        Updates task's result or error_message and transitions to reconciliation phase.
        Persistence of these changes is handled externally by the ModelService.
        """
        if self.phase != self.PHASE_EXECUTION:
            logger.warning(f"Task {self.id} cannot run execute. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) executing.")
        self.status = self.STATUS_EXECUTING # Ensure status reflects execution
        self.updated_at = datetime.datetime.utcnow()

        if not self.requests: # This might happen if assess decided to execute but didn't add requests
            logger.warning(f"Task {self.id} in execution phase but has no requests. Moving to reconciliation.")
            self.phase = self.PHASE_RECONCILIATION
            # If assess() transitions to EXECUTION, it *must* add requests.
            # This path indicates a logic flaw if reached after typical assessment.
            # However, a task could be manually set to EXECUTION phase.
            return

        # Simplified: process only the first request in the list.
        current_request = self.requests[0]
        try:
            api_result = current_request.execute(self.description)
            self.result = api_result
            # If API indicates error in its result string, capture it.
            if isinstance(api_result, str) and api_result.lower().startswith("error:"):
                self.error_message = api_result
            else:
                self.error_message = None # Clear any previous error if current execution is successful
        except Exception as e:
            logger.error(f"Task {self.id} (domain) execution error: {e}", exc_info=True)
            self.error_message = f"Unexpected error during execution: {str(e)}"
            self.result = None # Ensure result is cleared on error

        self.phase = self.PHASE_RECONCILIATION # Always move to reconciliation after execution attempt.


    def reconcile(self) -> None:
        """
        Reconciles the task's final status based on its execution result/error
        or the status of its subtasks.
        The `self.subtasks` list (of domain Task objects) must be populated by the caller
        (e.g., Agent via ModelService) before this method is called if the task
        is in `STATUS_PENDING_SUBTASKS`.
        Persistence of changes is handled externally.
        """
        if self.phase != self.PHASE_RECONCILIATION:
            logger.warning(f"Task {self.id} cannot run reconcile. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) reconciling. In-memory subtasks: {len(self.subtasks)}")
        self.updated_at = datetime.datetime.utcnow()

        initial_status_for_reconcile = self.status # Store status before potential changes

        if initial_status_for_reconcile == self.STATUS_PENDING_SUBTASKS:
            # Logic for handling subtask completion status
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
                    if subtask_domain.status != self.STATUS_COMPLETED: all_subtasks_completed = False
                    if subtask_domain.status == self.STATUS_FAILED: failed_subtask = True; break
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

        # If status was already set to a terminal one by assessment (e.g. direct_completion, cannot_complete)
        # or by subtask logic, don't override unless it's still in a processing state.
        if self.status not in [self.STATUS_COMPLETED, self.STATUS_FAILED, self.STATUS_PENDING, self.STATUS_PENDING_SUBTASKS]:
            if self.error_message: # Error from execute phase or previous assess
                self.status = self.STATUS_FAILED
            elif self.result is not None: # Success from execute phase or previous assess
                self.status = self.STATUS_COMPLETED
            else:
                # This path is tricky. If it was PENDING -> ASSESSMENT -> (no requests created) -> EXECUTION (no requests) -> RECONCILIATION,
                # then it means the assessment decided no direct action was needed, and execution also had nothing.
                # Such a task might be considered "completed" if there's no error, or it might indicate a logic flaw.
                if initial_status_for_reconcile == self.STATUS_EXECUTING: # Task came from an execution attempt
                    self.status = self.STATUS_COMPLETED
                    logger.info(f"Task {self.id} (domain) reconciled to COMPLETED as execution yielded no specific result/error.")
                # If initial_status_for_reconcile was something else (e.g. RECONCILING directly set),
                # and no subtask logic changed status, and no error/result, its state remains ambiguous.
                # For now, we only set to COMPLETED if it came from EXECUTE and had no errors.

        # Clear phase if task has reached a terminal status (Completed/Failed)
        # AND it's not being sent back to assessment (which would happen after subtasks complete).
        if (self.status == self.STATUS_COMPLETED or self.status == self.STATUS_FAILED) and \
           not (self.status == self.STATUS_PENDING and self.phase == self.PHASE_ASSESSMENT): # Check if it's going to re-assess
            self.phase = None

    def process_current_phase(self) -> None:
        """Processes the current phase of the task by calling internal phase methods.
           Modifies state in-memory. Persistence is handled by caller (Agent/ModelService).
        """
        logger.debug(f"Task {self.id} (domain) processing phase '{self.phase}' (Status: '{self.status}')")
        current_phase_before_call = self.phase
        current_status_before_call = self.status
        if self.phase == self.PHASE_ASSESSMENT: self.assess()
        elif self.phase == self.PHASE_EXECUTION:
            if self.status == self.STATUS_PENDING_SUBTASKS: # Should have been outcome of assess
                logger.info(f"Task {self.id} is {self.STATUS_PENDING_SUBTASKS}. Switching to reconcile phase.")
                self.phase = self.PHASE_RECONCILIATION
                # Agent will save this change and then call process_current_phase again.
                # Or, directly call reconcile if the pattern is single call, multiple internal transitions.
                self.reconcile() # Let reconcile handle PENDING_SUBTASKS
            else: self.execute()
        elif self.phase == self.PHASE_RECONCILIATION: self.reconcile()
        # This case handles if status is PENDING_SUBTASKS and phase was set to None (e.g. by add_subtask).
        # It should then go into reconciliation.
        elif self.status == self.STATUS_PENDING_SUBTASKS and not self.phase:
            logger.info(f"Task {self.id} (domain) is {self.STATUS_PENDING_SUBTASKS} with no prior phase. Setting to reconcile.")
            self.phase = self.PHASE_RECONCILIATION
            self.reconcile()
        else: logger.info(f"Task {self.id} (domain) status '{self.status}', phase '{self.phase}'. No specific phase action by process_current_phase.")
        # If status or phase changed during the processing, update the timestamp.
        if self.phase != current_phase_before_call or self.status != current_status_before_call:
             self.updated_at = datetime.datetime.utcnow()

    def to_pydantic_schema(self) -> 'TaskSchema':
        """
        Converts this domain Task object to its Pydantic TaskSchema representation.
        This is used for transferring task data, e.g., in API responses.
        """
        # Dynamically import TaskSchema here to avoid potential circular import issues at module level,
        # though with current structure it might be fine at the top.
        from june_agent.models_v2.pydantic_models import TaskSchema

        # Populate subtask_ids from the in-memory list of domain subtask objects.
        sub_ids = [st.id for st in self.subtasks] if self.subtasks else []

        return TaskSchema(
            id=self.id, description=self.description, status=self.status,
            phase=self.phase, result=self.result, error_message=self.error_message,
            initiative_id=self.initiative_id, parent_task_id=self.parent_task_id,
            created_at=self.created_at, updated_at=self.updated_at, subtask_ids=sub_ids
        )
