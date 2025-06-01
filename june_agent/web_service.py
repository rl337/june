import logging
from flask import Flask, request, jsonify, make_response # Added make_response
from pydantic import ValidationError # For catching Pydantic validation errors

# SQLAlchemy and new model imports
from june_agent.db_v2 import get_db # For DB session management
from sqlalchemy.orm import Session # For type hinting
from sqlalchemy.exc import SQLAlchemyError # For DB errors

# Refactored service-like classes for Initiative and Task
from june_agent.initiative import Initiative
from june_agent.task import Task

# Pydantic schemas for request validation and response formatting
from june_agent.models_v2.pydantic_models import (
    InitiativeSchema, InitiativeCreate, InitiativeUpdate,
    TaskSchema, TaskCreate, TaskUpdate
)
# ORM models might be needed for direct queries if service classes don't cover all cases
# from june_agent.models_v2.orm_models import InitiativeORM, TaskORM

logger = logging.getLogger(__name__)

def create_app(agent_logs_ref: list): # db_manager_ref removed
    """Application factory for the Flask web service (SQLAlchemy version)."""
    app = Flask(__name__, static_folder='../static', static_url_path='/static')
    app.config['agent_logs_ref'] = agent_logs_ref

    @app.errorhandler(ValidationError)
    def handle_pydantic_validation_error(error: ValidationError):
        logger.warning(f"Pydantic validation error: {error.errors()}", exc_info=True)
        return jsonify({"detail": error.errors()}), 400 # Standard FastAPI-like error response

    @app.errorhandler(SQLAlchemyError)
    def handle_sqlalchemy_error(error: SQLAlchemyError):
        logger.error(f"Database operation failed: {error}", exc_info=True)
        # db.rollback() might be needed if session is managed here, but get_db handles it
        return jsonify({"detail": "A database error occurred."}), 500

    @app.errorhandler(404) # Generic 404 handler for Flask
    def handle_flask_not_found_error(error): # Parameter name changed to avoid conflict
        return jsonify({"detail": "Resource not found."}), 404

    @app.route('/')
    def serve_index():
        return app.send_static_file('index.html')

    @app.route('/logs')
    def get_agent_logs():
        logs = app.config.get('agent_logs_ref', [])
        return jsonify(list(logs))

    @app.route('/status', methods=['GET'])
    def get_status():
        db: Session = next(get_db())
        try:
            # Use direct ORM queries for counts for simplicity here
            from june_agent.models_v2.orm_models import InitiativeORM, TaskORM # Local import

            total_initiatives = db.query(InitiativeORM).count()
            total_tasks = db.query(TaskORM).count()

            status_counts = {}
            for status_val in [Task.STATUS_PENDING, Task.STATUS_ASSESSING, Task.STATUS_EXECUTING,
                               Task.STATUS_RECONCILING, Task.STATUS_PENDING_SUBTASKS,
                               Task.STATUS_COMPLETED, Task.STATUS_FAILED]:
                status_counts[status_val] = db.query(TaskORM).filter(TaskORM.status == status_val).count()

            active_processing_count = (status_counts[Task.STATUS_ASSESSING] +
                                       status_counts[Task.STATUS_EXECUTING] +
                                       status_counts[Task.STATUS_RECONCILING] +
                                       status_counts[Task.STATUS_PENDING_SUBTASKS])
            current_agent_status = "processing" if active_processing_count > 0 else "idle"

            return jsonify({
                'agent_overall_status': current_agent_status,
                'total_initiatives': total_initiatives,
                'total_tasks': total_tasks,
                'status_counts': status_counts
            })
        except Exception as e: # Catch any other unexpected error during status fetch
            logger.error(f"Error fetching status from DB (SQLAlchemy): {e}", exc_info=True)
            return jsonify({'error': 'Failed to retrieve status from database'}), 500
        finally:
            db.close()

    @app.route('/initiatives', methods=['GET'])
    def list_initiatives():
        db: Session = next(get_db())
        try:
            initiative_schemas = Initiative.get_all(db) # Returns List[InitiativeSchema]
            return jsonify([s.dict() for s in initiative_schemas])
        finally:
            db.close()

    @app.route('/initiatives', methods=['POST'])
    def create_initiative_api():
        db: Session = next(get_db())
        try:
            initiative_data = InitiativeCreate(**request.get_json())
            created_initiative_schema = Initiative.create(db, initiative_data)
            return make_response(jsonify(created_initiative_schema.dict()), 201)
        except ValidationError as ve: # Handled by errorhandler, but can catch for specific logging
            logger.warning(f"Initiative creation validation failed: {ve.errors()}", exc_info=True)
            raise # Re-raise to be caught by the errorhandler
        except Exception as e: # Catch other errors during creation
            logger.error(f"Error creating initiative: {e}", exc_info=True)
            # db.rollback() is handled if error occurs in Initiative.create or by SQLAlchemyError handler
            return jsonify({"detail": "Failed to create initiative."}), 500
        finally:
            db.close()

    @app.route('/initiatives/<string:initiative_id>', methods=['GET'])
    def get_initiative_detail(initiative_id: str):
        db: Session = next(get_db())
        try:
            initiative_schema = Initiative.get(db, initiative_id) # Returns InitiativeSchema or None
            if not initiative_schema:
                return jsonify({"detail": "Initiative not found"}), 404
            return jsonify(initiative_schema.dict())
        finally:
            db.close()

    @app.route('/initiatives/<string:initiative_id>', methods=['PUT'])
    def update_initiative_api(initiative_id: str):
        db: Session = next(get_db())
        try:
            update_data = InitiativeUpdate(**request.get_json())
            updated_schema = Initiative.update(db, initiative_id, update_data)
            if not updated_schema:
                return jsonify({"detail": "Initiative not found for update"}), 404
            return jsonify(updated_schema.dict())
        finally:
            db.close()

    @app.route('/initiatives/<string:initiative_id>', methods=['DELETE'])
    def delete_initiative_api(initiative_id: str):
        db: Session = next(get_db())
        try:
            success = Initiative.delete(db, initiative_id)
            if not success:
                return jsonify({"detail": "Initiative not found for deletion"}), 404
            return jsonify({"message": "Initiative deleted successfully"}), 200 # Or 204 No Content
        finally:
            db.close()


    @app.route('/tasks', methods=['GET'])
    def list_tasks():
        db: Session = next(get_db())
        try:
            initiative_id_filter = request.args.get('initiative_id')
            # Task.get_all returns List[Task domain obj]
            task_domain_objects = Task.get_all(db, initiative_id=initiative_id_filter)
            # Convert to Pydantic schemas
            task_schemas = [task.to_pydantic_schema(db) for task in task_domain_objects]
            return jsonify([s.dict() for s in task_schemas])
        finally:
            db.close()

    @app.route('/tasks', methods=['POST'])
    def create_task_api():
        db: Session = next(get_db())
        try:
            json_data = request.get_json()
            # Ensure initiative_id is present in the payload for TaskCreate
            if 'initiative_id' not in json_data:
                return jsonify({"detail": "Missing 'initiative_id' in request."}), 400

            initiative_id = json_data.pop('initiative_id') # Remove it as TaskCreate doesn't expect it directly

            task_create_data = TaskCreate(**json_data) # Validate the rest of the data

            # Verify initiative exists before creating task under it
            parent_initiative_schema = Initiative.get(db, initiative_id)
            if not parent_initiative_schema:
                return jsonify({"detail": f"Initiative with ID '{initiative_id}' not found."}), 404

            created_task_schema = Task.create(db, task_create_data, initiative_id) # Use the new Task.create
            return make_response(jsonify(created_task_schema.dict()), 201)
        except ValidationError as ve:
            logger.warning(f"Task creation validation failed: {ve.errors()}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            return jsonify({"detail": "Failed to create task."}), 500
        finally:
            db.close()

    @app.route('/tasks/<string:task_id>', methods=['GET'])
    def get_task_detail(task_id: str):
        db: Session = next(get_db())
        try:
            task_domain_obj = Task.get(db, task_id) # Returns Task domain obj or None
            if not task_domain_obj:
                return jsonify({"detail": "Task not found"}), 404
            task_schema = task_domain_obj.to_pydantic_schema(db) # Pass db for subtask ID loading
            return jsonify(task_schema.dict())
        finally:
            db.close()

    @app.route('/tasks/<string:task_id>', methods=['PUT'])
    def update_task_api(task_id: str):
        db: Session = next(get_db())
        try:
            update_data_pydantic = TaskUpdate(**request.get_json())

            # Task.update method needs to be added to task.py
            # For now, fetching, updating specific fields, and saving:
            task_domain = Task.get(db, task_id)
            if not task_domain:
                return jsonify({"detail": "Task not found for update"}), 404

            update_data_dict = update_data_pydantic.dict(exclude_unset=True)
            needs_save = False
            for key, value in update_data_dict.items():
                if hasattr(task_domain, key): # Check if attribute exists on domain model
                    setattr(task_domain, key, value)
                    needs_save = True

            if needs_save:
                task_domain.save(db) # Persist changes

            updated_schema = task_domain.to_pydantic_schema(db)
            return jsonify(updated_schema.dict())
        finally:
            db.close()

    # Note: DELETE /tasks/<task_id> is not implemented here but would follow a similar pattern.

    return app
