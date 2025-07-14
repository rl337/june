import pytest
import json
from june_agent.web_service import create_app
from june_agent.task import Task # Using the actual Task class
# from june_agent.request import APIRequest # Not strictly needed here if not mocking request addition directly in web tests

@pytest.fixture
def app_instance(mocker):
    """Creates a Flask app instance for testing."""
    tasks_list = []  # Fresh list for each test run
    agent_logs = []  # Fresh list for each test run
    # Pass the actual Task class to the factory
    flask_app = create_app(tasks_list_ref=tasks_list, task_class_ref=Task, agent_logs_ref=agent_logs)
    flask_app.config.update({"TESTING": True})
    # The tasks_list is now stored in app.config by the modified create_app
    return flask_app

@pytest.fixture
def client(app_instance):
    """Provides a test client for the Flask app."""
    return app_instance.test_client()

@pytest.fixture
def tasks_list_from_app(app_instance):
    """Retrieves the tasks_list associated with the app instance for manipulation/assertion."""
    return app_instance.config['tasks_list_ref']

# Tests for /status endpoint
def test_status_empty(client):
    """Tests the /status endpoint with no tasks."""
    response = client.get('/status')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['agent_overall_status'] == 'idle'
    assert data['total_tasks'] == 0
    assert data['pending_tasks'] == 0
    assert data['processing_tasks'] == 0
    assert data['completed_tasks'] == 0
    assert data['failed_tasks'] == 0

def test_status_with_tasks(client, tasks_list_from_app, mocker):
    """Tests the /status endpoint with a variety of task statuses."""
    task1 = Task("Pending Task")
    task1.status = "pending"

    task2 = Task("Processing Task")
    task2.status = "processing"

    task3 = Task("Completed Task")
    task3.status = "completed"

    task4 = Task("Failed Task")
    task4.status = "failed"

    tasks_list_from_app.extend([task1, task2, task3, task4])

    response = client.get('/status')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['agent_overall_status'] == 'processing' # Since one task is processing
    assert data['total_tasks'] == 4
    assert data['pending_tasks'] == 1
    assert data['processing_tasks'] == 1
    assert data['completed_tasks'] == 1
    assert data['failed_tasks'] == 1

# Tests for /tasks GET endpoint
def test_get_tasks_empty(client):
    """Tests GET /tasks when there are no tasks."""
    response = client.get('/tasks')
    assert response.status_code == 200
    assert json.loads(response.data) == []

def test_get_tasks_with_data(client, tasks_list_from_app, mocker): # Added mocker
    """Tests GET /tasks with some tasks present."""
    task1 = Task("First task")
    # Manually setting ID for predictable testing, though Task auto-generates them.
    # This is fine for unit testing the web service's serialization.
    task1.id = "task1_id_override"
    task1.status = "pending"

    task2 = Task("Second task")
    task2.id = "task2_id_override"
    task2.status = "completed"
    task2.result = "All done"

    # Example of adding a mock request to test 'num_requests' in to_dict,
    # though not strictly necessary for testing the web service itself unless this influences output.
    # from june_agent.request import APIRequest # Would need this import
    # mock_api_req = mocker.Mock(spec=APIRequest)
    # task2.add_request(mock_api_req) # Assuming add_request works as tested elsewhere

    tasks_list_from_app.extend([task1, task2])

    response = client.get('/tasks')
    assert response.status_code == 200
    returned_data = json.loads(response.data)

    assert len(returned_data) == 2

    # Check data for task1
    assert returned_data[0]['id'] == "task1_id_override"
    assert returned_data[0]['description'] == "First task"
    assert returned_data[0]['status'] == "pending"
    assert returned_data[0]['num_requests'] == 0 # As no requests were added to task1

    # Check data for task2
    assert returned_data[1]['id'] == "task2_id_override"
    assert returned_data[1]['description'] == "Second task"
    assert returned_data[1]['status'] == "completed"
    assert returned_data[1]['result'] == "All done"
    # assert returned_data[1]['num_requests'] == 1 # If we added a mock request to task2

# Tests for /tasks POST endpoint
def test_post_task_valid(client, tasks_list_from_app):
    """Tests successfully POSTing a new task."""
    response = client.post('/tasks', json={'description': 'New awesome task'})
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['description'] == 'New awesome task'
    assert data['status'] == 'pending' # Default status for new tasks

    assert len(tasks_list_from_app) == 1
    assert tasks_list_from_app[0].description == 'New awesome task'
    assert tasks_list_from_app[0].id == data['id'] # Check if the ID in list matches returned ID

def test_post_task_invalid_missing_description_key(client, tasks_list_from_app):
    """Tests POST /tasks with the 'description' key missing."""
    response = client.post('/tasks', json={'title': 'This is not a description'}) # Missing 'description'
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == "Missing 'description' key in request JSON."
    assert len(tasks_list_from_app) == 0

def test_post_task_invalid_empty_description_value(client, tasks_list_from_app):
    """Tests POST /tasks with an empty string for 'description'."""
    response = client.post('/tasks', json={'description': '   '}) # Empty/whitespace description
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'Task description must be a non-empty string.'
    assert len(tasks_list_from_app) == 0

def test_post_task_invalid_non_string_description(client, tasks_list_from_app):
    """Tests POST /tasks with a non-string value for 'description'."""
    response = client.post('/tasks', json={'description': 123}) # Non-string description
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'Task description must be a non-empty string.'
    assert len(tasks_list_from_app) == 0
