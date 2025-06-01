import logging
import threading
import time
import os # For checking if DB exists
import sqlite3 # For catching sqlite3.Error

from june_agent.db import DatabaseManager
from june_agent.initiative import Initiative
from june_agent.task import Task
from june_agent.request import TogetherAIRequest # Still needed if default requests are added
from june_agent.web_service import create_app

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Global list for agent activity logs (for UI display)
agent_logs: list[str] = []
MAX_LOG_ENTRIES = 100

DB_PATH = 'june_agent.db' # Define DB Path

def ensure_initial_initiative_and_task(db_manager: DatabaseManager):
    """Ensures at least one initiative and task exist for demonstration/testing."""
    initiative_id_to_check = "init_main_001"
    task_id_to_check = "task_main_001_assess"

    # Check if the main initiative exists
    initiative = Initiative.load(initiative_id=initiative_id_to_check, db_manager=db_manager)
    if not initiative:
        logger.info(f"Creating initial default initiative '{initiative_id_to_check}'.")
        initiative = Initiative(
            name="Main Agent Initiative",
            description="Default initiative for ongoing agent tasks.",
            db_manager=db_manager,
            initiative_id=initiative_id_to_check,
            status="active" # Changed from "pending" to "active"
        )
        initiative.save()

        # Since initiative is new, the task also needs to be created.
        logger.info(f"Creating initial default task '{task_id_to_check}' for new initiative '{initiative.id}'.")
        initial_task = Task(
            description="Default task: Assess current agent objectives and plan.",
            db_manager=db_manager,
            task_id=task_id_to_check,
            initiative_id=initiative.id,
            status=Task.STATUS_PENDING,
            phase=Task.PHASE_ASSESSMENT
        )
        initial_task.save()
        # initiative.add_task_object(initial_task) # Not strictly needed here as loop loads from DB
        logger.info(f"Initial task '{initial_task.id}' created and saved.")
    else:
        logger.info(f"Initial initiative '{initiative_id_to_check}' already exists.")
        # Initiative exists, check if the specific default task exists
        task = Task.load(task_id=task_id_to_check, db_manager=db_manager)
        if not task:
            logger.info(f"Creating initial default task '{task_id_to_check}' for existing initiative '{initiative.id}'.")
            initial_task = Task(
                description="Default task: Assess current agent objectives and plan (for existing init).",
                db_manager=db_manager,
                task_id=task_id_to_check,
                initiative_id=initiative.id,
                status=Task.STATUS_PENDING,
                phase=Task.PHASE_ASSESSMENT
            )
            initial_task.save()
            logger.info(f"Initial task '{initial_task.id}' created and saved for existing initiative.")
        else:
            logger.info(f"Initial task '{task_id_to_check}' already exists for initiative '{initiative.id}'.")


def agent_loop(db_manager: DatabaseManager):
    """
    Main background loop for the agent.
    Periodically queries the database for tasks requiring processing and advances them through phases.
    """
    logger.info("Agent_loop thread started.")
    while True:
        try:
            # Query for tasks that need processing.
            # A task is processable if:
            # 1. Phase is ASSESSMENT, EXECUTION, or RECONCILIATION
            # 2. Status is PENDING_SUBTASKS (picked up by RECONCILIATION logic within process_current_phase)
            query = """
            SELECT id FROM tasks
            WHERE (phase IN (?, ?, ?)) OR status = ?
            ORDER BY updated_at ASC -- Process tasks that haven't been touched recently first
            """
            task_ids_to_process = db_manager.fetch_all(query, (
                Task.PHASE_ASSESSMENT, Task.PHASE_EXECUTION, Task.PHASE_RECONCILIATION,
                Task.STATUS_PENDING_SUBTASKS
            ))

            if task_ids_to_process:
                logger.info(f"Found {len(task_ids_to_process)} tasks potentially requiring processing.")
                for row in task_ids_to_process:
                    task_id = row['id']
                    task = Task.load(task_id=task_id, db_manager=db_manager)
                    if not task:
                        logger.warning(f"Task ID {task_id} found in query but could not be loaded. Skipping.")
                        continue

                    log_entry_pickup = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Agent considering task: {task.id} - '{task.description[:30]}' (Status: {task.status}, Phase: {task.phase})"
                    agent_logs.append(log_entry_pickup)
                    logger.info(f"Agent considering task ID: {task.id} - '{task.description[:50]}' (Status: {task.status}, Phase: {task.phase})")

                    task.process_current_phase() # This method handles logic and saving

                    log_entry_outcome = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task.id} processed. New Status: {task.status}, New Phase: {task.phase}"
                    agent_logs.append(log_entry_outcome)
                    logger.info(f"Task {task.id} processed. New Status: {task.status}, New Phase: {task.phase}")

                    if task.status == Task.STATUS_FAILED:
                         agent_logs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task.id} failed. Error: {str(task.error_message)[:100]}...")

                    if len(agent_logs) > MAX_LOG_ENTRIES: # Cap the logs
                        agent_logs.pop(0)
            # else:
                # logger.debug("No tasks found requiring active processing in this iteration.")

        except sqlite3.Error as db_err:
            logger.error(f"Database error in agent_loop: {db_err}", exc_info=True)
            time.sleep(15)
        except Exception as e:
            logger.error(f"Critical error in agent_loop: {e}", exc_info=True)
            # Avoid continuous fast error loops by still sleeping

        time.sleep(10) # Pause for 10 seconds

if __name__ == "__main__":
    logger.info("June agent process starting...")

    db_manager = DatabaseManager(db_path=DB_PATH)
    try:
        db_manager.connect()
        db_manager.create_tables()
        logger.info("Database initialized and tables created/verified.")

        # Ensure initial content. Call this after connect() and create_tables().
        ensure_initial_initiative_and_task(db_manager)

    except Exception as e:
        logger.error(f"Failed to initialize database or ensure initial data: {e}", exc_info=True)
        # Exit if DB initialization fails, as the agent cannot function.
        exit(1)


    logger.info("Initializing and starting agent_loop thread...")
    agent_thread = threading.Thread(target=agent_loop, args=(db_manager,), daemon=True)
    agent_thread.start()

    logger.info("Creating Flask application...")
    flask_app = create_app(
        db_manager_ref=db_manager,
        agent_logs_ref=agent_logs
    )

    logger.info("Starting Flask web server on host 0.0.0.0, port 8080...")
    flask_app.run(host='0.0.0.0', port=8080)

    logger.info("June agent process shutting down.")
    if db_manager:
        db_manager.close()
