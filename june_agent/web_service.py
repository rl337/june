import logging
from flask import Flask, request, jsonify
from june_agent.db import DatabaseManager # Added
from june_agent.initiative import Initiative # Added
from june_agent.task import Task

# Configure logging
logger = logging.getLogger(__name__)

def create_app(db_manager_ref: DatabaseManager, agent_logs_ref: list):
    """Application factory for the Flask web service."""
    app = Flask(__name__, static_folder='../static', static_url_path='/static')

    app.config['db_manager'] = db_manager_ref
    app.config['agent_logs_ref'] = agent_logs_ref

    @app.route('/')
    def serve_index():
        return app.send_static_file('index.html')

    @app.route('/logs')
    def get_agent_logs():
        logs = app.config.get('agent_logs_ref', [])
        return jsonify(list(logs))

    @app.route('/status', methods=['GET'])
    def get_status():
        db_manager = app.config['db_manager']
        try:
            total_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks")[0]
            pending_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks WHERE status = ?", (Task.STATUS_PENDING,))[0]
            assessing_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks WHERE status = ?", (Task.STATUS_ASSESSING,))[0]
            executing_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks WHERE status = ?", (Task.STATUS_EXECUTING,))[0]
            reconciling_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks WHERE status = ?", (Task.STATUS_RECONCILING,))[0]
            pending_sub_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks WHERE status = ?", (Task.STATUS_PENDING_SUBTASKS,))[0]
            completed_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks WHERE status = ?", (Task.STATUS_COMPLETED,))[0]
            failed_tasks = db_manager.fetch_one("SELECT COUNT(*) as count FROM tasks WHERE status = ?", (Task.STATUS_FAILED,))[0]

            total_initiatives = db_manager.fetch_one("SELECT COUNT(*) as count FROM initiatives")[0]

            active_processing_count = assessing_tasks + executing_tasks + reconciling_tasks + pending_sub_tasks
            current_agent_status = "processing" if active_processing_count > 0 else "idle"

            return jsonify({
                'agent_overall_status': current_agent_status,
                'total_initiatives': total_initiatives,
                'total_tasks': total_tasks,
                'status_counts': {
                    Task.STATUS_PENDING: pending_tasks,
                    Task.STATUS_ASSESSING: assessing_tasks,
                    Task.STATUS_EXECUTING: executing_tasks,
                    Task.STATUS_RECONCILING: reconciling_tasks,
                    Task.STATUS_PENDING_SUBTASKS: pending_sub_tasks,
                    Task.STATUS_COMPLETED: completed_tasks,
                    Task.STATUS_FAILED: failed_tasks,
                }
            })
        except Exception as e:
            logger.error(f"Error fetching status from DB: {e}", exc_info=True)
            return jsonify({'error': 'Failed to retrieve status from database'}), 500

    @app.route('/initiatives', methods=['GET'])
    def get_initiatives():
        db_manager = app.config['db_manager']
        try:
            initiatives = Initiative.load_all(db_manager)
            # For each initiative, load its tasks to populate task_ids for the UI
            # This could be heavy if there are many initiatives and tasks.
            # Consider optimizing if performance becomes an issue (e.g., selective loading).
            for init in initiatives:
                init.tasks = Task.load_all(db_manager, initiative_id=init.id) # Populate tasks for to_dict
            return jsonify([init.to_dict() for init in initiatives])
        except Exception as e:
            logger.error(f"Error fetching initiatives: {e}", exc_info=True)
            return jsonify({'error': 'Failed to retrieve initiatives'}), 500

    @app.route('/initiatives/<string:initiative_id>', methods=['GET'])
    def get_initiative_detail(initiative_id):
        db_manager = app.config['db_manager']
        try:
            initiative = Initiative.load(initiative_id, db_manager)
            if not initiative:
                return jsonify({'error': 'Initiative not found'}), 404
            # Load tasks for this specific initiative to populate task_ids
            initiative.tasks = Task.load_all(db_manager, initiative_id=initiative.id)
            return jsonify(initiative.to_dict())
        except Exception as e:
            logger.error(f"Error fetching initiative {initiative_id}: {e}", exc_info=True)
            return jsonify({'error': 'Failed to retrieve initiative details'}), 500

    @app.route('/tasks', methods=['GET', 'POST'])
    def manage_tasks():
        db_manager = app.config['db_manager']
        if request.method == 'GET':
            initiative_id_filter = request.args.get('initiative_id')
            try:
                tasks = Task.load_all(db_manager, initiative_id=initiative_id_filter)
                return jsonify([task.to_dict() for task in tasks])
            except Exception as e:
                logger.error(f"Error fetching tasks: {e}", exc_info=True)
                return jsonify({'error': 'Failed to retrieve tasks'}), 500

        elif request.method == 'POST':
            data = request.get_json()
            if not data or 'description' not in data or 'initiative_id' not in data:
                return jsonify({'error': "Missing 'description' or 'initiative_id' in request."}), 400

            description = data['description'].strip()
            initiative_id = data['initiative_id'].strip()

            if not description or not initiative_id:
                return jsonify({'error': "'description' and 'initiative_id' must be non-empty strings."}), 400

            # Verify initiative exists
            parent_initiative = Initiative.load(initiative_id, db_manager)
            if not parent_initiative:
                return jsonify({'error': f"Initiative with ID '{initiative_id}' not found."}), 404

            try:
                # Create new task, initially in pending status and assessment phase
                new_task = Task(
                    description=description,
                    db_manager=db_manager,
                    initiative_id=initiative_id,
                    status=Task.STATUS_PENDING, # Explicitly set
                    phase=Task.PHASE_ASSESSMENT # Explicitly set
                )
                new_task.save()
                logger.info(f"New task '{new_task.id}' created via API for initiative '{initiative_id}'.")
                return jsonify(new_task.to_dict()), 201
            except Exception as e:
                logger.error(f"Error creating task via API: {e}", exc_info=True)
                return jsonify({'error': 'Failed to create task'}), 500

    @app.route('/tasks/<string:task_id>', methods=['GET'])
    def get_task_detail(task_id):
        db_manager = app.config['db_manager']
        try:
            task = Task.load(task_id, db_manager)
            if not task:
                return jsonify({'error': 'Task not found'}), 404
            task.load_subtasks() # Ensure subtasks are loaded for the dict representation
            return jsonify(task.to_dict())
        except Exception as e:
            logger.error(f"Error fetching task {task_id}: {e}", exc_info=True)
            return jsonify({'error': 'Failed to retrieve task details'}), 500

    return app
