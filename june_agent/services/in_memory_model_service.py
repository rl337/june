import uuid
import datetime
import copy # For deepcopying objects to simulate DB detachment
from typing import List, Optional, Dict, Any

from june_agent.services.model_service_interface import ModelServiceAbc # Updated import
from june_agent.models_v2.pydantic_models import (
    InitiativeSchema, InitiativeCreate, InitiativeUpdate,
    TaskSchema, TaskCreate, TaskUpdate
)
# The InMemory service will also need to interact with domain objects if ModelService methods expect/return them
# For now, let's assume it stores and returns Pydantic Schemas primarily,
# and methods like get_task_domain_object will require a conversion step if used.
# Or, it directly stores domain objects if the interface dictates that for some methods.
# The current interface uses Pydantic schemas for most I/O.
# get_task_domain_object and get_processable_tasks_domain_objects are exceptions.
# For these, we'll need the domain Task class.
from june_agent.task import Task as DomainTask # Import the domain Task class

class InMemoryModelService(ModelServiceAbc): # Updated inheritance
    """
    In-memory implementation of the ModelServiceAbc interface.
    This service stores data in dictionaries and is primarily used for testing
    or simple deployments without a persistent database.
    It simulates database operations like CRUD and relationships.
    Note: `deepcopy` is used to simulate object detachment as if from a DB session.
    """
    def __init__(self):
        """Initializes the in-memory stores for initiatives and tasks."""
        self._initiatives: Dict[str, InitiativeSchema] = {}
        self._tasks: Dict[str, TaskSchema] = {} # Stores TaskSchema instances.

    # --- Initiative Methods ---
    def create_initiative(self, initiative_create: InitiativeCreate) -> InitiativeSchema:
        """
        Creates a new initiative in memory.
        Args:
            initiative_create: Pydantic model with new initiative data.
        Returns:
            The created initiative as a Pydantic schema.
        """
        initiative_id = uuid.uuid4().hex
        now = datetime.datetime.utcnow()
        initiative = InitiativeSchema(
            id=initiative_id,
            created_at=now,
            updated_at=now,
            task_ids=[], # Initially no tasks
            **initiative_create.model_dump()
        )
        self._initiatives[initiative_id] = copy.deepcopy(initiative)
        return copy.deepcopy(initiative)

    def get_initiative(self, initiative_id: str) -> Optional[InitiativeSchema]:
        """Retrieves an initiative by ID from memory."""
        initiative = self._initiatives.get(initiative_id)
        return copy.deepcopy(initiative) if initiative else None

    def get_all_initiatives(self, skip: int = 0, limit: int = 100) -> List[InitiativeSchema]:
        """Retrieves all initiatives from memory, with pagination."""
        # Sort by created_at descending to mimic typical DB order for "latest first".
        all_inits = sorted(list(self._initiatives.values()), key=lambda i: i.created_at, reverse=True)
        return [copy.deepcopy(i) for i in all_inits[skip : skip + limit]]

    def update_initiative(self, initiative_id: str, initiative_update: InitiativeUpdate) -> Optional[InitiativeSchema]:
        """Updates an existing initiative in memory."""
        if initiative_id not in self._initiatives:
            return None

        stored_initiative = self._initiatives[initiative_id]
        update_data = initiative_update.model_dump(exclude_unset=True)

        updated_initiative_data = stored_initiative.model_dump()
        updated_initiative_data.update(update_data)
        updated_initiative_data['updated_at'] = datetime.datetime.utcnow()

        # Re-validate with InitiativeSchema to ensure type consistency if needed, or just update fields
        updated_schema = InitiativeSchema(**updated_initiative_data)
        self._initiatives[initiative_id] = copy.deepcopy(updated_schema)
        return copy.deepcopy(updated_schema)

    def delete_initiative(self, initiative_id: str) -> bool:
        """
        Deletes an initiative from memory and cascades to its tasks.
        """
        if initiative_id in self._initiatives:
            del self._initiatives[initiative_id]
            # Also delete associated tasks (cascade behavior)
            tasks_to_delete = [tid for tid, task in self._tasks.items() if task.initiative_id == initiative_id]
            for tid in tasks_to_delete:
                del self._tasks[tid]
            return True
        return False

    # --- Task Methods ---
    def create_task(self, task_create: TaskCreate, initiative_id: str) -> TaskSchema:
        if initiative_id not in self._initiatives:
            raise ValueError(f"Initiative with ID {initiative_id} not found.")

        task_id = uuid.uuid4().hex
        now = datetime.datetime.utcnow()
        task = TaskSchema(
            id=task_id,
            created_at=now,
            updated_at=now,
            subtask_ids=[],
            initiative_id=initiative_id, # Explicitly use the passed initiative_id
            **(task_create.model_dump(exclude={'initiative_id'})) # Exclude initiative_id from the dict
        )
        self._tasks[task_id] = copy.deepcopy(task)

        # Add task_id to the parent initiative's task_ids list.
        if initiative_id in self._initiatives:
            self._initiatives[initiative_id].task_ids.append(task_id)
            self._initiatives[initiative_id].updated_at = now

        # If task has a parent_task_id, add this task's ID to parent's subtask_ids list.
        if task.parent_task_id and task.parent_task_id in self._tasks:
            parent_task_schema = self._tasks[task.parent_task_id]
            if task_id not in parent_task_schema.subtask_ids: # Avoid duplicates
                parent_task_schema.subtask_ids.append(task_id)
                parent_task_schema.updated_at = now

        return copy.deepcopy(task)

    def get_task(self, task_id: str) -> Optional[TaskSchema]:
        """Retrieves a task by ID from memory as a Pydantic schema."""
        task = self._tasks.get(task_id)
        return copy.deepcopy(task) if task else None

    def _task_schema_to_domain(self, schema: TaskSchema) -> DomainTask:
        """
        Converts a TaskSchema (Pydantic) to a DomainTask (pure Python object).
        This helper is used when domain logic needs to be applied.
        Subtasks are not recursively converted here; handled by calling logic if needed.
        """
        # Assumes DomainTask constructor matches these fields or can accept them.
        # The DomainTask's __init__ was refactored to accept these.
        domain_task = DomainTask(
            description=schema.description,
            task_id=schema.id,
            initiative_id=schema.initiative_id,
            parent_task_id=schema.parent_task_id,
            status=schema.status,
            phase=schema.phase,
            result=schema.result,
            error_message=schema.error_message,
            created_at=schema.created_at,
            updated_at=schema.updated_at,
            # `requests` are ephemeral to the domain object, not stored in TaskSchema.
            # `subtasks` (as domain objects) are populated by calling logic if needed.
        )
        return domain_task

    def _domain_task_to_schema(self, domain_obj: DomainTask) -> TaskSchema:
        """
        Converts a DomainTask (pure Python object) to a TaskSchema (Pydantic).
        This uses the DomainTask's own `to_pydantic_schema` method.
        """
        # The DomainTask.to_pydantic_schema() method was refactored to not require a db session.
        # It populates subtask_ids from its internal list of domain subtask objects.
        return domain_obj.to_pydantic_schema()

    def get_task_domain_object(self, task_id: str) -> Optional[DomainTask]:
        task_schema = self._tasks.get(task_id)
        if task_schema:
            # Convert schema to domain object.
            domain_task = self._task_schema_to_domain(copy.deepcopy(task_schema))
            # Populate domain_task.subtasks with domain objects.
            # This ensures the domain object has its children for any internal logic.
            sub_schemas = [self.get_task(sub_id) for sub_id in task_schema.subtask_ids if self.get_task(sub_id)]
            domain_task.subtasks = [self._task_schema_to_domain(copy.deepcopy(ss)) for ss in sub_schemas if ss is not None]
            return domain_task
        return None

    def get_all_tasks(self, initiative_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[TaskSchema]:
        """Retrieves tasks from memory, optionally filtered by initiative_id, with pagination."""
        filtered_tasks: List[TaskSchema]
        if initiative_id:
            # Ensure initiative exists before trying to access its task_ids.
            # However, tasks store initiative_id directly, so we can filter on that.
            if initiative_id not in self._initiatives:
                # Depending on strictness, could return empty list or raise error.
                # Interface implies empty list is fine.
                return []
            filtered_tasks = [task_schema for task_schema in self._tasks.values() if task_schema.initiative_id == initiative_id]
        else:
            filtered_tasks = list(self._tasks.values())

        # Sort by created_at ascending.
        sorted_tasks = sorted(filtered_tasks, key=lambda t: t.created_at)
        return [copy.deepcopy(t) for t in sorted_tasks[skip : skip + limit]]

    def get_processable_tasks_domain_objects(self) -> List[DomainTask]:
        """
        Retrieves processable tasks as domain objects from memory.
        A task is processable if its phase is assessment, execution, or reconciliation,
        or its status is pending_subtasks.
        Subtasks for each processable task are also converted to domain objects.
        """
        processable_schemas = []
        for task_schema in self._tasks.values():
            if (task_schema.phase in [DomainTask.PHASE_ASSESSMENT, DomainTask.PHASE_EXECUTION, DomainTask.PHASE_RECONCILIATION]) or \
               (task_schema.status == DomainTask.STATUS_PENDING_SUBTASKS):
                processable_schemas.append(task_schema)

        # Sort by updated_at to process tasks that haven't been touched recently first.
        sorted_schemas = sorted(processable_schemas, key=lambda t: t.updated_at)

        domain_objects = []
        for schema in sorted_schemas:
            domain_obj = self._task_schema_to_domain(copy.deepcopy(schema))
            # Populate domain_obj.subtasks with domain objects for reconciliation logic
            sub_ids = schema.subtask_ids
            domain_obj.subtasks = [] # Ensure it's an empty list before populating
            for sub_id in sub_ids:
                sub_task_schema = self.get_task(sub_id) # Fetches a deepcopy
                if sub_task_schema:
                     domain_obj.subtasks.append(self._task_schema_to_domain(sub_task_schema))
            domain_objects.append(domain_obj)
        return domain_objects


    def update_task(self, task_id: str, task_update: TaskUpdate) -> Optional[TaskSchema]:
        """Updates an existing task in memory."""
        if task_id not in self._tasks:
            return None

        stored_task_schema = self._tasks[task_id]
        update_data = task_update.model_dump(exclude_unset=True)

        # Create a new schema by merging old data with update_data
        updated_task_data = stored_task_schema.model_dump()
        updated_task_data.update(update_data)
        updated_task_data['updated_at'] = datetime.datetime.utcnow() # Update timestamp

        # Re-validate with TaskSchema to ensure type consistency and apply defaults if any change logic
        updated_schema = TaskSchema(**updated_task_data)
        self._tasks[task_id] = copy.deepcopy(updated_schema)
        return copy.deepcopy(updated_schema)

    def save_task_domain_object(self, task_domain_obj: DomainTask) -> TaskSchema:
        """
        Saves a DomainTask object's state to the in-memory store.
        This involves converting the domain object to its Pydantic schema representation.
        """
        # Convert domain object to schema. This schema should have updated timestamps.
        task_schema_to_save = self._domain_task_to_schema(task_domain_obj)
        # Ensure updated_at is current for this save operation. Domain object should manage this.
        task_schema_to_save.updated_at = task_domain_obj.updated_at

        # If it's a new task (ID not seen before), ensure created_at is also set.
        if task_schema_to_save.id not in self._tasks:
             task_schema_to_save.created_at = task_domain_obj.created_at

        self._tasks[task_schema_to_save.id] = copy.deepcopy(task_schema_to_save)

        # Update initiative's task list if this task is newly associated or re-associated
        if task_schema_to_save.initiative_id and task_schema_to_save.initiative_id in self._initiatives:
            initiative = self._initiatives[task_schema_to_save.initiative_id]
            if task_schema_to_save.id not in initiative.task_ids:
                initiative.task_ids.append(task_schema_to_save.id)
                initiative.updated_at = datetime.datetime.utcnow()

        # Update parent task's subtask list if this task is a subtask and newly associated
        if task_schema_to_save.parent_task_id and task_schema_to_save.parent_task_id in self._tasks:
            parent_task = self._tasks[task_schema_to_save.parent_task_id]
            if task_schema_to_save.id not in parent_task.subtask_ids:
                parent_task.subtask_ids.append(task_schema_to_save.id)
                parent_task.updated_at = datetime.datetime.utcnow()

        return copy.deepcopy(task_schema_to_save)


    def delete_task(self, task_id: str) -> bool:
        """Deletes a task from memory, including its subtasks and references."""
        if task_id in self._tasks:
            task_to_delete = self._tasks[task_id] # Get schema before deleting

            # Remove from parent initiative's task_ids list
            if task_to_delete.initiative_id and task_to_delete.initiative_id in self._initiatives:
                try:
                    self._initiatives[task_to_delete.initiative_id].task_ids.remove(task_id)
                    self._initiatives[task_to_delete.initiative_id].updated_at = datetime.datetime.utcnow()
                except ValueError:
                    pass # Not in list, ignore

            # Delete subtasks recursively (cascade behavior)
            if hasattr(task_to_delete, 'subtask_ids') and task_to_delete.subtask_ids:
                sub_ids_to_delete = list(task_to_delete.subtask_ids)
                for sub_id in sub_ids_to_delete:
                    self.delete_task(sub_id) # Recursive call will handle parent updates

            # Also remove from its own parent's subtask_ids list if it was a subtask
            if task_to_delete.parent_task_id and task_to_delete.parent_task_id in self._tasks:
                parent_task_schema = self._tasks[task_to_delete.parent_task_id]
                if task_id in parent_task_schema.subtask_ids:
                    parent_task_schema.subtask_ids.remove(task_id)
                    parent_task_schema.updated_at = datetime.datetime.utcnow()

            del self._tasks[task_id]
            return True
        return False

    def get_subtasks_for_task_domain_objects(self, parent_task_id: str) -> List[DomainTask]:
        """Retrieves subtasks for a parent task ID as domain objects."""
        parent_task_schema = self.get_task(parent_task_id) # This returns a deepcopy
        if not parent_task_schema:
            return []

        sub_domain_tasks = []
        for sub_id in parent_task_schema.subtask_ids:
            sub_schema = self.get_task(sub_id) # This also returns a deepcopy
            if sub_schema:
                # Convert schema to domain, no need to deepcopy schema again as get_task does it
                sub_domain_tasks.append(self._task_schema_to_domain(sub_schema))
        return sub_domain_tasks


    def ensure_initial_data(self, default_initiative_id: str, default_task_id: str) -> None:
        """Ensures default initiative and task exist in memory."""
        if not self.get_initiative(default_initiative_id):
            init_create = InitiativeCreate(
                name="Main Agent Initiative (InMem)",
                description="Default in-memory initiative.",
                status="active"
            )
            now = datetime.datetime.utcnow()
            default_init = InitiativeSchema(
                id=default_initiative_id,
                created_at=now, updated_at=now, task_ids=[], **init_create.model_dump()
            )
            self._initiatives[default_initiative_id] = default_init
            print(f"InMemory: Created default initiative {default_initiative_id}")

        if not self.get_task(default_task_id):
            # TaskCreate needs initiative_id for its own validation if strict,
            # but InMemory service's create_task uses the separate initiative_id param primarily.
            # The TaskCreate.initiative_id is optional and might be None.
            task_create_dto = TaskCreate(
                description="Default task: Assess objectives (InMem)",
                status=DomainTask.STATUS_PENDING,
                phase=DomainTask.PHASE_ASSESSMENT,
                # initiative_id=default_initiative_id # This field is in TaskBase, so it's fine here
            )
            # The create_task method will associate it with default_initiative_id
            self.create_task(task_create_dto, initiative_id=default_initiative_id)
            # We need to ensure the task created by self.create_task has the ID default_task_id.
            # Current self.create_task auto-generates ID. This needs adjustment for specific ID.

            # Manual creation for specific ID:
            if default_task_id in self._tasks: # If create_task somehow made it with a different ID
                # This path is unlikely if create_task was just called for a non-existent task
                pass
            else: # create_task didn't create it with this ID, or it failed. Let's create manually.
                # Remove if create_task made one with a different ID but same content
                # This logic is getting complicated, ensure_initial_data should be simpler for InMemory
                # For now, let's assume we can just overwrite or create with specific ID

                # Re-check after create_task, if it's there with the right ID, fine.
                # This part needs refinement if create_task can't take an ID.
                # For now, let's assume we need to ensure the task with default_task_id exists.
                # The create_task method adds to _tasks. If we want a specific ID, we should
                # modify create_task or do it manually here for ensure_initial_data.

                # Manual creation with specific ID for simplicity in ensure_initial_data:
                task_schema = TaskSchema(
                    id=default_task_id,
                    description="Default task: Assess objectives (InMem)",
                    status=DomainTask.STATUS_PENDING,
                    phase=DomainTask.PHASE_ASSESSMENT,
                    initiative_id=default_initiative_id,
                    created_at=datetime.datetime.utcnow(),
                    updated_at=datetime.datetime.utcnow(),
                    subtask_ids=[]
                )
                self._tasks[default_task_id] = task_schema
                if default_initiative_id in self._initiatives:
                    if default_task_id not in self._initiatives[default_initiative_id].task_ids:
                        self._initiatives[default_initiative_id].task_ids.append(default_task_id)
                print(f"InMemory: Ensured default task {default_task_id}")


    def get_total_initiatives_count(self) -> int:
        """Returns the total number of initiatives in memory."""
        return len(self._initiatives)

    def get_task_counts_by_status(self) -> Dict[str, int]:
        """Returns a dictionary with task counts by status from memory."""
        counts: Dict[str, int] = {}
        # Initialize all possible statuses to 0 using DomainTask constants.
        statuses_to_count = [
            DomainTask.STATUS_PENDING, DomainTask.STATUS_ASSESSING,
            DomainTask.STATUS_EXECUTING, DomainTask.STATUS_RECONCILING,
            DomainTask.STATUS_PENDING_SUBTASKS, DomainTask.STATUS_COMPLETED,
            DomainTask.STATUS_FAILED
        ]
        for status_val in statuses_to_count:
            counts[status_val] = 0

        # Count tasks by their status.
        for task_schema in self._tasks.values():
            if task_schema.status in counts: # Should always be true due to initialization
                counts[task_schema.status] += 1
            # else: # This case should ideally not be reached if statuses_to_count is comprehensive
            #     logger.warning(f"Task {task_schema.id} has unknown status '{task_schema.status}'")
            #     counts[task_schema.status] = 1
        return counts
            status=domain_obj.status,
            phase=domain_obj.phase,
            result=domain_obj.result,
            error_message=domain_obj.error_message,
            initiative_id=domain_obj.initiative_id,
            parent_task_id=domain_obj.parent_task_id,
            created_at=domain_obj.created_at,
            updated_at=domain_obj.updated_at,
            subtask_ids=[st.id for st in domain_obj.subtasks] # Assuming subtasks are domain objects
        )

    def get_task_domain_object(self, task_id: str) -> Optional[DomainTask]:
        task_schema = self._tasks.get(task_id)
        if task_schema:
            # Convert schema to domain object. This requires DomainTask class.
            # And potentially its subtasks if domain object expects them.
            domain_task = self._task_schema_to_domain(copy.deepcopy(task_schema))
            # Load subtasks for the domain object
            sub_schemas = [self.get_task(sub_id) for sub_id in task_schema.subtask_ids if self.get_task(sub_id)]
            domain_task.subtasks = [self._task_schema_to_domain(copy.deepcopy(ss)) for ss in sub_schemas if ss is not None]
            return domain_task
        return None

    def get_all_tasks(self, initiative_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[TaskSchema]:
        filtered_tasks = []
        if initiative_id:
            if initiative_id not in self._initiatives: return [] # No such initiative
            # This checks self._initiatives[initiative_id].task_ids
            # Or iterate all tasks and filter by task.initiative_id
            for task_id, task_schema in self._tasks.items():
                if task_schema.initiative_id == initiative_id:
                    filtered_tasks.append(task_schema)
        else:
            filtered_tasks = list(self._tasks.values())

        sorted_tasks = sorted(filtered_tasks, key=lambda t: t.created_at)
        return [copy.deepcopy(t) for t in sorted_tasks[skip : skip + limit]]

    def get_processable_tasks_domain_objects(self) -> List[DomainTask]:
        processable_schemas = []
        for task_schema in self._tasks.values():
            if (task_schema.phase in [DomainTask.PHASE_ASSESSMENT, DomainTask.PHASE_EXECUTION, DomainTask.PHASE_RECONCILIATION]) or \
               (task_schema.status == DomainTask.STATUS_PENDING_SUBTASKS):
                processable_schemas.append(task_schema)

        sorted_schemas = sorted(processable_schemas, key=lambda t: t.updated_at) # Process oldest first

        domain_objects = []
        for schema in sorted_schemas:
            # Convert to domain object, including subtasks for reconciliation logic
            domain_obj = self._task_schema_to_domain(copy.deepcopy(schema))
            sub_ids = schema.subtask_ids
            domain_obj.subtasks = []
            for sub_id in sub_ids:
                sub_task_schema = self.get_task(sub_id)
                if sub_task_schema:
                     # Recursive call to _task_schema_to_domain for subtasks
                     domain_obj.subtasks.append(self._task_schema_to_domain(copy.deepcopy(sub_task_schema)))
            domain_objects.append(domain_obj)
        return domain_objects


    def update_task(self, task_id: str, task_update: TaskUpdate) -> Optional[TaskSchema]:
        if task_id not in self._tasks:
            return None

        stored_task_schema = self._tasks[task_id]
        update_data = task_update.model_dump(exclude_unset=True)

        updated_task_data = stored_task_schema.model_dump()
        updated_task_data.update(update_data)
        updated_task_data['updated_at'] = datetime.datetime.utcnow()

        updated_schema = TaskSchema(**updated_task_data)
        self._tasks[task_id] = copy.deepcopy(updated_schema)
        return copy.deepcopy(updated_schema)

    def save_task_domain_object(self, task_domain_obj: DomainTask) -> TaskSchema:
        # Convert domain object to schema and store/update
        task_schema_to_save = self._domain_task_to_schema(task_domain_obj)
        task_schema_to_save.updated_at = datetime.datetime.utcnow() # Ensure timestamp is fresh

        # If it's a new task, ensure created_at is set (should be by domain obj init)
        if task_schema_to_save.id not in self._tasks:
             task_schema_to_save.created_at = task_schema_to_save.created_at or datetime.datetime.utcnow()

        self._tasks[task_schema_to_save.id] = copy.deepcopy(task_schema_to_save)

        # Update initiative's task list if this task is new to it
        if task_schema_to_save.initiative_id and task_schema_to_save.initiative_id in self._initiatives:
            initiative = self._initiatives[task_schema_to_save.initiative_id]
            if task_schema_to_save.id not in initiative.task_ids:
                initiative.task_ids.append(task_schema_to_save.id)
                initiative.updated_at = datetime.datetime.utcnow()

        # Handle subtasks: if domain object's subtasks list changed, reflect in storage
        # This part can get complex for an in-memory store if deep saves are expected.
        # For now, assume subtasks are saved via their own save_task_domain_object calls.
        # The parent's subtask_ids list in its schema should be accurate.

        return copy.deepcopy(task_schema_to_save)


    def delete_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            task_to_delete = self._tasks[task_id]
            # Remove from initiative's task_ids list
            if task_to_delete.initiative_id and task_to_delete.initiative_id in self._initiatives:
                try:
                    self._initiatives[task_to_delete.initiative_id].task_ids.remove(task_id)
                except ValueError:
                    pass # Not in list, ignore

            # Delete subtasks recursively (cascade behavior)
            if hasattr(task_to_delete, 'subtask_ids') and task_to_delete.subtask_ids:
                sub_ids_to_delete = list(task_to_delete.subtask_ids) # Iterate over a copy
                for sub_id in sub_ids_to_delete:
                    self.delete_task(sub_id) # Recursive call

            # Also remove from parent's subtask_ids list if it's a subtask
            if task_to_delete.parent_task_id and task_to_delete.parent_task_id in self._tasks:
                parent_task_schema = self._tasks[task_to_delete.parent_task_id]
                if task_id in parent_task_schema.subtask_ids:
                    parent_task_schema.subtask_ids.remove(task_id)
                    parent_task_schema.updated_at = datetime.datetime.utcnow()


            del self._tasks[task_id]
            return True
        return False

    def get_subtasks_for_task_domain_objects(self, parent_task_id: str) -> List[DomainTask]:
        parent_task_schema = self.get_task(parent_task_id)
        if not parent_task_schema:
            return []

        sub_domain_tasks = []
        for sub_id in parent_task_schema.subtask_ids:
            sub_schema = self.get_task(sub_id)
            if sub_schema:
                sub_domain_tasks.append(self._task_schema_to_domain(copy.deepcopy(sub_schema)))
        return sub_domain_tasks


    def ensure_initial_data(self, default_initiative_id: str, default_task_id: str) -> None:
        if not self.get_initiative(default_initiative_id):
            init_create = InitiativeCreate(
                name="Main Agent Initiative (InMem)",
                description="Default in-memory initiative.",
                status="active"
            )
            # To ensure specific ID, we need to adapt create_initiative or set it manually
            now = datetime.datetime.utcnow()
            default_init = InitiativeSchema(
                id=default_initiative_id,
                created_at=now, updated_at=now, task_ids=[], **init_create.model_dump()
            )
            self._initiatives[default_initiative_id] = default_init
            print(f"InMemory: Created default initiative {default_initiative_id}")

        if not self.get_task(default_task_id):
            task_create = TaskCreate(
                description="Default task: Assess objectives (InMem)",
                status=DomainTask.STATUS_PENDING, # Use constants from DomainTask for status/phase
                phase=DomainTask.PHASE_ASSESSMENT,
                initiative_id=default_initiative_id # Set this correctly
            )
            # Similar to initiative, ensure specific ID for task
            now = datetime.datetime.utcnow()
            default_task = TaskSchema(
                id=default_task_id,
                created_at=now, updated_at=now, subtask_ids=[],
                **(task_create.model_dump(exclude={'initiative_id'})), # Exclude from dict
            )
            # Ensure initiative_id is correctly set on the TaskSchema object (already passed to TaskCreate)
            default_task.initiative_id = default_initiative_id

            self._tasks[default_task_id] = default_task
            # Add to initiative's task list
            if default_initiative_id in self._initiatives:
                 self._initiatives[default_initiative_id].task_ids.append(default_task_id)
            print(f"InMemory: Created default task {default_task_id}")

    def get_total_initiatives_count(self) -> int:
        return len(self._initiatives)

    def get_task_counts_by_status(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        # Initialize all possible statuses to 0
        statuses_to_count = [
            DomainTask.STATUS_PENDING, DomainTask.STATUS_ASSESSING,
            DomainTask.STATUS_EXECUTING, DomainTask.STATUS_RECONCILING,
            DomainTask.STATUS_PENDING_SUBTASKS, DomainTask.STATUS_COMPLETED,
            DomainTask.STATUS_FAILED
        ]
        for status_val in statuses_to_count:
            counts[status_val] = 0

        for task_schema in self._tasks.values():
            if task_schema.status in counts:
                counts[task_schema.status] += 1
            else: # Should not happen if statuses_to_count is comprehensive
                counts[task_schema.status] = 1
        return counts
