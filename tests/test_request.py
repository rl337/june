import pytest
from june_agent.request import TogetherAIRequest
from june_agent.message import Message
import together # For together.APIError

def test_together_request_successful(mocker):
    """
    Tests successful execution of TogetherAIRequest, ensuring the API is called
    correctly and the response is processed as expected.
    """
    # Mock the response from client.chat.completions.create
    mock_choice = mocker.Mock()
    mock_choice.message.content = "Paris"
    mock_choice.message.tool_calls = None

    mock_response = mocker.Mock()
    mock_response.choices = [mock_choice]

    # Mock the create method itself
    mock_create_method = mocker.Mock(return_value=mock_response)

    # Mock the Together client instance and its chat.completions attribute
    mock_together_client_instance = mocker.Mock()
    mock_together_client_instance.chat.completions.create = mock_create_method

    # Patch the `together.Together` class to return our mocked client instance
    mocker.patch('june_agent.request.together.Together', return_value=mock_together_client_instance)

    # Instantiate the request handler
    request_handler = TogetherAIRequest(model="test-model", max_tokens=10)
    messages = [Message(role="user", content="What is the capital of France?")]

    # Execute the request
    response = request_handler.execute(messages)

    # Assertions
    assert response == "Paris"

    # Check that client.chat.completions.create was called once with the correct arguments
    mock_create_method.assert_called_once_with(
        model="test-model",
        messages=[message.as_dict() for message in messages],
        tools=[],
        tool_choice="auto"
    )


def test_together_request_generic_exception(mocker):
    """
    Tests that a generic Exception raised during the API call is caught and
    handled, returning an appropriate error message string.
    """
    # Mock `client.chat.completions.create` to raise a generic Exception
    mock_create_method = mocker.Mock(side_effect=Exception("Generic Test Error"))

    mock_together_client_instance = mocker.Mock()
    mock_together_client_instance.chat.completions.create = mock_create_method

    mocker.patch('june_agent.request.together.Together', return_value=mock_together_client_instance)

    request_handler = TogetherAIRequest(model="test-model-generic-exc", max_tokens=15)
    messages = [Message(role="user", content="This prompt will cause a generic exception")]

    response = request_handler.execute(messages)

    # Assert that the response string contains the error message
    # The exact formatting comes from request.py's exception handling
    assert "Error: Could not connect to or process response from Together AI. Details: Generic Test Error" in response
    mock_create_method.assert_called_once_with(
        model="test-model-generic-exc",
        messages=[message.as_dict() for message in messages],
        tools=[],
        tool_choice="auto"
    )

def test_together_request_no_choices_in_response(mocker):
    """
    Tests the scenario where the API response object or its 'choices' attribute is None or empty.
    """
    # Mock a response that doesn't conform to expectations (e.g., no choices)
    mock_empty_response = mocker.Mock()
    mock_empty_response.choices = [] # Empty choices list

    mock_create_method = mocker.Mock(return_value=mock_empty_response)

    mock_together_client_instance = mocker.Mock()
    mock_together_client_instance.chat.completions.create = mock_create_method

    mocker.patch('june_agent.request.together.Together', return_value=mock_together_client_instance)

    request_handler = TogetherAIRequest()
    messages = [Message(role="user", content="A prompt that leads to an empty response")]
    response = request_handler.execute(messages)

    assert "Error: No response or choices found from API." in response
    mock_create_method.assert_called_once()

# Implicit test for API Key handling:
# The tests above already cover this. If `together.Together()` was called without mocks,
# and if the API key was missing, it would raise an error from the `together` library itself
# before any of our mocked methods are even reached (unless the constructor itself fails,
# which is a library concern). By successfully mocking `together.Together` and its instance
# methods, we are effectively bypassing any actual API key checks for these unit tests.
# Instantiating `TogetherAIRequest` itself does not require the API key; only its `execute` method
# (which initializes the client) would trigger such a check if not mocked.
# A dedicated test for instantiation could be:
def test_together_request_instantiation():
    """Tests that TogetherAIRequest can be instantiated."""
    try:
        handler = TogetherAIRequest(model="init-test-model", max_tokens=1)
        assert handler.model == "init-test-model"
        assert handler.max_tokens == 1
    except Exception as e:
        pytest.fail(f"TogetherAIRequest instantiation failed: {e}")
