import uuid
import logging
import datetime
import json
from typing import Optional, List, Any

from .request import APIRequest # Still needed for type hints and if requests list stores them
# Remove direct import of TogetherAIRequest if factory is always used
# from .request import TogetherAIRequest
from june_agent.prompts import get_prompt
from june_agent.request_factory import RequestFactory # Import RequestFactory

logger = logging.getLogger(__name__)

class Task: # Pure Domain Object
    """
    Represents a domain Task object with its properties and in-memory business logic.

    This class is responsible for managing the state of a task (e.g., description,
    status, phase, result, error messages) and defining the transitions between
    these states/phases through methods like `assess`, `execute`, and `reconcile`.

    Key aspects:
    - **Pure Domain Logic**: It focuses on the rules and state changes of a task,
      independent of how it's stored or retrieved.
    - **State Management**: Holds all attributes of a task, including lists for
      `requests` (API calls to be made) and `subtasks` (child domain Task objects).
    - **Phase Transitions**: The `process_current_phase` method orchestrates calls to
      `assess`, `execute`, or `reconcile` based on the task's current phase.
    - **AI-Driven Assessment**: The `assess` method uses a `RequestFactory` to obtain an
      `APIRequest` object, calls an AI model (via a prompt from `june_agent.prompts`)
      to determine the task's nature, and updates its state based on the AI's response
      (e.g., direct completion, subtask breakdown, execution readiness, or failure).
    - **Subtask Handling**: If assessment suggests subtasks, their descriptions are stored
      in `suggested_subtasks`. The `Agent` class is responsible for creating these
      subtasks via the `ModelService`. The `reconcile` method checks the status of
      its `subtasks` list (which must be populated by the `Agent`/`ModelService`)
      to determine the parent task's outcome.
    - **Persistence Agnostic**: This class does not interact directly with any database
      or persistence layer. Saving and loading task state is handled by a `ModelService`.
    - **Pydantic Conversion**: Provides a `to_pydantic_schema()` method to convert itself
      into a `TaskSchema` Pydantic model, typically for API responses.
    """
    # --- Task Status Constants ---
    STATUS_PENDING = "pending"          # Task is new, awaiting assessment, or has completed subtasks and needs re-assessment.
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
                 requests: Optional[List[APIRequest]] = None,    # In-memory list of APIRequest objects for execution.
                 subtasks: Optional[List['Task']] = None):       # In-memory list of child Task domain objects.
        """
        Initializes a Task domain object.

        Args:
            description: Textual description of the task.
            task_id: Optional unique ID. Auto-generated if None.
            initiative_id: Optional ID of the parent initiative.
            parent_task_id: Optional ID of the parent task if this is a subtask.
            status: Initial status (e.g., "pending").
            phase: Initial phase (e.g., "assessment").
            result: Pre-set result if task is already completed or has a direct result.
            error_message: Pre-set error message if task has already failed.
            created_at: Optional creation timestamp (defaults to `datetime.utcnow()`).
            updated_at: Optional last update timestamp (defaults to `created_at`).
            requests: Optional list of `APIRequest` objects for the task's execution phase.
            subtasks: Optional list of child `Task` domain objects.
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
    def assess(self, request_factory: RequestFactory) -> None: # Added request_factory
        """
        Assesses the task by querying an AI model (via RequestFactory) for the best course of action.
        Updates task state based on the AI's structured JSON response.
        Persistence of these changes is handled externally by the ModelService.
        Args:
            request_factory: A RequestFactory instance to create APIRequest objects.
        """
        if self.phase != self.PHASE_ASSESSMENT:
            logger.warning(f"Task {self.id} cannot run assess. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) assessing using AI model via RequestFactory.")
        self.requests = [] # Clear any prior execution requests
        self.suggested_subtasks = None # Clear previous suggestions
        self.result = None # Clear previous result
        self.error_message = None # Clear previous error
        self.updated_at = datetime.datetime.utcnow() # Mark as updated

        if not self.description:
            self.status = self.STATUS_FAILED
            self.error_message = "Task description is empty, cannot assess."
            self.phase = None # No further phase progression.
            logger.error(f"Task {self.id} (domain) assessment failed: {self.error_message}")
            return

        # Retrieve the appropriate prompt template.
        prompt_text = get_prompt("assess_task_v1", task_description=self.description)
        if not prompt_text:
            self.status = self.STATUS_FAILED
            self.error_message = "Failed to retrieve assessment prompt template 'assess_task_v1'."
            self.phase = None
            logger.error(f"Task {self.id} (domain) assessment failed: {self.error_message}")
            return

        # Create an APIRequest instance using the provided factory.
        # 'prompt_type' can be used by the factory to customize the request if needed.
        assessment_request = request_factory.create_request(prompt_type="assessment")

        try:
            # Execute the assessment request (e.g., call an AI model).
            raw_ai_response = assessment_request.execute(prompt_text)

            # Handle cases where the request execution itself indicates an error.
            if raw_ai_response and raw_ai_response.lower().startswith("error:"):
                self.status = self.STATUS_FAILED
                self.error_message = f"Assessment API request failed: {raw_ai_response}"
                self.phase = None
                logger.error(f"Task {self.id} (domain) assessment API error: {self.error_message}")
                return

            # Attempt to parse the AI's response (expected to be JSON).
            try:
                # Basic cleanup: find first '{' and last '}' to extract potential JSON substring.
                # This helps if the AI wraps the JSON in explanatory text.
                json_start = raw_ai_response.find('{')
                json_end = raw_ai_response.rfind('}') + 1
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_str = raw_ai_response[json_start:json_end]
                    assessment_data = json.loads(json_str)
                else:
                    # If no JSON structure is found, raise an error to be caught below.
                    raise json.JSONDecodeError("No JSON object found in AI response.", raw_ai_response, 0)

            except json.JSONDecodeError as e:
                self.status = self.STATUS_FAILED
                self.error_message = f"Failed to parse AI assessment response as JSON: {e}. Response snippet: {raw_ai_response[:200]}..."
                self.phase = None
                logger.error(f"Task {self.id} (domain) assessment JSON parsing error: {self.error_message}")
                return

            # Process the successfully parsed structured assessment data.
            outcome = assessment_data.get("assessment_outcome")
            payload = assessment_data.get("result_payload")
            # reasoning = assessment_data.get("reasoning", "") # Optional: log or store reasoning.

            if outcome == "direct_completion":
                self.status = self.STATUS_COMPLETED
                self.result = str(payload) if payload is not None else "Completed directly by AI assessment."
                self.phase = None # Task is terminal.
                logger.info(f"Task {self.id} assessed for 'direct_completion'. Result: {self.result}")
            elif outcome == "subtask_breakdown":
                if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
                    self.status = self.STATUS_PENDING_SUBTASKS
                    self.suggested_subtasks = payload # Store descriptions for Agent to process.
                    self.phase = None # Parent task waits; Agent will create subtasks.
                    logger.info(f"Task {self.id} assessed for 'subtask_breakdown'. Suggested subtasks: {len(payload)}.")
                else:
                    self.status = self.STATUS_FAILED
                    self.error_message = "AI suggested subtask breakdown, but the 'result_payload' was not a list of strings."
                    self.phase = None
                    logger.error(f"Task {self.id} (domain) assessment error: {self.error_message} Payload type: {type(payload)}")
            elif outcome == "cannot_complete":
                self.status = self.STATUS_FAILED
                self.error_message = str(payload) if payload is not None else "AI assessment: Task cannot be completed."
                self.phase = None # Task is terminal.
                logger.info(f"Task {self.id} assessed as 'cannot_complete'. Reason: {self.error_message}")
            elif outcome == "proceed_to_execution":
                self.status = self.STATUS_EXECUTING
                self.phase = self.PHASE_EXECUTION
                # Assessment indicates standard execution is possible.
                # An execution request (e.g. a default one) is added.
                # The payload from AI could potentially configure this request in more advanced scenarios.
                execution_request = request_factory.create_request(prompt_type="execution")
                self.add_request(execution_request)
                logger.info(f"Task {self.id} assessed to 'proceed_to_execution'. Added 1 execution request.")
            else: # Handle unknown or missing outcome.
                self.status = self.STATUS_FAILED
                self.error_message = f"Unknown or missing 'assessment_outcome' from AI: '{outcome}'. Full response: {assessment_data}"
                self.phase = None
                logger.error(f"Task {self.id} (domain) assessment error: {self.error_message}")

        except Exception as e: # Catch any other unexpected error during the assessment process.
            self.status = self.STATUS_FAILED
            self.error_message = f"An unexpected error occurred during AI assessment: {str(e)}"
            self.phase = None
            logger.error(f"Task {self.id} (domain) critical error during assessment: {self.error_message}", exc_info=True)

        logger.info(f"Task {self.id} (domain) assessment final outcome: Status='{self.status}', Phase='{self.phase}'")


    def execute(self, request_factory: RequestFactory) -> None:
        """
        Executes the primary action of the task, typically involving an API call
        using a request object from `self.requests`.

        This method is called when the task is in the `PHASE_EXECUTION`.
        It processes the first request in `self.requests`. The `assess` method should
        have populated `self.requests` if this phase was determined by AI.
        The `request_factory` parameter is available for consistency or if `execute`
        needs to dynamically create further requests, though not used in the current basic implementation.

        Updates `self.result` or `self.error_message` and transitions to `PHASE_RECONCILIATION`.
        Persistence is handled externally.

        Args:
            request_factory: A RequestFactory instance.
        """
        if self.phase != self.PHASE_EXECUTION:
            logger.warning(f"Task {self.id} cannot run execute. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) executing.")
        self.status = self.STATUS_EXECUTING
        self.updated_at = datetime.datetime.utcnow()

        if not self.requests:
            logger.warning(f"Task {self.id} is in execution phase but has no requests. This might indicate an issue in prior assessment logic if requests were expected. Moving to reconciliation.")
            self.phase = self.PHASE_RECONCILIATION
            self.result = "No execution requests were available; task proceeded to reconciliation."
            return

        current_request = self.requests[0] # Process the first request.

        try:
            api_result = current_request.execute(self.description)
            self.result = api_result
            if isinstance(api_result, str) and api_result.lower().startswith("error:"):
                self.error_message = api_result
            else:
                self.error_message = None # Clear previous errors on successful execution.
        except Exception as e:
            logger.error(f"Task {self.id} (domain) execution API error: {e}", exc_info=True)
            self.error_message = f"Unexpected error during task execution API call: {str(e)}"
            self.result = None

        self.phase = self.PHASE_RECONCILIATION


    def reconcile(self) -> None:
        """
        Reconciles the task's final status after assessment, execution, or subtask processing.

        If the task was `PENDING_SUBTASKS`, it checks the status of `self.subtasks`
        (which must be populated externally before calling this method).
        - If any subtask failed, the parent task is marked `FAILED`.
        - If all subtasks completed, the parent task status becomes `PENDING` and phase `ASSESSMENT`
          for re-evaluation or finalization.
        - If subtasks are still pending, the parent remains `PENDING_SUBTASKS` and in `PHASE_RECONCILIATION`.

        If not primarily driven by subtasks, it finalizes status based on `self.result` or
        `self.error_message` (populated by `assess` or `execute`).
        A terminal status (`COMPLETED` or `FAILED`) will set `phase` to `None`.
        Persistence of changes is handled externally.
        """
        if self.phase != self.PHASE_RECONCILIATION:
            logger.warning(f"Task {self.id} cannot run reconcile. Current phase: {self.phase}, Status: {self.status}")
            return

        logger.info(f"Task {self.id} (domain) reconciling. In-memory subtasks: {len(self.subtasks)}")
        self.updated_at = datetime.datetime.utcnow()

        initial_status_for_reconcile = self.status # To understand entry state for some logic paths.

        if initial_status_for_reconcile == self.STATUS_PENDING_SUBTASKS:
            # Logic for handling subtask completion status.
            # Assumes self.subtasks (list of DomainTask objects) has been populated by the caller.
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

    def process_current_phase(self, request_factory: RequestFactory) -> None: # Added request_factory
        """Processes the current phase of the task by calling internal phase methods.
           Modifies state in-memory. Persistence is handled by caller (Agent/ModelService).
           Args:
               request_factory: A RequestFactory instance to be passed to phase methods if they need to create APIRequests.
        """
        logger.debug(f"Task {self.id} (domain) processing phase '{self.phase}' (Status: '{self.status}')")
        current_phase_before_call = self.phase
        current_status_before_call = self.status

        if self.phase == self.PHASE_ASSESSMENT: self.assess(request_factory) # Pass factory
        elif self.phase == self.PHASE_EXECUTION:
            if self.status == self.STATUS_PENDING_SUBTASKS: # Should have been outcome of assess
                logger.info(f"Task {self.id} is {self.STATUS_PENDING_SUBTASKS}. Switching to reconcile phase.")
                self.phase = self.PHASE_RECONCILIATION
                # Agent will save this change and then call process_current_phase again.
                # Or, directly call reconcile if the pattern is single call, multiple internal transitions.
                self.reconcile() # Let reconcile handle PENDING_SUBTASKS
            else: self.execute(request_factory) # Pass factory
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
