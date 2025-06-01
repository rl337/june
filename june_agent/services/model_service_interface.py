from abc import ABC, abstractmethod
from typing import List, Optional, Any # Any for now for Pydantic models or dicts

# Forward declare Pydantic models or import them if they don't cause circularity
# For the interface, using 'Any' or specific Dict structures can also work initially.
# Let's assume Pydantic models will be used for data transfer objects (DTOs).
from typing import Dict # Added Dict
from june_agent.models_v2.pydantic_models import (
    InitiativeSchema, InitiativeCreate, InitiativeUpdate,
    TaskSchema, TaskCreate, TaskUpdate
)

class IModelService(ABC):
    """
    Interface defining the contract for a model service.
    A model service provides methods for creating, reading, updating, and deleting (CRUD)
    domain entities (Initiatives and Tasks), abstracting the underlying persistence mechanism.
    It uses Pydantic schemas for data transfer objects (DTOs) in most public methods,
    but may also work with or return pure domain objects for internal agent logic.
    """

    # --- Initiative Methods ---
    @abstractmethod
    def create_initiative(self, initiative_create: InitiativeCreate) -> InitiativeSchema:
        """
        Creates a new initiative.
        Args:
            initiative_create: Pydantic model containing data for the new initiative.
        Returns:
            The created initiative as a Pydantic schema.
        """
        pass

    @abstractmethod
    def get_initiative(self, initiative_id: str) -> Optional[InitiativeSchema]:
        """
        Retrieves an initiative by its ID.
        Args:
            initiative_id: The ID of the initiative to retrieve.
        Returns:
            The initiative as a Pydantic schema, or None if not found.
        """
        pass

    @abstractmethod
    def get_all_initiatives(self, skip: int = 0, limit: int = 100) -> List[InitiativeSchema]:
        """
        Retrieves a list of all initiatives, with optional pagination.
        Args:
            skip: Number of records to skip (for pagination).
            limit: Maximum number of records to return (for pagination).
        Returns:
            A list of initiatives as Pydantic schemas.
        """
        pass

    @abstractmethod
    def update_initiative(self, initiative_id: str, initiative_update: InitiativeUpdate) -> Optional[InitiativeSchema]:
        """
        Updates an existing initiative.
        Args:
            initiative_id: The ID of the initiative to update.
            initiative_update: Pydantic model containing fields to update.
        Returns:
            The updated initiative as a Pydantic schema, or None if not found.
        """
        pass

    @abstractmethod
    def delete_initiative(self, initiative_id: str) -> bool:
        """
        Deletes an initiative by its ID.
        Args:
            initiative_id: The ID of the initiative to delete.
        Returns:
            True if deletion was successful, False otherwise (e.g., if not found).
        """
        pass

    # --- Task Methods ---
    @abstractmethod
    def create_task(self, task_create: TaskCreate, initiative_id: str) -> TaskSchema:
        """
        Creates a new task associated with a given initiative.
        Args:
            task_create: Pydantic model containing data for the new task.
            initiative_id: The ID of the initiative this task belongs to.
        Returns:
            The created task as a Pydantic schema.
        """
        pass

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[TaskSchema]:
        """
        Retrieves a task by its ID.
        Args:
            task_id: The ID of the task to retrieve.
        Returns:
            The task as a Pydantic schema, or None if not found.
        """
        pass

    @abstractmethod
    def get_task_domain_object(self, task_id: str) -> Optional[Any]: # 'Any' placeholder for DomainTask
        """
        Retrieves a task by its ID and returns it as a pure domain object.
        This is intended for use by the agent's core logic which operates on domain models.
        Args:
            task_id: The ID of the task to retrieve.
        Returns:
            The task as a domain object (e.g., june_agent.task.Task), or None if not found.
        """
        pass

    @abstractmethod
    def get_all_tasks(self, initiative_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[TaskSchema]:
        """
        Retrieves a list of tasks, optionally filtered by initiative_id, with pagination.
        Args:
            initiative_id: Optional ID of an initiative to filter tasks by.
            skip: Number of records to skip.
            limit: Maximum number of records to return.
        Returns:
            A list of tasks as Pydantic schemas.
        """
        pass

    @abstractmethod
    def get_processable_tasks_domain_objects(self) -> List[Any]: # 'Any' placeholder for DomainTask
        """
        Retrieves all tasks that are in a state considered processable by the agent's loop,
        as pure domain objects.
        Returns:
            A list of processable tasks as domain objects.
        """
        pass

    @abstractmethod
    def update_task(self, task_id: str, task_update: TaskUpdate) -> Optional[TaskSchema]:
        """
        Updates an existing task.
        Args:
            task_id: The ID of the task to update.
            task_update: Pydantic model containing fields to update.
        Returns:
            The updated task as a Pydantic schema, or None if not found.
        """
        pass

    @abstractmethod
    def save_task_domain_object(self, task_domain_obj: Any) -> TaskSchema: # 'Any' placeholder for DomainTask
        """
        Saves the state of a pure domain task object to the persistence layer.
        This method is used by the agent after modifying a task's state in memory.
        Args:
            task_domain_obj: The domain task object (e.g., june_agent.task.Task) to save.
        Returns:
            The saved task represented as a Pydantic schema.
        """
        pass

    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        """
        Deletes a task by its ID.
        Args:
            task_id: The ID of the task to delete.
        Returns:
            True if deletion was successful, False otherwise.
        """
        pass

    @abstractmethod
    def get_subtasks_for_task_domain_objects(self, parent_task_id: str) -> List[Any]: # 'Any' placeholder for DomainTask
        """
        Retrieves all subtasks for a given parent task ID, returned as pure domain objects.
        Args:
            parent_task_id: The ID of the parent task.
        Returns:
            A list of subtasks as domain objects.
        """
        pass


    # --- General Methods ---
    @abstractmethod
    def ensure_initial_data(self, default_initiative_id: str, default_task_id: str) -> None:
        """
        Ensures that essential default data (e.g., a default initiative and task) exists.
        Implementations should be idempotent.
        Args:
            default_initiative_id: The specific ID to use for the default initiative.
            default_task_id: The specific ID to use for the default task.
        """
        pass

    @abstractmethod
    def get_total_initiatives_count(self) -> int:
        """Returns the total number of initiatives."""
        pass

    @abstractmethod
    def get_task_counts_by_status(self) -> Dict[str, int]:
        """
        Returns a dictionary with task counts, keyed by task status.
        Should include all defined task statuses with a count of 0 if no tasks exist for that status.
        """
        pass
