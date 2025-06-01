import uuid
import datetime
import copy # For deepcopying objects to simulate DB detachment
from typing import List, Optional, Dict, Any

from june_agent.services.model_service_interface import IModelService
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
from june_agent.task import Task as DomainTask # Import the domain Task

class InMemoryModelService(IModelService):
    def __init__(self):
        self._initiatives: Dict[str, InitiativeSchema] = {}
        self._tasks: Dict[str, TaskSchema] = {} # Storing TaskSchema for simplicity
        # For methods returning domain objects, we'll convert on the fly or store domain objects.
        # Let's store TaskSchema and convert to/from DomainTask as needed for specific methods.

    # --- Initiative Methods ---
    def create_initiative(self, initiative_create: InitiativeCreate) -> InitiativeSchema:
        initiative_id = uuid.uuid4().hex
        now = datetime.datetime.utcnow()
        initiative = InitiativeSchema(
            id=initiative_id,
            created_at=now,
            updated_at=now,
            task_ids=[], # Initially no tasks
            **initiative_create.dict()
        )
        self._initiatives[initiative_id] = copy.deepcopy(initiative)
        return copy.deepcopy(initiative)

    def get_initiative(self, initiative_id: str) -> Optional[InitiativeSchema]:
        initiative = self._initiatives.get(initiative_id)
        return copy.deepcopy(initiative) if initiative else None

    def get_all_initiatives(self, skip: int = 0, limit: int = 100) -> List[InitiativeSchema]:
        all_inits = sorted(list(self._initiatives.values()), key=lambda i: i.created_at, reverse=True)
        return [copy.deepcopy(i) for i in all_inits[skip : skip + limit]]

    def update_initiative(self, initiative_id: str, initiative_update: InitiativeUpdate) -> Optional[InitiativeSchema]:
        if initiative_id not in self._initiatives:
            return None

        stored_initiative = self._initiatives[initiative_id]
        update_data = initiative_update.dict(exclude_unset=True)

        updated_initiative_data = stored_initiative.dict()
        updated_initiative_data.update(update_data)
        updated_initiative_data['updated_at'] = datetime.datetime.utcnow()

        # Re-validate with InitiativeSchema to ensure type consistency if needed, or just update fields
        updated_schema = InitiativeSchema(**updated_initiative_data)
        self._initiatives[initiative_id] = copy.deepcopy(updated_schema)
        return copy.deepcopy(updated_schema)

    def delete_initiative(self, initiative_id: str) -> bool:
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
            **(task_create.dict(exclude={'initiative_id'})) # Exclude initiative_id from the dict
        )
        self._tasks[task_id] = copy.deepcopy(task)

        # Add task_id to the parent initiative's task_ids list
        if initiative_id in self._initiatives: # Ensure initiative exists
            self._initiatives[initiative_id].task_ids.append(task_id)
            self._initiatives[initiative_id].updated_at = now # Touch initiative

        # If task has a parent_task_id, add this task's ID to parent's subtask_ids
        if task.parent_task_id and task.parent_task_id in self._tasks:
            parent_task_schema = self._tasks[task.parent_task_id]
            if task_id not in parent_task_schema.subtask_ids:
                parent_task_schema.subtask_ids.append(task_id)
                parent_task_schema.updated_at = now # Touch parent task

        return copy.deepcopy(task)

    def get_task(self, task_id: str) -> Optional[TaskSchema]:
        task = self._tasks.get(task_id)
        return copy.deepcopy(task) if task else None

    def _task_schema_to_domain(self, schema: TaskSchema) -> DomainTask:
        # Simplified conversion; real domain Task might need more complex init
        # This assumes DomainTask can be initialized adequately from schema fields.
        # This is a placeholder for the actual conversion logic.
        # The real DomainTask constructor was refactored but might need adjustment
        # if it no longer takes all these fields directly.
        dt = DomainTask(
            description=schema.description,
            task_id=schema.id,
            initiative_id=schema.initiative_id,
            parent_task_id=schema.parent_task_id,
            status=schema.status,
            phase=schema.phase,
            result=schema.result,
            error_message=schema.error_message,
            created_at=schema.created_at,
            updated_at=schema.updated_at
        )
        # If domain task needs its subtasks list populated with domain objects:
        # for sub_id in schema.subtask_ids:
        #    sub_schema = self.get_task(sub_id)
        #    if sub_schema:
        #        dt.subtasks.append(self._task_schema_to_domain(sub_schema))
        return dt

    def _domain_task_to_schema(self, domain_obj: DomainTask) -> TaskSchema:
        # Assumes domain_obj has a to_pydantic_schema method or similar,
        # or we manually construct TaskSchema from domain_obj fields.
        # The current DomainTask has to_pydantic_schema().
        # We need to pass a DB session to it, which InMemory doesn't have.
        # So, manual conversion for InMemory:
        return TaskSchema(
            id=domain_obj.id,
            description=domain_obj.description,
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
        update_data = task_update.dict(exclude_unset=True)

        updated_task_data = stored_task_schema.dict()
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
                created_at=now, updated_at=now, task_ids=[], **init_create.dict()
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
                **task_create.dict() # This will set initiative_id from task_create again
            )
            # Ensure initiative_id is correctly set on the TaskSchema object
            default_task.initiative_id = default_initiative_id

            self._tasks[default_task_id] = default_task
            # Add to initiative's task list
            if default_initiative_id in self._initiatives:
                 self._initiatives[default_initiative_id].task_ids.append(default_task_id)
            print(f"InMemory: Created default task {default_task_id}")
