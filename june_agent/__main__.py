import logging
import threading # For running the agent loop in a background thread
import time # For adding delays in the agent loop
# uuid is no longer needed here as Task generates its own ID.
# os and together are no longer directly used here.

from .task import Task
from .request import TogetherAIRequest
from .web_service import create_app

# Configure basic logging for the application.
# This setup logs messages with INFO level and above to the console.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# Global list to store all tasks managed by the agent.
# This list is shared between the agent_loop and the web_service.
tasks_list: list[Task] = []

# Global list to store agent activity logs.
agent_logs: list[str] = []
MAX_LOG_ENTRIES = 100

# The old find_task_by_id helper is no longer needed here as tasks are processed directly
# and task finding logic for API calls is within the Task.process or request execution.

# The old call_together_api function is removed. Its functionality is now part of
# TogetherAIRequest.execute() and Task.process().

def agent_loop():
    """
    Main background loop for the agent.
    This function runs in a separate thread and periodically checks for pending tasks.
    For each pending task, it assigns a request handler (e.g., TogetherAIRequest)
    and then tells the task to process itself.
    """
    logging.info("Agent_loop thread started.")
    while True:
        try:
            current_tasks_snapshot = list(tasks_list)

            if not current_tasks_snapshot:
                pass
            else:
                pending_tasks_to_process = [task for task in current_tasks_snapshot if task.status == 'pending']

                if pending_tasks_to_process:
                    logging.info(f"Found {len(pending_tasks_to_process)} pending tasks to process.")
                    for task in pending_tasks_to_process:
                        if task.status == 'pending':
                            log_entry_pickup = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Picking up task: {task.id} - {task.description[:50]}..."
                            agent_logs.append(log_entry_pickup)
                            logging.info(f"Agent picking up task ID: {task.id} - '{task.description[:50]}...'") # Keep console log

                            if not task.requests:
                                task.add_request(TogetherAIRequest())
                                logging.info(f"Added TogetherAIRequest to task {task.id}.")
                            else:
                                logging.info(f"Task {task.id} already has {len(task.requests)} request(s). Proceeding to process.")

                            task.process()

                            # Log outcome
                            if task.status == "completed":
                                log_entry_done = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task.id} completed. Result: {str(task.result)[:100]}..."
                                agent_logs.append(log_entry_done)
                            elif task.status == "failed":
                                log_entry_fail = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task.id} failed. Error: {str(task.error_message)[:100]}..."
                                agent_logs.append(log_entry_fail)

                            # Cap the logs
                            if len(agent_logs) > MAX_LOG_ENTRIES:
                                agent_logs.pop(0)
                # else:
                    # logging.debug("No pending tasks found in this iteration. Sleeping.")


        except Exception as e:
            # Catch-all for unexpected errors within the loop to prevent the agent thread from crashing.
            logging.error(f"Critical error in agent_loop: {e}", exc_info=True)
            # Avoid continuous fast error loops in case of persistent issues by still sleeping.

        time.sleep(5) # Pause for 5 seconds before checking for new tasks again.

if __name__ == "__main__":
    # This block executes when the script is run directly (e.g., python -m june_agent).
    logging.info("June agent process starting...")

    # Initialize the global tasks list. This list will be shared with the web service.
    # tasks_list is already defined globally, so just ensuring it's clear it's used from here.

    # Start the agent_loop in a daemon thread.
    # Daemon threads automatically exit when the main program (Flask server in this case) exits.
    logging.info("Initializing and starting agent_loop thread...")
    agent_thread = threading.Thread(target=agent_loop, daemon=True)
    agent_thread.start()

    # Create the Flask application using the factory from web_service.
    # Pass the shared tasks_list, Task class, and agent_logs to the factory.
    logging.info("Creating Flask application...")
    flask_app = create_app(
        tasks_list_ref=tasks_list,
        task_class_ref=Task,
        agent_logs_ref=agent_logs
    )

    # Start the Flask development server.
    # It will listen on all available network interfaces (0.0.0.0) on port 8080.
    logging.info("Starting Flask web server on host 0.0.0.0, port 8080...")
    # Note: flask_app.run() is blocking for the main thread. The agent_loop runs in its daemon thread.
    flask_app.run(host='0.0.0.0', port=8080)

    logging.info("June agent process shutting down.") # This line might only be reached if app.run() is non-blocking or server is stopped.
