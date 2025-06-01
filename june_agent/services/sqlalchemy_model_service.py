import datetime
from typing import List, Optional, Any
from sqlalchemy.orm import Session, joinedload, selectinload # For eager loading

from june_agent.services.model_service_interface import IModelService
from june_agent.models_v2.orm_models import InitiativeORM, TaskORM, Base # Base for create_all if needed here
from june_agent.models_v2.pydantic_models import (
    InitiativeSchema, InitiativeCreate, InitiativeUpdate,
    TaskSchema, TaskCreate, TaskUpdate
)
# Import the domain Task object for conversions and for its constants
from june_agent.task import Task as DomainTask
from june_agent.db_v2 import get_db, engine # For session and potentially direct engine use

import logging
logger = logging.getLogger(__name__)

class SQLAlchemyModelService(IModelService):

    def __init__(self, session_factory): # session_factory like db_v2.SessionLocal
        self.session_factory = session_factory

    # --- Helper for session management ---
    def _get_session(self) -> Session:
        return self.session_factory() # Create a new session

    # --- Initiative Methods ---
    def create_initiative(self, initiative_create: InitiativeCreate) -> InitiativeSchema:
        db = self._get_session()
        try:
            db_initiative_orm = InitiativeORM(
                name=initiative_create.name,
                description=initiative_create.description,
                status=initiative_create.status
            )
            db.add(db_initiative_orm)
            db.commit()
            db.refresh(db_initiative_orm)

            schema = InitiativeSchema.from_orm(db_initiative_orm)
            # Manually load task_ids if not automatically handled by from_orm from an empty list
            schema.task_ids = [task.id for task in db_initiative_orm.tasks] # Will be empty
            return schema
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_initiative(self, initiative_id: str) -> Optional[InitiativeSchema]:
        db = self._get_session()
        try:
            # Eager load tasks to populate task_ids in the schema
            db_initiative_orm = db.query(InitiativeORM).options(selectinload(InitiativeORM.tasks)).filter(InitiativeORM.id == initiative_id).first()
            if db_initiative_orm:
                schema = InitiativeSchema.from_orm(db_initiative_orm)
                schema.task_ids = [task.id for task in db_initiative_orm.tasks]
                return schema
            return None
        finally:
            db.close()

    def get_all_initiatives(self, skip: int = 0, limit: int = 100) -> List[InitiativeSchema]:
        db = self._get_session()
        try:
            db_initiatives_orm = (db.query(InitiativeORM)
                                  .options(selectinload(InitiativeORM.tasks)) # Eager load tasks
                                  .order_by(InitiativeORM.created_at.desc())
                                  .offset(skip).limit(limit).all())

            schemas = []
            for db_init_orm in db_initiatives_orm:
                schema = InitiativeSchema.from_orm(db_init_orm)
                schema.task_ids = [task.id for task in db_init_orm.tasks]
                schemas.append(schema)
            return schemas
        finally:
            db.close()

    def update_initiative(self, initiative_id: str, initiative_update: InitiativeUpdate) -> Optional[InitiativeSchema]:
        db = self._get_session()
        try:
            db_initiative_orm = db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id).first()
            if not db_initiative_orm:
                return None

            update_data = initiative_update.dict(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_initiative_orm, key, value)

            db.add(db_initiative_orm) # Add to session before commit if changed
            db.commit()
            db.refresh(db_initiative_orm)

            schema = InitiativeSchema.from_orm(db_initiative_orm)
            schema.task_ids = [task.id for task in db_initiative_orm.tasks] # Re-populate task_ids
            return schema
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def delete_initiative(self, initiative_id: str) -> bool:
        db = self._get_session()
        try:
            db_initiative_orm = db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id).first()
            if not db_initiative_orm:
                return False

            db.delete(db_initiative_orm) # Cascade delete for tasks is handled by DB schema
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # --- Task ORM <-> Domain Conversion Helpers ---
    def _task_orm_to_domain(self, task_orm: TaskORM, load_subtasks: bool = False, db: Optional[Session] = None) -> DomainTask:
        domain = DomainTask(
            task_id=task_orm.id,
            description=task_orm.description,
            initiative_id=task_orm.initiative_id,
            parent_task_id=task_orm.parent_task_id,
            status=task_orm.status,
            phase=task_orm.phase,
            result=task_orm.result,
            error_message=task_orm.error_message,
            created_at=task_orm.created_at,
            updated_at=task_orm.updated_at
            # requests are not persisted, subtasks need explicit loading if required here
        )
        if load_subtasks and db: # Only if db session is provided
            # This uses the ORM's subtasks relationship.
            # Ensure subtasks are loaded in the ORM object (e.g., via selectinload or by access).
            # Accessing task_orm.subtasks might trigger a lazy load if not already loaded.
            domain.subtasks = [self._task_orm_to_domain(sub_orm, db=db, load_subtasks=False) for sub_orm in task_orm.subtasks]
            # Set load_subtasks=False in recursive call to prevent very deep loads unless specifically designed for.
        return domain

    def _task_domain_to_orm(self, domain_task: DomainTask, db_task_orm: Optional[TaskORM] = None) -> TaskORM:
        if db_task_orm is None: # Creating new ORM obj
            db_task_orm = TaskORM(id=domain_task.id, created_at=domain_task.created_at)

        db_task_orm.description = domain_task.description
        db_task_orm.initiative_id = domain_task.initiative_id
        db_task_orm.parent_task_id = domain_task.parent_task_id
        db_task_orm.status = domain_task.status
        db_task_orm.phase = domain_task.phase
        db_task_orm.result = domain_task.result
        db_task_orm.error_message = domain_task.error_message
        # updated_at is handled by ORM onupdate or set explicitly before commit if needed
        db_task_orm.updated_at = domain_task.updated_at # Sync from domain's last update

        # Subtasks are not directly managed here; relationships are handled by SQLAlchemy
        # when parent and child ORM objects are session-managed and linked.
        return db_task_orm

    # --- Task Methods ---
    def create_task(self, task_create: TaskCreate, initiative_id: str) -> TaskSchema:
        db = self._get_session()
        try:
            # Verify initiative exists
            parent_initiative_orm = db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id).first()
            if not parent_initiative_orm:
                raise ValueError(f"Initiative with ID {initiative_id} not found for task creation.")

            db_task_orm = TaskORM(
                description=task_create.description,
                status=task_create.status,
                phase=task_create.phase,
                initiative_id=initiative_id,
                parent_task_id=task_create.parent_task_id # Can be None
            )
            db.add(db_task_orm)
            db.commit()
            db.refresh(db_task_orm)

            domain_task = self._task_orm_to_domain(db_task_orm, db=db)
            return domain_task.to_pydantic_schema()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_task(self, task_id: str) -> Optional[TaskSchema]:
        db = self._get_session()
        try:
            db_task_orm = db.query(TaskORM).options(
                selectinload(TaskORM.subtasks),
                joinedload(TaskORM.initiative),
                joinedload(TaskORM.parent_task)
            ).filter(TaskORM.id == task_id).first()

            if db_task_orm:
                domain_task = self._task_orm_to_domain(db_task_orm, load_subtasks=True, db=db)
                return domain_task.to_pydantic_schema()
            return None
        finally:
            db.close()

    def get_task_domain_object(self, task_id: str, load_subtasks: bool = False) -> Optional[DomainTask]:
        db = self._get_session()
        try:
            options = [joinedload(TaskORM.initiative), joinedload(TaskORM.parent_task)]
            if load_subtasks:
                options.append(selectinload(TaskORM.subtasks))

            db_task_orm = db.query(TaskORM).options(*options).filter(TaskORM.id == task_id).first()
            if db_task_orm:
                return self._task_orm_to_domain(db_task_orm, load_subtasks=load_subtasks, db=db)
            return None
        finally:
            db.close()


    def get_all_tasks(self, initiative_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[TaskSchema]:
        db = self._get_session()
        try:
            query = db.query(TaskORM).options(selectinload(TaskORM.subtasks)).order_by(TaskORM.created_at.asc())
            if initiative_id:
                query = query.filter(TaskORM.initiative_id == initiative_id)

            db_task_orms = query.offset(skip).limit(limit).all()

            schemas = []
            for orm_obj in db_task_orms:
                domain_obj = self._task_orm_to_domain(orm_obj, load_subtasks=True, db=db)
                schemas.append(domain_obj.to_pydantic_schema())
            return schemas
        finally:
            db.close()

    def get_processable_tasks_domain_objects(self) -> List[DomainTask]:
        db = self._get_session()
        try:
            task_orms = (
                db.query(TaskORM)
                .options(selectinload(TaskORM.subtasks),
                         joinedload(TaskORM.initiative),
                         joinedload(TaskORM.parent_task))
                .filter(
                    (TaskORM.phase.in_([DomainTask.PHASE_ASSESSMENT, DomainTask.PHASE_EXECUTION, DomainTask.PHASE_RECONCILIATION])) |
                    (TaskORM.status == DomainTask.STATUS_PENDING_SUBTASKS)
                )
                .order_by(TaskORM.updated_at.asc())
                .all()
            )
            domain_tasks = []
            for task_orm in task_orms:
                domain_task = self._task_orm_to_domain(task_orm, load_subtasks=True, db=db)
                domain_tasks.append(domain_task)
            return domain_tasks
        finally:
            db.close()

    def update_task(self, task_id: str, task_update: TaskUpdate) -> Optional[TaskSchema]:
        db = self._get_session()
        try:
            db_task_orm = db.query(TaskORM).filter(TaskORM.id == task_id).first()
            if not db_task_orm:
                return None

            update_data = task_update.dict(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_task_orm, key, value)

            db_task_orm.updated_at = datetime.datetime.utcnow()

            db.add(db_task_orm)
            db.commit()
            db.refresh(db_task_orm)

            domain_task = self._task_orm_to_domain(db_task_orm, load_subtasks=True, db=db)
            return domain_task.to_pydantic_schema()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def save_task_domain_object(self, task_domain_obj: DomainTask) -> TaskSchema:
        db = self._get_session()
        try:
            db_task_orm = db.query(TaskORM).filter(TaskORM.id == task_domain_obj.id).first()
            is_new = False
            if not db_task_orm:
                db_task_orm = TaskORM(id=task_domain_obj.id, created_at=task_domain_obj.created_at)
                is_new = True

            self._task_domain_to_orm(task_domain_obj, db_task_orm)

            # Handle subtasks: if domain subtasks were added/removed, reflect in ORM.
            # This requires careful management of the session and relationships.
            # For simplicity here, assume direct children are handled if their parent_task_id is set.
            # If task_domain_obj.subtasks contains new DomainTask instances not yet in DB,
            # they need to be converted to ORM and added to session.
            # If subtasks were removed, their ORM counterparts might need removal or parent_task_id nulled.

            # Simplified: if new subtasks (domain objects) are in task_domain_obj.subtasks
            # and not yet persisted or linked, this would need more logic.
            # The current _task_domain_to_orm only updates scalar fields.
            # For full subtask sync, one would iterate domain_obj.subtasks,
            # convert each to ORM, ensure they are in session, and linked to db_task_orm.
            # For now, this save focuses on the task itself, assuming subtasks are managed elsewhere
            # or their linkage via parent_task_id is sufficient for ORM to pick up.

            if is_new:
                db.add(db_task_orm)
            else:
                db_task_orm = db.merge(db_task_orm)

            db.commit()
            db.refresh(db_task_orm)

            task_domain_obj.created_at = db_task_orm.created_at
            task_domain_obj.updated_at = db_task_orm.updated_at
            # After saving, refresh domain object's subtasks from ORM to ensure consistency
            # self._task_orm_to_domain will create new domain subtask objects
            if hasattr(db_task_orm, 'subtasks'): # Check if subtasks relationship was loaded
                task_domain_obj.subtasks = [self._task_orm_to_domain(sub_orm, db=db, load_subtasks=False) for sub_orm in db_task_orm.subtasks]

            return task_domain_obj.to_pydantic_schema()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def delete_task(self, task_id: str) -> bool:
        db = self._get_session()
        try:
            db_task_orm = db.query(TaskORM).filter(TaskORM.id == task_id).first()
            if not db_task_orm:
                return False

            db.delete(db_task_orm)
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_subtasks_for_task_domain_objects(self, parent_task_id: str) -> List[DomainTask]:
        db = self._get_session()
        try:
            parent_orm = db.query(TaskORM).options(selectinload(TaskORM.subtasks)).filter(TaskORM.id == parent_task_id).first()
            if not parent_orm:
                return []

            domain_subtasks = [self._task_orm_to_domain(sub_orm, db=db, load_subtasks=False) for sub_orm in parent_orm.subtasks]
            return domain_subtasks
        finally:
            db.close()


    def ensure_initial_data(self, default_initiative_id: str, default_task_id: str) -> None:
        db = self._get_session()
        try:
            if not db.query(InitiativeORM).filter(InitiativeORM.id == default_initiative_id).first():
                init_orm = InitiativeORM(id=default_initiative_id, name="Main Agent Initiative (SQLAlchemy)", status="active")
                db.add(init_orm)
                logger.info(f"SQLAlchemyModelService: Created default initiative {default_initiative_id}")

            if not db.query(TaskORM).filter(TaskORM.id == default_task_id).first():
                task_orm = TaskORM(
                    id=default_task_id,
                    description="Default task: Assess objectives (SQLAlchemy)",
                    initiative_id=default_initiative_id,
                    status=DomainTask.STATUS_PENDING,
                    phase=DomainTask.PHASE_ASSESSMENT
                )
                db.add(task_orm)
                logger.info(f"SQLAlchemyModelService: Created default task {default_task_id}")
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"SQLAlchemyModelService: Error in ensure_initial_data: {e}", exc_info=True)
            raise
        finally:
            db.close()
