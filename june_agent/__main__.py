import logging
import threading
import time
import os

# SQLAlchemy and new model imports
from june_agent import db_v2 # For create_db_and_tables, get_db
from june_agent.models_v2.orm_models import TaskORM, InitiativeORM # Direct ORM for queries
from june_agent.models_v2.pydantic_models import InitiativeCreate, TaskCreate # For creating initial data
from june_agent.initiative import Initiative # Refactored Initiative service class
from june_agent.task import Task # Refactored Task domain class
from sqlalchemy.orm import Session # For type hinting
from sqlalchemy.exc import SQLAlchemyError # For specific exceptions

from june_agent.web_service import create_app # create_app signature will change

# Configure basic logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
# Use module-level logger for consistency
logger = logging.getLogger(__name__)
if not logger.handlers: # Avoid duplicate handlers if already configured
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')


# Global list for agent activity logs (for UI display)
agent_logs: list[str] = []
MAX_LOG_ENTRIES = 100

# DB_PATH is now implicitly handled by db_v2.DATABASE_URL

# Helper to add a create method to Task class, similar to Initiative class
# This should ideally be in task.py, but adding here for now if subtask cannot modify task.py again.
# If task.py can be modified, this should be added there.
# For this subtask, assume we can't modify task.py again, so define helper or adapt.
# Better: Assume Task will have a .create classmethod similar to Initiative.
# If not, this function needs to do direct ORM object creation for tasks.

def ensure_initial_initiative_and_task(db: Session):
    """Ensures at least one initiative and task exist using SQLAlchemy session."""
    initiative_id_to_check = "init_main_001"
    task_id_to_check = "task_main_001_assess"

    # Check if the main initiative exists
    # Initiative.get returns a Pydantic schema or None
    existing_initiative_schema = Initiative.get(db, initiative_id_to_check)

    initiative_id_for_task: str
    if not existing_initiative_schema:
        logger.info(f"Creating initial default initiative '{initiative_id_to_check}'.")

        # Delete if it somehow exists from a partial previous attempt with a different structure
        # This is unlikely if Initiative.get returned None, but as a safeguard.
        db.query(InitiativeORM).filter(InitiativeORM.id == initiative_id_to_check).delete()
        db.commit() # Commit deletion before trying to add new with same ID

        default_initiative_orm = InitiativeORM(
            id=initiative_id_to_check, # Set specific ID
            name="Main Agent Initiative",
            description="Default initiative for ongoing agent tasks.",
            status="active"
        )
        db.add(default_initiative_orm)
        try:
            db.commit()
            db.refresh(default_initiative_orm)
            initiative_id_for_task = default_initiative_orm.id
            logger.info(f"Default initiative '{initiative_id_for_task}' ensured.")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create default initiative {initiative_id_to_check}: {e}", exc_info=True)
            db.rollback()
            # Cannot proceed without initiative if it failed
            raise Exception(f"Critical: Could not create default initiative {initiative_id_to_check}.") from e
    else:
        initiative_id_for_task = existing_initiative_schema.id
        logger.info(f"Initial initiative '{initiative_id_for_task}' already exists.")

    # Check if the initial task for this initiative exists
    # Task.get returns a domain Task object or None
    existing_task_domain_obj = Task.get(db, task_id_to_check)
    if not existing_task_domain_obj:
        logger.info(f"Creating initial default task '{task_id_to_check}' for initiative '{initiative_id_for_task}'.")

        # Delete if it somehow exists from a partial previous attempt
        db.query(TaskORM).filter(TaskORM.id == task_id_to_check).delete()
        db.commit()

        default_task_orm = TaskORM(
            id=task_id_to_check, # Set specific ID
            description="Default task: Assess current agent objectives and plan.",
            initiative_id=initiative_id_for_task,
            status=Task.STATUS_PENDING,
            phase=Task.PHASE_ASSESSMENT
        )
        db.add(default_task_orm)
        try:
            db.commit()
            logger.info(f"Initial task '{default_task_orm.id}' created and saved.")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create default task {task_id_to_check}: {e}", exc_info=True)
            db.rollback()
            # Log error but system might still be usable depending on other tasks
            # For now, let's not raise an exception here, to allow agent to start if possible.
    else:
        logger.info(f"Initial task '{task_id_to_check}' already exists for initiative '{initiative_id_for_task}'.")


