import pytest
from june_agent.task import Task
from june_agent.request import TogetherAIRequest
from june_agent.message import Message
from june_agent import tools
import io
from unittest.mock import Mock, MagicMock

# Define the scenarios
scenarios = [
    {
        "name": "hello_world",
        "description": "create and run a program that prints “hello world”",
        "side_effects": [
            [Mock(type="function", function=Mock(name="save_file", arguments='{"filename": "hello_world.py", "content": "print(\\"hello world\\")"}'), id="call_1")],
            [Mock(type="function", function=Mock(name="run_python", arguments='{"code": "with open(\\"hello_world.py\\", \\"r\\") as f: exec(f.read())"}'), id="call_2")],
            "hello world\n"
        ],
        "expected_status": "completed",
        "expected_result": "hello world\n"
    },
    {
        "name": "subtasks",
        "description": "Find the files in the current directory and read the contents of the first file.",
        "side_effects": [
            [Mock(type="function", function=Mock(name="list_files", arguments='{}'), id="call_1")],
            [Mock(type="function", function=Mock(name="read_file", arguments='{"filename": "file1.txt"}'), id="call_2")],
            "hello world"
        ],
        "expected_status": "completed",
        "expected_result": "hello world"
    },
    {
        "name": "not_possible",
        "description": "Order a pizza for me.",
        "side_effects": [
            "I'm sorry, I can't do that. I'm not connected to the internet.",
            "I'm sorry, I can't do that. I'm not connected to the internet.",
            "I'm sorry, I can't do that. I'm not connected to the internet."
        ],
        "expected_status": "completed",
        "expected_result": "I'm sorry, I can't do that. I'm not connected to the internet."
    }
]

for scenario in scenarios:
    for side_effect in scenario["side_effects"]:
        if isinstance(side_effect, list):
            for call in side_effect:
                if isinstance(call.function, Mock):
                    call.function.name = call.function._mock_name

@pytest.mark.parametrize("scenario", scenarios, ids=[s["name"] for s in scenarios])
def test_scenario(mocker, scenario):
    """
    Tests a scenario from the scenarios list.
    """
    # Mock the open function to avoid writing to a file
    mocker.patch('builtins.open', mocker.mock_open(read_data="print('hello world')"))

    # Mock the TogetherAIRequest.execute method to return the side effects for the scenario
    mock_execute = mocker.patch('june_agent.request.TogetherAIRequest.execute')
    mock_execute.side_effect = scenario["side_effects"]

    # Create a task
    task = Task(scenario["description"])
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
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "Lists the files in the current directory.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Reads the contents of a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The name of the file to read."
                        }
                    },
                    "required": ["filename"]
                }
            }
        }
    ])
    task.add_request(request)

    # Process the task
    task.process()

    # Assert that the task is completed and the result is as expected
    assert task.status == scenario["expected_status"], f"Scenario '{scenario['name']}' failed: status was '{task.status}' but expected '{scenario['expected_status']}'"
    assert task.result == scenario["expected_result"], f"Scenario '{scenario['name']}' failed: result was '{task.result}' but expected '{scenario['expected_result']}'"
