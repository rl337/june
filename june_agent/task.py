import uuid
import logging
import datetime # For datetime objects

# SQLAlchemy imports
from sqlalchemy.orm import Session, joinedload, selectinload
from june_agent.models_v2.orm_models import TaskORM, InitiativeORM # TaskORM for self, InitiativeORM for linking
from june_agent.models_v2.pydantic_models import TaskSchema, TaskCreate, TaskUpdate # Pydantic models

# Request handling (remains the same for now)
from .request import APIRequest, TogetherAIRequest

# Imports that might be needed by Pydantic models if they have complex types
from typing import Optional, List

logger = logging.getLogger(__name__)

class Task: # Acts as a domain model, interacts with TaskORM for persistence
    # Status and Phase constants remain the same
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
                 created_at: datetime.datetime | None = None,
                 updated_at: datetime.datetime | None = None,
                 # ORM instance can be passed if reconstructing from DB, not for new instances
                 _orm_obj: Optional[TaskORM] = None):

        self.id: str = task_id if task_id else uuid.uuid4().hex
        self.description: str = description
        self.initiative_id: str | None = initiative_id
        self.parent_task_id: str | None = parent_task_id
        self.status: str = status
        self.phase: str | None = phase
        self.result: str | None = result
        self.error_message: str | None = error_message

        # Timestamps are datetime objects now
        self.created_at: datetime.datetime = created_at if created_at else datetime.datetime.utcnow()
        self.updated_at: datetime.datetime = updated_at if updated_at else self.created_at

        self.requests: list[APIRequest] = []
        self.subtasks: list[Task] = [] # Holds domain Task objects

        # Store the ORM object if this Task instance is a representation of persisted data
        # This is one way to bridge domain model and ORM instance; alternatives exist.
        self._orm_obj_cache: Optional[TaskORM] = _orm_obj

        logger.info(f"Task domain model {'initialized' if not _orm_obj else 'reconstructed'} for ID: {self.id}")

    def _to_orm(self, db_task_orm: Optional[TaskORM] = None) -> TaskORM:
        """Converts this domain Task to a TaskORM object (new or existing)."""
        if db_task_orm is None: # Creating a new ORM object
            db_task_orm = TaskORM(id=self.id)

        # Update attributes from domain model
        db_task_orm.description = self.description
        db_task_orm.initiative_id = self.initiative_id
        db_task_orm.parent_task_id = self.parent_task_id
        db_task_orm.status = self.status
        db_task_orm.phase = self.phase
        db_task_orm.result = self.result
        db_task_orm.error_message = self.error_message

        # Timestamps: created_at is set on new ORM obj by default.
        # updated_at is set by onupdate or manually here if needed before commit.
        # If creating new, ORM default for created_at is used.
        # If updating, ORM onupdate for updated_at is used.
        if self.id == db_task_orm.id: # Ensure we are not overwriting a different task's ORM
             db_task_orm.created_at = self.created_at # Preserve original created_at for existing
        db_task_orm.updated_at = datetime.datetime.utcnow() # Explicitly set for save

        return db_task_orm

    @classmethod
    def _from_orm(cls, db_task_orm: TaskORM) -> 'Task':
        """Creates a domain Task instance from a TaskORM object."""
        instance = cls(
            task_id=db_task_orm.id,
            description=db_task_orm.description,
            initiative_id=db_task_orm.initiative_id,
            parent_task_id=db_task_orm.parent_task_id,
            status=db_task_orm.status,
            phase=db_task_orm.phase,
            result=db_task_orm.result,
            error_message=db_task_orm.error_message,
            created_at=db_task_orm.created_at,
            updated_at=db_task_orm.updated_at,
            _orm_obj=db_task_orm # Cache the ORM object
        )
        # Subtasks are not eagerly loaded here by default to avoid deep object graphs.
        # Use load_subtasks_from_orm for that.
        return instance

    def save(self, db: Session) -> None:
        """Saves the current task state to the database using SQLAlchemy."""
        db_task_orm = db.query(TaskORM).filter(TaskORM.id == self.id).first()
        is_new = False
        if not db_task_orm:
            db_task_orm = TaskORM(id=self.id, created_at=self.created_at) # Pass created_at for new
            is_new = True

        # Transfer state from domain model to ORM model
        self._to_orm(db_task_orm) # This updates db_task_orm fields, including updated_at

        if is_new:
            db.add(db_task_orm)
        else:
            # If already managed, SQLAlchemy tracks changes. Explicit add not always needed.
            # However, if it was detached or to be safe:
            db.merge(db_task_orm)

        try:
            db.commit()
            db.refresh(db_task_orm) # Refresh to get DB-generated values like updated_at
            self._orm_obj_cache = db_task_orm # Update cache
            self.updated_at = db_task_orm.updated_at # Sync domain model timestamp
            if is_new:
                 self.created_at = db_task_orm.created_at # Sync if it was DB default
            logger.info(f"Task {self.id} {'saved' if is_new else 'updated'} in the database.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save/update task {self.id}: {e}", exc_info=True)
            raise

    @classmethod
    def get(cls, db: Session, task_id: str) -> Optional['Task']:
        """Loads a task from the database by its ID using SQLAlchemy."""
        # Eagerly load initiative and parent_task if they are frequently accessed after loading a task.
        # Use joinedload for many-to-one. Use selectinload for one-to-many (subtasks).
        db_task_orm = (
            db.query(TaskORM)
            .options(joinedload(TaskORM.initiative), joinedload(TaskORM.parent_task))
            .filter(TaskORM.id == task_id)
            .first()
        )
        if db_task_orm:
            logger.info(f"Task {task_id} loaded from database via ORM.")
            return cls._from_orm(db_task_orm)
        logger.warning(f"Task with ID {task_id} not found via ORM.")
        return None

    @classmethod
    def get_all(cls, db: Session, initiative_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List['Task']:
        """Loads tasks from the database, optionally filtered and with pagination."""
        query = db.query(TaskORM).order_by(TaskORM.created_at.asc())
        if initiative_id:
            query = query.filter(TaskORM.initiative_id == initiative_id)

        db_task_orms = query.offset(skip).limit(limit).all()
        tasks = [cls._from_orm(db_task_orm) for db_task_orm in db_task_orms]
        logger.info(f"Loaded {len(tasks)} tasks via ORM.")
        return tasks

    @classmethod
    def create(cls, db: Session, task_create: TaskCreate, initiative_id: str) -> TaskSchema:
        """Creates a new task in the database via ORM, associated with an initiative."""
        # Verify initiative exists (optional here, can be done by caller, but good for robustness)
        # parent_initiative_orm = db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id).first()
        # if not parent_initiative_orm:
        #     # Or raise an exception
        #     logger.warning(f"Cannot create task, initiative {initiative_id} not found.")
        #     return None # Or raise specific error

        db_task_orm = TaskORM(
            description=task_create.description,
            status=task_create.status, # Pydantic model provides default
            phase=task_create.phase,   # Pydantic model provides default
            result=task_create.result,
            error_message=task_create.error_message,
            initiative_id=initiative_id, # Explicitly passed
            parent_task_id=task_create.parent_task_id
            # id, created_at, updated_at have defaults in ORM model
        )
        db.add(db_task_orm)
        db.commit()
        db.refresh(db_task_orm)
        logger.info(f"Task created with ID: {db_task_orm.id} for initiative {initiative_id}")

        # Convert ORM object to domain object, then to Pydantic schema
        # Alternatively, directly TaskSchema.from_orm(db_task_orm) if TaskSchema is simple enough
        domain_task = cls._from_orm(db_task_orm)
        return domain_task.to_pydantic_schema(db) # Pass db if schema conversion needs it for subtasks etc.

    def load_subtasks_from_orm(self, db: Session) -> None:
        """Loads subtasks for this task from the database using ORM relationships."""
        if not self._orm_obj_cache: # If this domain task doesn't have its ORM counterpart cached
            # Fetch the ORM object for this task, ensuring subtasks are loaded
            db_task_orm_with_subtasks = (
                db.query(TaskORM)
                .options(selectinload(TaskORM.subtasks)) # Eager load subtasks
                .filter(TaskORM.id == self.id)
                .first()
            )
            if not db_task_orm_with_subtasks:
                logger.error(f"Cannot load subtasks for task {self.id}: ORM object not found.")
                self.subtasks = []
                return
            self._orm_obj_cache = db_task_orm_with_subtasks

        # If ORM object is cached or just fetched, its .subtasks relationship should be populated
        # (if eager loaded or accessed causing lazy load)
        self.subtasks = [Task._from_orm(sub_orm) for sub_orm in self._orm_obj_cache.subtasks]
        logger.info(f"Loaded {len(self.subtasks)} subtasks for task {self.id} via ORM.")


    def add_request(self, request_obj: APIRequest) -> None: # No change, in-memory
        if not isinstance(request_obj, APIRequest):
            logger.warning(f"Attempted to add an invalid request object to task {self.id}.")
            return
        self.requests.append(request_obj)
        logger.info(f"Request added to task {self.id}. Total requests: {len(self.requests)}")

    def add_subtask(self, db: Session, subtask_domain_obj: 'Task') -> None:
        """Adds a subtask (domain object) to this task and saves both via ORM."""
        if not isinstance(subtask_domain_obj, Task):
            raise TypeError("Subtask must be an instance of Task domain model.")

        subtask_domain_obj.parent_task_id = self.id
        subtask_domain_obj.initiative_id = self.initiative_id # Inherit initiative

        if subtask_domain_obj not in self.subtasks: # Check against in-memory list
            self.subtasks.append(subtask_domain_obj)

            self.status = self.STATUS_PENDING_SUBTASKS
            self.phase = None # Parent task pauses
            # self.updated_at = datetime.datetime.utcnow() # Handled by save->to_orm

            # Save the new subtask first
            subtask_domain_obj.save(db) # This will create TaskORM for subtask

            # Then save the parent task (its status/phase changed)
            self.save(db)
            logger.info(f"Subtask {subtask_domain_obj.id} added to task {self.id}. Parent status: {self.status}.")
        else:
            logger.warning(f"Subtask {subtask_domain_obj.id} domain object already in parent's list {self.id}.")


    # --- Phase Methods (assess, execute, reconcile, process_current_phase) ---
    # These methods need to call self.save(db) and require a `db: Session` parameter.
    # Their internal logic remains largely the same, but persistence calls are updated.

    def assess(self, db: Session) -> None:
        if self.phase != self.PHASE_ASSESSMENT:
            logger.warning(f"Task {self.id} cannot run assess. Current phase: {self.phase}")
            return
        logger.info(f"Task {self.id} entering assessment phase.")
        self.requests = []
        if not self.description:
            self.status = self.STATUS_FAILED
            self.error_message = "Task description is empty, cannot assess."
            self.phase = None
        else:
            self.add_request(TogetherAIRequest())
            self.phase = self.PHASE_EXECUTION
            self.status = self.STATUS_EXECUTING
        self.save(db) # Pass session

    def execute(self, db: Session) -> None:
        if self.phase != self.PHASE_EXECUTION:
            logger.warning(f"Task {self.id} cannot run execute. Current phase: {self.phase}")
            return
        logger.info(f"Task {self.id} entering execution phase.")
        self.status = self.STATUS_EXECUTING
        if not self.requests:
            self.phase = self.PHASE_RECONCILIATION
            self.save(db)
            return
        current_request = self.requests[0]
        try:
            api_result = current_request.execute(self.description)
            self.result = api_result
            if isinstance(api_result, str) and api_result.lower().startswith("error:"):
                self.error_message = api_result
        except Exception as e:
            self.error_message = f"Unexpected error during execution: {str(e)}"
            self.result = None
        self.phase = self.PHASE_RECONCILIATION
        self.save(db) # Pass session

    def reconcile(self, db: Session) -> None:
        if self.phase != self.PHASE_RECONCILIATION:
            logger.warning(f"Task {self.id} cannot run reconcile. Current phase: {self.phase}")
            return
        logger.info(f"Task {self.id} entering reconciliation phase.")

        if self.status == self.STATUS_PENDING_SUBTASKS:
            self.load_subtasks_from_orm(db) # Ensure subtasks are loaded via ORM
            all_subtasks_completed = True
            failed_subtask = False
            if not self.subtasks: # Should not happen if status is PENDING_SUBTASKS and correctly managed
                logger.warning(f"Task {self.id} is PENDING_SUBTASKS but has no subtasks loaded/found.")
                # This might indicate an issue or that subtasks were deleted.
                # For now, assume if no subtasks, it can proceed with its own reconciliation.
                pass # Fall through to reconcile self as if no subtasks were pending.

            for subtask_domain in self.subtasks:
                if subtask_domain.status != self.STATUS_COMPLETED: all_subtasks_completed = False
                if subtask_domain.status == self.STATUS_FAILED: failed_subtask = True; break

            if failed_subtask:
                self.status = self.STATUS_FAILED
                self.error_message = "One or more subtasks failed."
            elif all_subtasks_completed:
                self.status = self.STATUS_PENDING
                self.phase = self.PHASE_ASSESSMENT
            else: # Not all subtasks done
                self.save(db); return # Exit early

        # Standard reconciliation if not primarily waiting on subtasks or if subtasks completed
        if self.status not in [self.STATUS_PENDING_SUBTASKS, self.STATUS_PENDING, self.STATUS_FAILED]: # Avoid overwriting if already set by subtask logic
            if self.error_message:
                self.status = self.STATUS_FAILED
            elif self.result is not None:
                self.status = self.STATUS_COMPLETED
            else: # No error, no result (e.g. from execute phase with no requests)
                self.status = self.STATUS_COMPLETED

        if self.status == self.STATUS_COMPLETED or self.status == self.STATUS_FAILED:
            self.phase = None

        self.save(db) # Pass session

    def process_current_phase(self, db: Session) -> None:
        logger.debug(f"Processing current phase '{self.phase}' for task {self.id} (status '{self.status}')")
        if self.phase == self.PHASE_ASSESSMENT: self.assess(db)
        elif self.phase == self.PHASE_EXECUTION:
            if self.status == self.STATUS_PENDING_SUBTASKS:
                logger.info(f"Task {self.id} has pending subtasks. Triggering reconcile.")
                self.phase = self.PHASE_RECONCILIATION # Ensure it reconciles next
                self.save(db) # Save phase change
                self.reconcile(db)
                return
            self.execute(db)
        elif self.phase == self.PHASE_RECONCILIATION: self.reconcile(db)
        elif self.status == self.STATUS_PENDING_SUBTASKS and not self.phase:
            logger.info(f"Task {self.id} is pending subtasks. Triggering reconciliation.")
            self.phase = self.PHASE_RECONCILIATION
            self.save(db)
            self.reconcile(db)
        else:
            logger.info(f"Task {self.id} (status '{self.status}', phase '{self.phase}'): No specific action.")


    def to_pydantic_schema(self, db: Optional[Session] = None) -> TaskSchema:
        """Converts this domain Task to its Pydantic TaskSchema representation."""
        sub_ids = []
        if db and self._orm_obj_cache: # If we have a session and ORM object
            # Eagerly load subtask IDs if not already loaded in self.subtasks
            # This ensures subtask_ids in the schema are accurate from DB perspective
            if not self.subtasks and self._orm_obj_cache.subtasks: # ORM has subtasks but domain list is empty
                 sub_ids = [st_orm.id for st_orm in self._orm_obj_cache.subtasks]
            else: # Use domain list if populated, assuming it's fresh or just loaded
                 sub_ids = [st.id for st in self.subtasks]
        elif self.subtasks: # Fallback to in-memory if no DB session
            sub_ids = [st.id for st in self.subtasks]

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
            subtask_ids=sub_ids
        )

# Remove old if __name__ == '__main__' block
# Add imports for Optional, List at the top from typing
# from typing import Optional, List # Already done at the top
