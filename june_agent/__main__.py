import logging
import threading # Keep for Agent thread if main directly starts it, but Agent class handles its own thread.
import time # Keep for __main__ level delays if any, or logging.
import os

# Core application components
from june_agent.agent import Agent  # The main agent controller.
from june_agent.services.model_service_interface import IModelService  # Service interface for type hinting.
from june_agent.services.sqlalchemy_model_service import SQLAlchemyModelService # Default DB-backed service.
# from june_agent.services.in_memory_model_service import InMemoryModelService # Alternative in-memory service.

# Database setup utilities from the SQLAlchemy service package.
from june_agent.services.sqlalchemy_database import create_db_and_tables, SessionLocal

# Web service factory.
from june_agent.web_service import create_app

# Standard library imports
from typing import List, Optional # For type hinting agent_instance

# Configure module-level logger.
# Ensures logging is set up consistently. If already configured by another module,
# this basicConfig call might not have an effect, which is fine.
# For more complex scenarios, a dedicated logging configuration module might be used.
logger = logging.getLogger(__name__)
if not logger.handlers: # Check to avoid adding handlers multiple times if __main__ is re-imported or re-run in some contexts.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s'
    )

# --- Global Shared Data ---
# `agent_logs`: A list to store recent activity logs from the agent for UI display.
# This is a simple inter-component communication method. In larger systems,
# a more robust logging/eventing system might be used.
agent_logs: List[str] = []
MAX_LOG_ENTRIES = 100 # Maximum number of log entries to keep in `agent_logs`.


def ensure_initial_data_via_service(model_service: IModelService) -> None:
    """
    Ensures that essential default/initial data exists in the persistence layer,
    using the provided model service. This typically includes a default initiative
    and a default starting task for the agent.

    Args:
        model_service: An instance of IModelService to interact with the data layer.

    Raises:
        Exception: If there's a critical error during data setup, preventing the agent from starting.
    """
    # Define specific IDs for default entities for consistency and predictability.
    default_initiative_id = "init_main_001"
    default_task_id = "task_main_001_assess"

    try:
        model_service.ensure_initial_data(default_initiative_id, default_task_id)
        logger.info("Initial data (default initiative and task) ensured via ModelService.")
    except Exception as e:
        logger.error(f"Failed to ensure initial data via ModelService: {e}", exc_info=True)
        # This is considered a critical failure for startup.
        raise


if __name__ == "__main__":
    """
    Main entry point for the June Agent application.
    Orchestrates the initialization of services, the agent itself, and the web UI.
    """
    logger.info("June agent process starting (Agent & ModelService architecture)...")
    agent_instance: Optional[Agent] = None # Define agent_instance for access in finally block

    try:
        # 1. Initialize Database Schema:
        # Ensures all tables defined by SQLAlchemy ORM models are created if they don't exist.
        # This uses the setup from `june_agent.services.sqlalchemy_database`.
        create_db_and_tables()
        logger.info("Database tables created/verified (via sqlalchemy_database module).")

        # 2. Instantiate the ModelService:
        # This service abstracts data persistence. SQLAlchemyModelService uses the live database.
        # For testing or different backends, another implementation of IModelService could be used.
        model_service_instance: IModelService = SQLAlchemyModelService(session_factory=SessionLocal)
        # Example for using InMemoryModelService:
        # model_service_instance: IModelService = InMemoryModelService()
        logger.info(f"Using ModelService implementation: {type(model_service_instance).__name__}")

        # 3. Ensure Initial/Default Data:
        # Populates essential records (e.g., a default initiative/task) if they are missing.
        ensure_initial_data_via_service(model_service_instance)

    except Exception as e:
        logger.critical(f"CRITICAL: Failed during initial setup (database or model service initialization): {e}", exc_info=True)
        exit(1) # Exit if core setup (DB, initial data) fails.

    # 4. Instantiate and Start the Agent:
    # The Agent class contains the core task processing loop.
    try:
        agent_instance = Agent(model_service=model_service_instance, run_interval_seconds=10)
        agent_instance.start() # The Agent manages its own background thread.
        logger.info("Agent instance created and background processing started successfully.")
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to instantiate or start the Agent: {e}", exc_info=True)
        exit(1) # Exit if the agent itself cannot start.

    # 5. Create and Run the Flask Web Application:
    # The web service provides a UI and API for interacting with the agent and its data.
    # It's passed a reference to the model service and the shared agent_logs list.
    try:
        logger.info("Creating Flask application...")
        flask_app = create_app(
            model_service_ref=model_service_instance,
            agent_logs_ref=agent_logs
        )

        logger.info("Starting Flask web server on host 0.0.0.0, port 8080...")
        # flask_app.run() is blocking and will keep the main thread alive.
        # The agent runs in a daemon thread, so it will exit when the main thread (Flask app) exits.
        # Setting debug=False is typical for production or non-development runs.
        flask_app.run(host='0.0.0.0', port=8080, debug=False)

    except Exception as e:
        logger.critical(f"CRITICAL: Failed to start the Flask web server: {e}", exc_info=True)
        # If the web server fails, attempt to stop the agent gracefully before exiting.
        if agent_instance:
            logger.info("Attempting to stop agent due to web server startup failure...")
            agent_instance.stop(wait_for_thread=True) # Wait for thread to try to clean up
        exit(1) # Exit if web server fails.

    finally:
        # This block executes when flask_app.run() exits (e.g., on Ctrl+C).
        logger.info("June agent process shutting down...")
        if agent_instance:
             logger.info("Stopping agent...")
             agent_instance.stop(wait_for_thread=False) # Non-blocking stop as app is exiting.
        logger.info("Shutdown complete.")
