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

# For /status if direct ORM queries are kept temporarily
from june_agent.db_v2 import get_db
from sqlalchemy.orm import Session
from june_agent.models_v2.orm_models import InitiativeORM, TaskORM


logger = logging.getLogger(__name__)

def create_app(model_service_ref: IModelService, agent_logs_ref: list):
    """Application factory for the Flask web service using ModelService."""
    app = Flask(__name__, static_folder='../static', static_url_path='/static')

    app.config['model_service'] = model_service_ref
    app.config['agent_logs_ref'] = agent_logs_ref

    @app.errorhandler(ValidationError)
    def handle_pydantic_validation_error(error: ValidationError):
        logger.warning(f"Pydantic validation error: {error.errors()}", exc_info=False) # exc_info=False for brevity
        return jsonify({"detail": error.errors()}), 400

    # Using a more generic error handler for now for DB/unexpected issues
    @app.errorhandler(Exception)
    def handle_generic_error(error: Exception):
        # Log the full error internally
        logger.error(f"An unexpected error occurred: {error}", exc_info=True)
        # Check if it's a known DB error type if more specific handling is needed later
        # from sqlalchemy.exc import SQLAlchemyError
        # if isinstance(error, SQLAlchemyError):
        #     return jsonify({"detail": "A database error occurred."}), 500
        return jsonify({"detail": "An internal server error occurred."}), 500

    @app.errorhandler(404) # Handles Flask's default 404
    def handle_flask_not_found_error(error): # Parameter name changed to avoid conflict
        # This will catch errors from Flask if a route is not found,
        # or if abort(404) is called.
        return jsonify({"detail": "The requested resource was not found."}), 404


    @app.route('/')
    def serve_index():
        return app.send_static_file('index.html')

    @app.route('/logs')
    def get_agent_logs():
        logs = app.config.get('agent_logs_ref', [])
        return jsonify(list(logs))

    @app.route('/status', methods=['GET'])
    def get_status():
        # This endpoint performs specific aggregate queries.
        # Ideally, these would be methods on IModelService.
        # For now, using get_db() directly as a temporary measure if IModelService
        # doesn't have get_total_initiatives_count(), get_tasks_count_by_status() etc.
        # This is a deviation from pure ModelService usage for this specific endpoint.
        # TODO: Refactor /status to use methods from ModelService once they are added.
        db: Session = next(get_db())
        try:
            total_initiatives = db.query(InitiativeORM).count()
            total_tasks = db.query(TaskORM).count()

            status_counts = {}
            for status_val in [DomainTask.STATUS_PENDING, DomainTask.STATUS_ASSESSING, DomainTask.STATUS_EXECUTING,
                               DomainTask.STATUS_RECONCILING, DomainTask.STATUS_PENDING_SUBTASKS,
                               DomainTask.STATUS_COMPLETED, DomainTask.STATUS_FAILED]:
                status_counts[status_val] = db.query(TaskORM).filter(TaskORM.status == status_val).count()

            active_processing_count = (status_counts[DomainTask.STATUS_ASSESSING] +
                                       status_counts[DomainTask.STATUS_EXECUTING] +
                                       status_counts[DomainTask.STATUS_RECONCILING] +
                                       status_counts[DomainTask.STATUS_PENDING_SUBTASKS])
            current_agent_status = "processing" if active_processing_count > 0 else "idle"

            return jsonify({
                'agent_overall_status': current_agent_status,
                'total_initiatives': total_initiatives,
                'total_tasks': total_tasks,
                'status_counts': status_counts
            })
        finally:
            db.close()

    @app.route('/initiatives', methods=['GET'])
    def list_initiatives():
        model_service: IModelService = app.config['model_service']
        # Assuming get_all_initiatives takes optional skip/limit
        initiative_schemas = model_service.get_all_initiatives()
        return jsonify([s.dict() for s in initiative_schemas])

    @app.route('/initiatives', methods=['POST'])
    def create_initiative_api():
        model_service: IModelService = app.config['model_service']
        initiative_data = InitiativeCreate(**request.get_json()) # Validates request
        created_initiative_schema = model_service.create_initiative(initiative_data)
        return make_response(jsonify(created_initiative_schema.dict()), 201)

    @app.route('/initiatives/<string:initiative_id>', methods=['GET'])
    def get_initiative_detail(initiative_id: str):
        model_service: IModelService = app.config['model_service']
        initiative_schema = model_service.get_initiative(initiative_id)
        if not initiative_schema:
            return jsonify({"detail": "Initiative not found"}), 404
        return jsonify(initiative_schema.dict())

    @app.route('/initiatives/<string:initiative_id>', methods=['PUT'])
    def update_initiative_api(initiative_id: str):
        model_service: IModelService = app.config['model_service']
        update_data = InitiativeUpdate(**request.get_json()) # Validates
        updated_schema = model_service.update_initiative(initiative_id, update_data)
        if not updated_schema:
            return jsonify({"detail": "Initiative not found for update"}), 404
        return jsonify(updated_schema.dict())

    @app.route('/initiatives/<string:initiative_id>', methods=['DELETE'])
    def delete_initiative_api(initiative_id: str):
        model_service: IModelService = app.config['model_service']
        success = model_service.delete_initiative(initiative_id)
        if not success:
            return jsonify({"detail": "Initiative not found for deletion"}), 404
        return jsonify({"message": "Initiative deleted successfully"}), 200


    @app.route('/tasks', methods=['GET'])
    def list_tasks():
        model_service: IModelService = app.config['model_service']
        initiative_id_filter = request.args.get('initiative_id')
        # get_all_tasks returns List[TaskSchema]
        task_schemas = model_service.get_all_tasks(initiative_id=initiative_id_filter)
        return jsonify([s.dict() for s in task_schemas])

    @app.route('/tasks', methods=['POST'])
    def create_task_api():
        model_service: IModelService = app.config['model_service']
        json_data = request.get_json()

        if not isinstance(json_data, dict): # Ensure json_data is a dict
             raise ValidationError([{"loc": ["request_body"], "msg": "Request body must be a JSON object", "type": "value_error.jsonobject"}], TaskCreate)

        if 'initiative_id' not in json_data or not json_data['initiative_id']: # check for presence and non-empty
            # Manually create a Pydantic-like error structure for consistency
            # This will be caught by the ValidationError handler
            raise ValidationError([{"loc": ["initiative_id"], "msg": "Field required and cannot be empty", "type": "value_error.missing"}], TaskCreate) # type: ignore

        initiative_id = json_data.pop('initiative_id')
        task_create_data = TaskCreate(**json_data) # Validate other fields

        # Verify initiative exists (ModelService's create_task should handle this or raise error)
        # For robustness, can check here too:
        if not model_service.get_initiative(initiative_id):
             return jsonify({"detail": f"Parent initiative with ID '{initiative_id}' not found."}), 404

        created_task_schema = model_service.create_task(task_create_data, initiative_id)
        return make_response(jsonify(created_task_schema.dict()), 201)

    @app.route('/tasks/<string:task_id>', methods=['GET'])
    def get_task_detail(task_id: str):
        model_service: IModelService = app.config['model_service']
        task_schema = model_service.get_task(task_id) # Returns TaskSchema
        if not task_schema:
            return jsonify({"detail": "Task not found"}), 404
        return jsonify(task_schema.dict())

    @app.route('/tasks/<string:task_id>', methods=['PUT'])
    def update_task_api(task_id: str):
        model_service: IModelService = app.config['model_service']
        update_data_pydantic = TaskUpdate(**request.get_json()) # Validates
        updated_schema = model_service.update_task(task_id, update_data_pydantic)
        if not updated_schema:
            return jsonify({"detail": "Task not found for update"}), 404
        return jsonify(updated_schema.dict())

    return app
