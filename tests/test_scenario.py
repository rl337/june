import pytest
from june_agent.task import Task
from june_agent.request import TogetherAIRequest
from june_agent.message import Message
import subprocess

def test_hello_world_scenario(mocker):
    """
    Tests a scenario where the user asks the agent to create and run a "hello world" program.
    """
    # Mock the subprocess.run method
    mock_subprocess_run = mocker.patch('subprocess.run')
    mock_subprocess_run.return_value.stdout = "hello world\n"

    # Mock the TogetherAIRequest.execute method
    mock_tool_call = mocker.Mock()
    mock_tool_call.type = "function"
    mock_tool_call.function.name = "run_python"
    mock_tool_call.function.arguments = '{"code": "print(\\"hello world\\")"}'
    mock_execute = mocker.patch('june_agent.request.TogetherAIRequest.execute')
    mock_execute.return_value = [mock_tool_call]

    # Create a task
    task = Task("create and run a program that prints “hello world”")
    request = TogetherAIRequest(tools=[
        {
            "type": "function",
            "function": {
                "name": "run_python",
                "description": "Runs a Python script and returns the output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The Python code to run."
                        }
                    },
                    "required": ["code"]
                }
            }
        }
    ])
    task.add_request(request)

    # Process the task
    task.process()

    # Assert that the task is completed and the result is "hello world"
    assert task.status == "completed"
    assert task.result == "hello world\n"

    # Assert that the execute method was called with the correct messages
    messages = [Message(role="user", content="create and run a program that prints “hello world”")]
    mock_execute.assert_called_once_with(messages)

    # Assert that the subprocess.run method was called with the correct arguments
    mock_subprocess_run.assert_called_once_with(['python', '-c', 'print("hello world")'], capture_output=True, text=True)
