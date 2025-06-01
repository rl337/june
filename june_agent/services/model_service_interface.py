from abc import ABC, abstractmethod
from typing import List, Optional, Any # Any for now for Pydantic models or dicts

# Forward declare Pydantic models or import them if they don't cause circularity
# For the interface, using 'Any' or specific Dict structures can also work initially.
# Let's assume Pydantic models will be used for data transfer objects (DTOs).
from june_agent.models_v2.pydantic_models import (
    InitiativeSchema, InitiativeCreate, InitiativeUpdate,
    TaskSchema, TaskCreate, TaskUpdate
)

class IModelService(ABC):

    # --- Initiative Methods ---
    @abstractmethod
    def create_initiative(self, initiative_create: InitiativeCreate) -> InitiativeSchema:
        pass

    @abstractmethod
    def get_initiative(self, initiative_id: str) -> Optional[InitiativeSchema]:
        pass

    @abstractmethod
    def get_all_initiatives(self, skip: int = 0, limit: int = 100) -> List[InitiativeSchema]:
        pass

    @abstractmethod
    def update_initiative(self, initiative_id: str, initiative_update: InitiativeUpdate) -> Optional[InitiativeSchema]:
        pass

    @abstractmethod
    def delete_initiative(self, initiative_id: str) -> bool:
        pass

    # --- Task Methods ---
    @abstractmethod
    def create_task(self, task_create: TaskCreate, initiative_id: str) -> TaskSchema:
        pass

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[TaskSchema]:
        pass

    @abstractmethod
    def get_task_domain_object(self, task_id: str) -> Optional[Any]: # 'Any' for now, will be domain Task
        pass

    @abstractmethod
    def get_all_tasks(self, initiative_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[TaskSchema]:
        pass

    @abstractmethod
    def get_processable_tasks_domain_objects(self) -> List[Any]: # 'Any' for now, will be domain Task
        pass

    @abstractmethod
    def update_task(self, task_id: str, task_update: TaskUpdate) -> Optional[TaskSchema]:
        pass

    @abstractmethod
    def save_task_domain_object(self, task_domain_obj: Any) -> TaskSchema: # 'Any' for domain Task
        pass

    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        pass

    @abstractmethod
    def get_subtasks_for_task_domain_objects(self, parent_task_id: str) -> List[Any]: # 'Any' for domain Task
        pass


    # --- General Methods ---
    @abstractmethod
    def ensure_initial_data(self, default_initiative_id: str, default_task_id: str) -> None:
        pass
