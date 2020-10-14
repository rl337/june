import pytest
from june_agent.task import Task
from june_agent.request import APIRequest # For spec in mocker and isinstance checks

def test_task_initialization():
    """Tests the initialization of a Task object."""
    description = "Test task description"
    task = Task(description=description)

    assert task.description == description
    assert task.id is not None
    assert isinstance(task.id, str)
    assert task.status == "pending"
    assert task.result is None
    assert task.error_message is None
    assert task.requests == []

    # Test basic to_dict functionality
    task_dict = task.to_dict()
    assert task_dict['description'] == description
    assert task_dict['id'] == task.id
    assert task_dict['status'] == "pending"
    assert task_dict['num_requests'] == 0

def test_task_add_request_valid(mocker):
    """Tests adding a valid APIRequest object to a task."""
    task = Task("Test add_request")
    # Create a mock object that respects the APIRequest interface
    mock_api_request = mocker.Mock(spec=APIRequest)

    task.add_request(mock_api_request)

    assert len(task.requests) == 1
    assert task.requests[0] == mock_api_request

def test_task_add_request_invalid_type_logs_error_and_does_not_add(mocker):
    """
    Tests that adding an invalid object type to `add_request` logs an error
    (as per current implementation) and does not add the object to requests.
    """
    task = Task("Test invalid add_request")

    # Patch the logger in june_agent.task module
    mock_logger_warning = mocker.patch('june_agent.task.logging.warning')

    invalid_request_object = "this is a string, not an APIRequest"
    task.add_request(invalid_request_object)

    assert len(task.requests) == 0 # The invalid object should not be added
    # Check that logging.warning was called.
    # We can check for a specific message part if needed, but assert_called_once() is a good start.
    mock_logger_warning.assert_called_once()
    # Example of checking part of the log message:
    # mock_logger_warning.assert_called_once_with(mocker.ANY) # Basic check
    # More specific:
    args, _ = mock_logger_warning.call_args
    assert f"Attempted to add an invalid request object to task {task.id}" in args[0]


def test_task_process_success(mocker):
    """Tests successful processing of a task."""
    task_description = "Test successful process"
    task = Task(task_description)

    mock_api_request = mocker.Mock(spec=APIRequest)
    # Configure the mock's execute method to return a successful result
    mock_api_request.execute.return_value = "Successful API result"

    task.add_request(mock_api_request)
    task.process()

    assert task.status == "completed"
    assert task.result == "Successful API result"
    assert task.error_message is None
    # Verify that the APIRequest's execute method was called with the task's description
    mock_api_request.execute.assert_called_once_with(task_description)

def test_task_process_api_error_string_returned(mocker):
    """Tests task processing when the APIRequest's execute method returns an error string."""
    task_description = "Test API error string"
    task = Task(task_description)

    mock_api_request = mocker.Mock(spec=APIRequest)
    # Simulate the APIRequest object returning an error string (as per its own error handling)
    error_string_from_api = "Error: API communication failed"
    mock_api_request.execute.return_value = error_string_from_api

    task.add_request(mock_api_request)
    task.process()

    assert task.status == "failed"
    assert task.result == error_string_from_api # Result should store the error string from APIRequest
    assert task.error_message == error_string_from_api # error_message should also store it
    mock_api_request.execute.assert_called_once_with(task_description)

def test_task_process_execute_method_raises_exception(mocker):
    """Tests task processing when the APIRequest's execute method itself raises an exception."""
    task_description = "Test execute exception"
    task = Task(task_description)

    mock_api_request = mocker.Mock(spec=APIRequest)
    # Configure the mock's execute method to raise an exception
    exception_message = "Underlying execute crashed"
    mock_api_request.execute.side_effect = Exception(exception_message)

    task.add_request(mock_api_request)
    task.process()

    assert task.status == "failed"
    assert task.result is None # Result should be None if process itself fails internally
    assert exception_message in task.error_message # The exception message should be in error_message
    mock_api_request.execute.assert_called_once_with(task_description)

def test_task_process_no_requests():
    """Tests processing a task that has no APIRequest objects added."""
    task = Task("Test no requests")

    # Patch the logger to check for the warning
    mock_logger_warning = mocker.patch('june_agent.task.logging.warning')

    task.process()

    assert task.status == "failed"
    # Updated to match the actual error message format from task.py
    expected_error_message = f"Task {task.id} has no requests to process. Setting status to 'failed'."
    # Check if the actual error message logged matches what we expect, or part of it
    args, _ = mock_logger_warning.call_args
    assert args[0] == expected_error_message
    assert task.error_message == "No requests to process for this task." # This is set on the task object

def test_task_process_not_pending_status(mocker):
    """Tests attempting to process a task that is not in 'pending' status."""
    task = Task("Test not pending")
    task.status = "completed" # Set to a non-pending state

    mock_api_request = mocker.Mock(spec=APIRequest)
    task.add_request(mock_api_request)

    # Patch the logger to check for the warning
    mock_logger_warning = mocker.patch('june_agent.task.logging.warning')

    task.process()

    assert task.status == "completed" # Status should not change
    mock_api_request.execute.assert_not_called() # Execute should not have been called
    # Check that the warning about incorrect status was logged
    args, _ = mock_logger_warning.call_args
    assert f"Task {task.id} cannot be processed because its status is '{task.status}'" in args[0]

def test_task_to_dict_method(mocker):
    """Tests the to_dict method for a more complex task."""
    task = Task("Complex task")
    task.status = "completed"
    task.result = "Some result"

    mock_req1 = mocker.Mock(spec=APIRequest)
    mock_req2 = mocker.Mock(spec=APIRequest)
    task.add_request(mock_req1)
    task.add_request(mock_req2)

    task_dict = task.to_dict()

    assert task_dict['id'] == task.id
    assert task_dict['description'] == "Complex task"
    assert task_dict['status'] == "completed"
    assert task_dict['result'] == "Some result"
    assert task_dict['error_message'] is None
    assert task_dict['num_requests'] == 2
