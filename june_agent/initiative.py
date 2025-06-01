import uuid
import logging
import datetime # Keep for Pydantic models if they use it, and for ORM defaults.

# SQLAlchemy imports
from sqlalchemy.orm import Session
from june_agent.models_v2.orm_models import InitiativeORM, TaskORM # Assuming TaskORM is needed for task relationship
from june_agent.models_v2.pydantic_models import InitiativeSchema, InitiativeCreate, InitiativeUpdate # For .from_orm and type hints

# Temporarily, we might still need the old Task class if Initiative.tasks holds instances of it
# For now, let's assume Initiative.tasks will hold TaskSchema or ORM Task objects if directly accessed.
# from june_agent.task import Task # Old task class

# Imports that might be needed by Pydantic models if they have complex types
from typing import Optional, List

logger = logging.getLogger(__name__)

class Initiative: # This class now acts more like a domain model or service for Initiatives
    # It will operate on InitiativeORM objects and use SQLAlchemy sessions.

    # We are moving away from this class being the primary data holder.
    # Pydantic and ORM models will handle that. This class might eventually
    # become a service class or be merged. For now, we adapt its methods.

    # The __init__ is more for conceptual representation if an instance of this 'service' class
    # were to hold a specific loaded ORM object, but classmethods are preferred for stateless operations.
    def __init__(self,
                 orm_obj: InitiativeORM): # Now takes an ORM object
        self._orm_obj = orm_obj # Keep a reference to the ORM object

    # Expose properties from the ORM object
    @property
    def id(self) -> str: return self._orm_obj.id
    @property
    def name(self) -> str: return self._orm_obj.name
    @property
    def description(self) -> Optional[str]: return self._orm_obj.description
    @property
    def status(self) -> str: return self._orm_obj.status
    @property
    def created_at(self) -> datetime.datetime: return self._orm_obj.created_at
    @property
    def updated_at(self) -> datetime.datetime: return self._orm_obj.updated_at
    @property
    def tasks(self) -> List[TaskORM]: return self._orm_obj.tasks


    @classmethod
    def create(cls, db: Session, initiative_create: InitiativeCreate) -> InitiativeSchema:
        """Creates a new initiative in the database."""
        db_initiative_orm = InitiativeORM(
            name=initiative_create.name,
            description=initiative_create.description,
            status=initiative_create.status
            # id, created_at, updated_at have defaults in ORM
        )
        db.add(db_initiative_orm)
        db.commit()
        db.refresh(db_initiative_orm)
        logger.info(f"Initiative created with ID: {db_initiative_orm.id}, Name: '{db_initiative_orm.name}'")

        # Populate task_ids for the schema
        schema = InitiativeSchema.from_orm(db_initiative_orm)
        schema.task_ids = [task.id for task in db_initiative_orm.tasks] # tasks will be empty on create
        return schema

    @classmethod
    def get(cls, db: Session, initiative_id: str) -> Optional[InitiativeSchema]:
        """Loads an initiative from the database by its ID using SQLAlchemy."""
        db_initiative_orm = db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id).first()
        if db_initiative_orm:
            logger.info(f"Initiative {initiative_id} loaded from database.")
            schema = InitiativeSchema.from_orm(db_initiative_orm)
            schema.task_ids = [task.id for task in db_initiative_orm.tasks] # Populate task_ids
            return schema
        logger.warning(f"Initiative with ID {initiative_id} not found.")
        return None

    @classmethod
    def get_all(cls, db: Session, skip: int = 0, limit: int = 100) -> List[InitiativeSchema]:
        """Loads all initiatives from the database with pagination."""
        db_initiatives_orm = db.query(InitiativeORM).order_by(InitiativeORM.created_at.desc()).offset(skip).limit(limit).all()

        results = []
        for db_init_orm in db_initiatives_orm:
            schema = InitiativeSchema.from_orm(db_init_orm)
            schema.task_ids = [task.id for task in db_init_orm.tasks] # Populate task_ids
            results.append(schema)

        logger.info(f"Loaded {len(results)} initiatives from database.")
        return results

    @classmethod
    def update(cls, db: Session, initiative_id: str, initiative_update: InitiativeUpdate) -> Optional[InitiativeSchema]:
        """Updates an existing initiative in the database."""
        db_initiative_orm = db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id).first()
        if not db_initiative_orm:
            logger.warning(f"Initiative with ID {initiative_id} not found for update.")
            return None

        update_data = initiative_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_initiative_orm, key, value)

        # updated_at is handled by onupdate in ORM model
        db.add(db_initiative_orm)
        db.commit()
        db.refresh(db_initiative_orm)
        logger.info(f"Initiative {initiative_id} updated.")

        schema = InitiativeSchema.from_orm(db_initiative_orm)
        schema.task_ids = [task.id for task in db_initiative_orm.tasks] # Populate task_ids
        return schema

    @classmethod
    def delete(cls, db: Session, initiative_id: str) -> bool:
        """Deletes an initiative from the database."""
        db_initiative_orm = db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id).first()
        if not db_initiative_orm:
            logger.warning(f"Initiative with ID {initiative_id} not found for deletion.")
            return False

        db.delete(db_initiative_orm)
        db.commit()
        logger.info(f"Initiative {initiative_id} deleted.")
        return True

# Note: The old `if __name__ == '__main__':` block is removed.
# Tests should be used for validation.
