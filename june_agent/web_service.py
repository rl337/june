import logging
from flask import Flask, request, jsonify, make_response # Added make_response
from pydantic import ValidationError # For catching Pydantic validation errors

# ModelService interface and Pydantic schemas
from june_agent.services.model_service_interface import IModelService
from june_agent.models_v2.pydantic_models import (
    InitiativeSchema, InitiativeCreate, InitiativeUpdate,
    TaskSchema, TaskCreate, TaskUpdate
)
# Domain Task constants are needed for status endpoint logic
from june_agent.task import Task as DomainTask

# Imports for /status endpoint if it used direct DB access are no longer needed here
# from june_agent.services.sqlalchemy_database import get_db
# from sqlalchemy.orm import Session
# from june_agent.models_v2.orm_models import InitiativeORM, TaskORM


logger = logging.getLogger(__name__)

def create_app(model_service_ref: IModelService, agent_logs_ref: list) -> Flask:
    """
    Application factory for the June Agent's Flask web service.

    Configures Flask, registers blueprints (if any), error handlers,
    and API routes. It uses an IModelService instance for data operations,
    making it independent of the specific database implementation.

    Args:
        model_service_ref: An instance of a class implementing IModelService,
                           used for all data interactions.
        agent_logs_ref: A list (shared reference) where agent activity logs are stored
                        for display in the UI.

    Returns:
        The configured Flask application instance.
    """
    app = Flask(__name__, static_folder='../static', static_url_path='/static')

    # Store references to the model service and agent logs in Flask's app config
    # for easy access within route handlers.
    app.config['model_service'] = model_service_ref
    app.config['agent_logs_ref'] = agent_logs_ref

    # --- Error Handlers ---
    @app.errorhandler(ValidationError)
    def handle_pydantic_validation_error(error: ValidationError):
        """Handles Pydantic validation errors for incoming request data."""
        logger.warning(f"Pydantic validation error: {error.errors()}", exc_info=False)
        return jsonify({"detail": error.errors()}), 400

    @app.errorhandler(Exception)
    def handle_generic_error(error: Exception):
        """Handles unexpected server errors."""
        logger.error(f"An unexpected error occurred on the server: {error}", exc_info=True)
        # In a production environment, you might want to return a more generic error message
        # and log the specifics (as done here).
        return jsonify({"detail": "An internal server error occurred. Please check server logs."}), 500

    @app.errorhandler(404)
    def handle_flask_not_found_error(error):
        """Handles 404 errors (resource not found) raised by Flask."""
        return jsonify({"detail": "The requested API endpoint or resource was not found."}), 404

    # --- Static Routes ---
    @app.route('/')
    def serve_index():
        """Serves the main HTML page for the agent UI."""
        return app.send_static_file('index.html')

    @app.route('/logs')
    def get_agent_logs():
        """Provides agent activity logs for the UI."""
        logs = app.config.get('agent_logs_ref', [])
        return jsonify(list(logs)) # Return a copy

    # --- API Routes ---

    @app.route('/status', methods=['GET'])
    def get_status():
        """
        Provides the current operational status of the agent, including
        counts of initiatives and tasks by their status.
        This endpoint currently uses direct DB access for aggregate counts
        via `get_db()` but ideally would use methods on the ModelService.
        """
        # This endpoint performs specific aggregate queries.
        # Ideally, these would be methods on IModelService.
        # For now, using get_db() directly as a temporary measure if IModelService
        # doesn't have get_total_initiatives_count(), get_tasks_count_by_status() etc.
        # This endpoint now uses the ModelService for all data.
        model_service: IModelService = app.config['model_service']

        total_initiatives = model_service.get_total_initiatives_count()
        task_counts = model_service.get_task_counts_by_status() # Dict[str, int]

        total_tasks = sum(task_counts.values())

        # Determine overall agent status based on active task counts.
        active_processing_count = (
            task_counts.get(DomainTask.STATUS_ASSESSING, 0) +
            task_counts.get(DomainTask.STATUS_EXECUTING, 0) +
            task_counts.get(DomainTask.STATUS_RECONCILING, 0) +
            task_counts.get(DomainTask.STATUS_PENDING_SUBTASKS, 0)
        )
        current_agent_status = "processing" if active_processing_count > 0 else "idle"

        return jsonify({
            'agent_overall_status': current_agent_status,
            'total_initiatives': total_initiatives,
            'total_tasks': total_tasks,
            'status_counts': task_counts
        })

    # --- Initiative API Endpoints ---

    @app.route('/initiatives', methods=['GET'])
    def list_initiatives():
        """Lists all initiatives, optionally paginated."""
        model_service: IModelService = app.config['model_service']
        # TODO: Add skip/limit query parameters from request.args
        initiative_schemas = model_service.get_all_initiatives()
        return jsonify([s.model_dump() for s in initiative_schemas])

    @app.route('/initiatives', methods=['POST'])
    def create_initiative_api():
        """Creates a new initiative from JSON payload."""
        model_service: IModelService = app.config['model_service']
        initiative_data = InitiativeCreate(**request.get_json()) # Validates request data
        created_initiative_schema = model_service.create_initiative(initiative_data)
        return make_response(jsonify(created_initiative_schema.model_dump()), 201)

    @app.route('/initiatives/<string:initiative_id>', methods=['GET'])
    def get_initiative_detail(initiative_id: str):
        """Retrieves details for a specific initiative by its ID."""
        model_service: IModelService = app.config['model_service']
        initiative_schema = model_service.get_initiative(initiative_id)
        if not initiative_schema:
            return jsonify({"detail": "Initiative not found"}), 404
        return jsonify(initiative_schema.model_dump())

    @app.route('/initiatives/<string:initiative_id>', methods=['PUT'])
    def update_initiative_api(initiative_id: str):
        """Updates an existing initiative by its ID from JSON payload."""
        model_service: IModelService = app.config['model_service']
        update_data = InitiativeUpdate(**request.get_json()) # Validates update data
        updated_schema = model_service.update_initiative(initiative_id, update_data)
        if not updated_schema:
            return jsonify({"detail": "Initiative not found for update"}), 404
        return jsonify(updated_schema.model_dump())

    @app.route('/initiatives/<string:initiative_id>', methods=['DELETE'])
    def delete_initiative_api(initiative_id: str):
        """Deletes an initiative by its ID."""
        model_service: IModelService = app.config['model_service']
        success = model_service.delete_initiative(initiative_id)
        if not success:
            return jsonify({"detail": "Initiative not found for deletion"}), 404
        return jsonify({"message": "Initiative deleted successfully"}), 200 # OK (or 204 No Content)

    # --- Task API Endpoints ---

    @app.route('/tasks', methods=['GET'])
    def list_tasks():
        """
        Lists tasks, optionally filtered by initiative_id.
        Supports pagination via query parameters (TODO: implement skip/limit).
        """
        model_service: IModelService = app.config['model_service']
        initiative_id_filter = request.args.get('initiative_id')
        # TODO: Add skip/limit query parameters from request.args to service call
        task_schemas = model_service.get_all_tasks(initiative_id=initiative_id_filter)
        return jsonify([s.model_dump() for s in task_schemas])

    @app.route('/tasks', methods=['POST'])
    def create_task_api():
        """Creates a new task from JSON payload, associated with an initiative."""
        model_service: IModelService = app.config['model_service']
        model_service: IModelService = app.config['model_service']
        json_data = request.get_json()

        if not isinstance(json_data, dict):
             # This provides a more specific error if request is not JSON or not an object.
             return jsonify({"detail": "Invalid JSON payload: Expected a JSON object."}), 400

        # `initiative_id` is crucial and must be provided in the payload for task creation.
        if 'initiative_id' not in json_data or not json_data['initiative_id']:
            # Raise ValidationError to be handled by the errorhandler for consistent 400 response.
            errors = [{"loc": ["initiative_id"], "msg": "Field required and cannot be empty.", "type": "value_error.missing"}]
            raise ValidationError.from_exception_data(TaskCreate, errors) # type: ignore

        initiative_id = json_data.pop('initiative_id') # Extract for service call, remove from TaskCreate data.
        task_create_data = TaskCreate(**json_data) # Validate remaining fields against TaskCreate.

        # Check if the parent initiative exists before attempting to create the task.
        if not model_service.get_initiative(initiative_id):
             return jsonify({"detail": f"Parent initiative with ID '{initiative_id}' not found."}), 404 # Not Found

        created_task_schema = model_service.create_task(task_create_data, initiative_id)
        return make_response(jsonify(created_task_schema.model_dump()), 201) # Created

    @app.route('/tasks/<string:task_id>', methods=['GET'])
    def get_task_detail(task_id: str):
        """Retrieves details for a specific task by its ID."""
        model_service: IModelService = app.config['model_service']
        task_schema = model_service.get_task(task_id)
        if not task_schema:
            return jsonify({"detail": "Task not found"}), 404
        return jsonify(task_schema.model_dump())

    @app.route('/tasks/<string:task_id>', methods=['PUT'])
    def update_task_api(task_id: str):
        """Updates an existing task by its ID from JSON payload."""
        model_service: IModelService = app.config['model_service']
        update_data_pydantic = TaskUpdate(**request.get_json()) # Validates
        updated_schema = model_service.update_task(task_id, update_data_pydantic)
        if not updated_schema:
            return jsonify({"detail": "Task not found for update"}), 404
        return jsonify(updated_schema.model_dump())

    return app
