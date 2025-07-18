import pytest
from june_agent.task import Task
from june_agent.request import TogetherAIRequest
from june_agent.message import Message
from june_agent import tools
import io

def test_hello_world_scenario(mocker):
    """
    Tests a scenario where the user asks the agent to create and run a "hello world" program.
    """
    # Mock the open function to avoid writing to a file
    mocker.patch('builtins.open', mocker.mock_open())

    # Mock the TogetherAIRequest.execute method to return a call to save_file
    mock_save_file_call = mocker.Mock()
    mock_save_file_call.type = "function"
    mock_save_file_call.function.name = "save_file"
    mock_save_file_call.function.arguments = '{"filename": "hello_world.py", "content": "print(\\"hello world\\")"}'
    mock_save_file_call.id = "call_1"

    # Mock the TogetherAIRequest.execute method to return a call to run_python
    mock_run_python_call = mocker.Mock()
    mock_run_python_call.type = "function"
    mock_run_python_call.function.name = "run_python"
    mock_run_python_call.function.arguments = '{"code": "with open(\\"hello_world.py\\", \\"r\\") as f: exec(f.read())"}'
    mock_run_python_call.id = "call_2"

    mock_execute = mocker.patch('june_agent.request.TogetherAIRequest.execute')
    mock_execute.side_effect = [[mock_save_file_call], [mock_run_python_call], "hello world\n"]

    # Create a task
    task = Task("create and run a program that prints “hello world”")
    request = TogetherAIRequest(tools=[
        {
            "type": "function",
            "function": {
                "name": "save_file",
                "description": "Saves content to a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The name of the file to save."
                        },
                        "content": {
                            "type": "string",
                            "description": "The content to save to the file."
                        }
                    },
                    "required": ["filename", "content"]
                }
            }
        },
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
