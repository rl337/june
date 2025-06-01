import logging
import threading # Keep for Agent thread if main directly starts it, but Agent class handles its own thread.
import time # Keep for __main__ level delays if any, or logging.
import os

# New imports for Agent and ModelService
from june_agent.agent import Agent
from june_agent.services.model_service_interface import IModelService # For type hinting
from june_agent.services.sqlalchemy_model_service import SQLAlchemyModelService
# from june_agent.services.in_memory_model_service import InMemoryModelService # For easy switching

from june_agent import db_v2 # For create_db_and_tables and SessionLocal

from june_agent.web_service import create_app

# Configure basic logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# Global list for agent activity logs (for UI display)
# This is still used by Agent class and web_service.
agent_logs: list[str] = []
MAX_LOG_ENTRIES = 100


def ensure_initial_data_via_service(model_service: IModelService):
    """Ensures at least one initiative and task exist using the ModelService."""
    # These IDs are expected by the ModelService's ensure_initial_data method
    default_initiative_id = "init_main_001"
    default_task_id = "task_main_001_assess"

    try:
        model_service.ensure_initial_data(default_initiative_id, default_task_id)
        logger.info("Initial data ensured via ModelService.")
    except Exception as e:
        logger.error(f"Failed to ensure initial data via ModelService: {e}", exc_info=True)
        # Depending on severity, might re-raise or exit
        raise # Critical for startup


if __name__ == "__main__":
    logger.info("June agent process starting (Agent & ModelService architecture)...")
    agent_instance: Optional[Agent] = None # Define agent_instance outside try for access in finally

    try:
        # 1. Initialize DB schema (SQLAlchemy specific)
        db_v2.create_db_and_tables()
        logger.info("Database tables created/verified (SQLAlchemy).")

        # 2. Instantiate the desired ModelService
        # For production, use SQLAlchemyModelService
        model_service_instance: IModelService = SQLAlchemyModelService(session_factory=db_v2.SessionLocal)
        # To use InMemory for testing from main:
        # model_service_instance: IModelService = InMemoryModelService()
        logger.info(f"Using ModelService: {type(model_service_instance).__name__}")

        # 3. Ensure initial data using the ModelService
        ensure_initial_data_via_service(model_service_instance)

    except Exception as e:
        logger.critical(f"Failed during initial setup (DB or ModelService): {e}", exc_info=True)
        exit(1) # Exit if core setup fails

    # 4. Instantiate and start the Agent
    try:
        agent_instance = Agent(model_service=model_service_instance, run_interval_seconds=10)
        agent_instance.start() # Agent manages its own thread
        logger.info("Agent started successfully.")
    except Exception as e:
        logger.critical(f"Failed to start the Agent: {e}", exc_info=True)
        exit(1) # Exit if agent fails to start

    # 5. Create and run the Flask application
    # Pass the ModelService instance and agent_logs to the web service
    try:
        logger.info("Creating Flask application...")
        flask_app = create_app(
            model_service_ref=model_service_instance, # Pass the service instance
            agent_logs_ref=agent_logs
        )
        logger.info("Starting Flask web server on host 0.0.0.0, port 8080...")
        # flask_app.run() is blocking. Agent runs in its daemon thread.
        flask_app.run(host='0.0.0.0', port=8080, debug=False) # debug=False for production/typical runs
    except Exception as e:
        logger.critical(f"Failed to start the Flask web server: {e}", exc_info=True)
        # Attempt to stop the agent gracefully if web server fails to start
        if agent_instance:
            agent_instance.stop()
        exit(1)
    finally: # Ensure agent is stopped if flask_app.run() exits (e.g. Ctrl+C)
        logger.info("June agent process shutting down...")
        if agent_instance:
             agent_instance.stop(wait_for_thread=False) # Non-blocking stop as app is exiting
