import logging
from flask import Flask, request, jsonify
from .task import Task # Assuming Task is in .task

# Configure logging for this module
# logger = logging.getLogger(__name__) # Preferred for libraries
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')


def create_app(tasks_list_ref: list, task_class_ref: type[Task], agent_logs_ref: list):
    """
    Application factory for the Flask web service.

    Args:
        tasks_list_ref (list): A reference to the global list holding all tasks.
        task_class_ref (type[Task]): A reference to the Task class.
        agent_logs_ref (list): A reference to the global list holding agent logs.

    Returns:
        Flask: The configured Flask application instance.
    """
    # Ensure static files are served from 'june_agent/static'
    # __name__ here is 'june_agent.web_service'
    # static_folder path is relative to the location of web_service.py
    app = Flask(__name__, static_folder='../static', static_url_path='/static')

    # The global agent_status might be managed by the main agent logic.
    # For the web service, it can report a simple status or a derived one.
    # For now, let's assume a simple static status for the web service itself.
    # More complex status reporting can be derived from task_list_ref or other sources.
    # agent_overall_status = "running" # This could be passed in or managed differently.

    @app.route('/')
    def serve_index():
        """Serves the main index.html page from the static folder."""
        # app.send_static_file will look in the app.static_folder,
        # which was configured as '../static' relative to web_service.py,
        # effectively pointing to 'june_agent/static/'.
        return app.send_static_file('index.html')

    @app.route('/logs')
    def get_agent_logs():
        """API endpoint to get the agent's activity logs."""
        logs = app.config.get('agent_logs_ref', [])
        # Return logs, perhaps newest first if that's desired for display
        # For now, returning in collected order (oldest first, newest last)
        return jsonify(list(logs))

    @app.route('/status', methods=['GET'])
    def get_status():
        """
        API endpoint to get the current overall status of the agent and task counts.
        """
        # Calculate task status counts from the shared tasks_list_ref
        pending_tasks = sum(1 for task_obj in tasks_list_ref if task_obj.status == 'pending')
        processing_tasks = sum(1 for task_obj in tasks_list_ref if task_obj.status == 'processing')
        completed_tasks = sum(1 for task_obj in tasks_list_ref if task_obj.status == 'completed')
        failed_tasks = sum(1 for task_obj in tasks_list_ref if task_obj.status == 'failed')

        # The 'agent_overall_status' could be more dynamic in a mature system
        # For now, if there are processing tasks, we can indicate it's busy, else idle.
        current_agent_status = "processing" if processing_tasks > 0 else "idle"

        return jsonify({
            'agent_overall_status': current_agent_status,
            'total_tasks': len(tasks_list_ref),
            'pending_tasks': pending_tasks,
            'processing_tasks': processing_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks
        })

    @app.route('/tasks', methods=['GET', 'POST'])
    def manage_tasks():
        """
        API endpoint to manage tasks.
        - GET: Retrieves a list of all tasks.
        - POST: Creates a new task.
        """
        if request.method == 'GET':
            # Convert each Task object in tasks_list_ref to its dictionary representation
            return jsonify([task_obj.to_dict() for task_obj in tasks_list_ref])

        elif request.method == 'POST':
            data = request.get_json()
            # Enhanced validation for description
            if not data or 'description' not in data:
                logging.warning("Task creation failed via API: 'description' key missing.")
                return jsonify({'error': "Missing 'description' key in request JSON."}), 400

            description_value = data['description']
            if not isinstance(description_value, str) or not description_value.strip():
                logging.warning(f"Task creation failed via API: description is not a non-empty string. Value: {description_value!r}")
                return jsonify({'error': 'Task description must be a non-empty string.'}), 400

            description = description_value.strip()

            # Use the provided task_class_ref to create a new task instance
            new_task_obj = task_class_ref(description=description)

            # The agent loop will be responsible for adding the appropriate APIRequest to the task.
            # The web service only creates the task entry.
            tasks_list_ref.append(new_task_obj)

            logging.info(f"New task created via API: ID {new_task_obj.id}, Description: '{new_task_obj.description[:50]}...'")
            return jsonify(new_task_obj.to_dict()), 201 # 201 Created

    app.config['tasks_list_ref'] = tasks_list_ref
    app.config['agent_logs_ref'] = agent_logs_ref # Store agent_logs_ref in app config
    return app
