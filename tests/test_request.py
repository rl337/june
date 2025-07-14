import pytest
from june_agent.request import TogetherAIRequest
import together # For together.APIError

def test_together_request_successful(mocker):
    """
    Tests successful execution of TogetherAIRequest, ensuring the API is called
    correctly and the response is processed as expected.
    """
    # Mock the response from client.completions.create
    mock_completion_choice = mocker.Mock()
    mock_completion_choice.text = "Paris"

    mock_completion_response = mocker.Mock()
    mock_completion_response.choices = [mock_completion_choice]

    # Mock the create method itself
    mock_completions_create_method = mocker.Mock(return_value=mock_completion_response)

    # Mock the Together client instance and its completions attribute
    mock_together_client_instance = mocker.Mock()
    # To mock `client.completions.create`, we need `completions` to be a mock
    # that has a `create` method.
    mock_together_client_instance.completions = mocker.Mock()
    mock_together_client_instance.completions.create = mock_completions_create_method

    # Patch the `together.Together` class to return our mocked client instance
    mocker.patch('june_agent.request.together.Together', return_value=mock_together_client_instance)

    # Instantiate the request handler
    request_handler = TogetherAIRequest(model="test-model", max_tokens=10)
    prompt = "What is the capital of France?"

    # Execute the request
    response = request_handler.execute(prompt)

    # Assertions
    assert response == "Paris"

    # Check that the `together.Together` client was initialized (implicitly by being patched)
    # Check that client.completions.create was called once with the correct arguments
    mock_completions_create_method.assert_called_once_with(
        model="test-model",
        prompt=prompt,
        max_tokens=10
    )


def test_together_request_generic_exception(mocker):
    """
    Tests that a generic Exception raised during the API call is caught and
    handled, returning an appropriate error message string.
    """
    # Mock `client.completions.create` to raise a generic Exception
    mock_completions_create_method = mocker.Mock(side_effect=Exception("Generic Test Error"))

    mock_together_client_instance = mocker.Mock()
    mock_together_client_instance.completions = mocker.Mock()
    mock_together_client_instance.completions.create = mock_completions_create_method

    mocker.patch('june_agent.request.together.Together', return_value=mock_together_client_instance)

    request_handler = TogetherAIRequest(model="test-model-generic-exc", max_tokens=15)
    prompt = "This prompt will cause a generic exception"

    response = request_handler.execute(prompt)

    # Assert that the response string contains the error message
    # The exact formatting comes from request.py's exception handling
    assert "Error: Could not connect to or process response from Together AI. Details: Generic Test Error" in response
    mock_completions_create_method.assert_called_once_with(
        model="test-model-generic-exc",
        prompt=prompt,
        max_tokens=15
    )

def test_together_request_no_choices_in_response(mocker):
    """
    Tests the scenario where the API response object or its 'choices' attribute is None or empty.
    """
    # Mock a response that doesn't conform to expectations (e.g., no choices)
    mock_empty_completion_response = mocker.Mock()
    mock_empty_completion_response.choices = [] # Empty choices list

    mock_completions_create_method = mocker.Mock(return_value=mock_empty_completion_response)

    mock_together_client_instance = mocker.Mock()
    mock_together_client_instance.completions = mocker.Mock()
    mock_together_client_instance.completions.create = mock_completions_create_method

    mocker.patch('june_agent.request.together.Together', return_value=mock_together_client_instance)

    request_handler = TogetherAIRequest()
    prompt = "A prompt that leads to an empty response"
    response = request_handler.execute(prompt)

    assert "Error: No response or choices found from API." in response
    mock_completions_create_method.assert_called_once()

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