def agent_loop(): # No longer takes db_manager
    """
    Main background loop for the agent using SQLAlchemy sessions.
    """
    logger.info("Agent_loop thread started (SQLAlchemy version).")
    while True:
        db: Optional[Session] = None
        try:
            db = next(db_v2.get_db()) # Obtain a session

            # Query for processable tasks using SQLAlchemy ORM
            processable_tasks_orm = (
                db.query(TaskORM)
                .filter(
                    (TaskORM.phase.in_([Task.PHASE_ASSESSMENT, Task.PHASE_EXECUTION, Task.PHASE_RECONCILIATION])) |
                    (TaskORM.status == Task.STATUS_PENDING_SUBTASKS)
                )
                .order_by(TaskORM.updated_at.asc())
                .all()
            )

            if processable_tasks_orm:
                logger.info(f"Found {len(processable_tasks_orm)} tasks potentially requiring processing (SQLAlchemy).")
                for task_orm_obj in processable_tasks_orm:
                    # Convert ORM object to domain Task object
                    task_domain_obj = Task._from_orm(task_orm_obj) # Use the converter

                    log_entry_pickup = (
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Agent considering task: {task_domain_obj.id} "
                        f"- '{task_domain_obj.description[:30]}' (Status: {task_domain_obj.status}, Phase: {task_domain_obj.phase})"
                    )
                    agent_logs.append(log_entry_pickup)
                    logger.info(f"Agent considering task ID: {task_domain_obj.id} - '{task_domain_obj.description[:50]}' "
                                f"(Status: {task_domain_obj.status}, Phase: {task_domain_obj.phase})")

                    # Process the current phase using the domain object, passing the session
                    task_domain_obj.process_current_phase(db) # This method now handles its own saving via the session

                    # Log outcome (domain object's state might have changed)
                    log_entry_outcome = (
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task_domain_obj.id} processed. "
                        f"New Status: {task_domain_obj.status}, New Phase: {task_domain_obj.phase}"
                    )
                    agent_logs.append(log_entry_outcome)
                    logger.info(f"Task {task_domain_obj.id} processed. New Status: {task_domain_obj.status}, New Phase: {task_domain_obj.phase}")

                    if task_domain_obj.status == Task.STATUS_FAILED:
                         agent_logs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task_domain_obj.id} failed. Error: {str(task_domain_obj.error_message)[:100]}...")

                    if len(agent_logs) > MAX_LOG_ENTRIES: # Cap the logs
                        agent_logs.pop(0)
            # else:
                # logger.debug("No tasks found requiring active processing in this iteration (SQLAlchemy).")

        except SQLAlchemyError as db_err: # Catch SQLAlchemy specific errors
            logger.error(f"SQLAlchemy Database error in agent_loop: {db_err}", exc_info=True)
            if db: db.rollback() # Rollback session on error
            time.sleep(15)
        except Exception as e:
            logger.error(f"Critical error in agent_loop: {e}", exc_info=True)
            if db: db.rollback() # Attempt rollback on other errors too if session exists
        finally:
            if db: db.close() # Ensure session is closed

        time.sleep(10)

if __name__ == "__main__":
    logger.info("June agent process starting (SQLAlchemy version)...")

    try:
        db_v2.create_db_and_tables() # Initialize DB using SQLAlchemy setup
        logger.info("Database initialized and tables created/verified (SQLAlchemy).")

        # Ensure initial content using a session
        db_session_for_init = next(db_v2.get_db())
        try:
            ensure_initial_initiative_and_task(db_session_for_init)
        finally:
            db_session_for_init.close()

    except Exception as e:
        logger.error(f"Failed to initialize database or ensure initial data (SQLAlchemy): {e}", exc_info=True)
        exit(1)

    logger.info("Initializing and starting agent_loop thread (SQLAlchemy)...")
    agent_thread = threading.Thread(target=agent_loop, daemon=True) # No longer passes db_manager
    agent_thread.start()

    logger.info("Creating Flask application (SQLAlchemy)...")
    # create_app will now import get_db from db_v2 directly
    flask_app = create_app(agent_logs_ref=agent_logs)

    logger.info("Starting Flask web server on host 0.0.0.0, port 8080...")
    flask_app.run(host='0.0.0.0', port=8080)

    logger.info("June agent process shutting down.")
    # No global db_manager to close here. Sessions are managed by get_db().
