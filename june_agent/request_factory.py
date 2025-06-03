from typing import Callable, Optional, Literal
import logging

from june_agent.request import APIRequest, TogetherAIRequest
from june_agent.testing.mocks import MockRequest # Assuming MockRequest is in testing.mocks

logger = logging.getLogger(__name__)

# Define a type alias for a callable that creates an APIRequest instance.
# This callable takes no arguments and returns an object implementing the APIRequest interface.
RequestCreationCallable = Callable[[], APIRequest]

class RequestFactory:
    """
    Factory for creating APIRequest instances (e.g., actual API clients or mocks).
    This allows decoupling the core logic (like Task assessment) from concrete
    request implementations, facilitating easier testing and potential swapping
    of API providers or request strategies.
    """

    def __init__(self,
                 mode: Literal["production", "test", "custom"] = "production",
                 custom_factory_fn: Optional[RequestCreationCallable] = None,
                 default_mock_response: str = "Default mock response from factory-created mock"):
        """
        Initializes the RequestFactory.

        The factory can operate in one of three modes:
        - "production": Creates real `TogetherAIRequest` instances for live API calls.
        - "test": Creates `MockRequest` instances, useful for unit/integration testing
                  without making actual external API calls.
        - "custom": Uses a user-provided callable (`custom_factory_fn`) to create
                    `APIRequest` instances, allowing for flexible or specialized instantiation.

        Args:
            mode: The operational mode of the factory. Defaults to "production".
            custom_factory_fn: A callable that returns an `APIRequest` instance.
                               Required if `mode` is "custom".
            default_mock_response: The default response string for `MockRequest` instances
                                   created when `mode` is "test".

        Raises:
            ValueError: If `mode` is "custom" and `custom_factory_fn` is not provided or not callable.
        """
        self.mode = mode
        self.custom_factory_fn = custom_factory_fn
        self.default_mock_response = default_mock_response

        if self.mode == "custom" and not callable(self.custom_factory_fn):
            logger.error("RequestFactory: Mode is 'custom' but custom_factory_fn is missing or not callable.")
            raise ValueError("custom_factory_fn must be a callable if mode is 'custom'.")

        logger.info(f"RequestFactory initialized. Mode: '{self.mode}'.")

    def create_request(self, prompt_type: Optional[str] = None) -> APIRequest:
        """
        Creates and returns an APIRequest instance based on the factory's current mode.

        The `prompt_type` argument is currently a placeholder for future enhancements,
        where the factory might create different types or configurations of APIRequest
        objects based on the context of the prompt (e.g., "assessment", "execution_code",
        "execution_text_gen").

        Args:
            prompt_type: An optional string indicating the type or purpose of the prompt
                         for which this request is being created. Currently unused.

        Returns:
            An instance that adheres to the APIRequest interface.

        Raises:
            ValueError: Should not occur if __init__ validation is correct, but theoretically
                        if mode is 'custom' and custom_factory_fn is None due to external change.
        """
        logger.debug(f"RequestFactory: Attempting to create request. Mode: '{self.mode}', Prompt Type: '{prompt_type}'.")

        if self.mode == "production":
            # In "production" mode, create a real TogetherAIRequest.
            # Future: Could configure with API keys, specific model names based on prompt_type, etc.
            logger.info("RequestFactory: Creating TogetherAIRequest instance (production mode).")
            return TogetherAIRequest()

        elif self.mode == "test":
            # In "test" mode, create a MockRequest instance.
            # Each call creates a new MockRequest for better test isolation, allowing
            # individual tests to configure their mocks independently.
            logger.info(f"RequestFactory: Creating MockRequest instance (test mode) with default response: '{self.default_mock_response}'.")
            return MockRequest(default_response=self.default_mock_response)

        elif self.mode == "custom":
            # In "custom" mode, use the provided factory function.
            if self.custom_factory_fn: # Validated in __init__, but check again for safety.
                logger.info("RequestFactory: Creating request using custom_factory_fn.")
                return self.custom_factory_fn()
            else:
                # This state should ideally be prevented by the __init__ check.
                logger.error("RequestFactory: Mode is 'custom' but custom_factory_fn is missing. Critical configuration error.")
                # Fallback to a mock to prevent None return, but this indicates a setup problem.
                return MockRequest(default_response="CRITICAL ERROR: Custom factory missing")

        else:
            # Fallback for an unknown or unsupported mode.
            logger.error(f"RequestFactory: Unknown mode '{self.mode}'. Falling back to MockRequest to avoid None return.")
            return MockRequest(default_response=f"Fallback mock: Unknown factory mode '{self.mode}'")

# Example Usage (commented out, suitable for direct testing of this file)
# if __name__ == "__main__":
#     # --- Production Mode Example ---
#     prod_factory = RequestFactory(mode="production")
#     prod_request = prod_factory.create_request(prompt_type="text_generation")
#     logger.info(f"Production request type: {type(prod_request)}")
#     # Example (requires TOGETHER_API_KEY to be set):
#     # try:
#     #     response = prod_request.execute("A short poem about a cat:")
#     #     logger.info(f"Prod response: {response[:100]}...")
#     # except Exception as e:
#     #     logger.error(f"Error executing production request: {e}")

#     # --- Test Mode Example ---
#     test_factory = RequestFactory(mode="test", default_mock_response="Mock API says: Hello there!")
#     test_req_1 = test_factory.create_request()
#     logger.info(f"Test request 1 type: {type(test_req_1)}")
#     logger.info(f"Test request 1 (default prompt): {test_req_1.execute('any prompt')}")

#     test_req_2 = test_factory.create_request() # Gets a new MockRequest instance
#     if isinstance(test_req_2, MockRequest): # Type guard for IDE/mypy
#         test_req_2.set_response_for_prompt("specific_query", "Mock API says: Found your specific query!")
#         logger.info(f"Test request 2 ('specific_query'): {test_req_2.execute('specific_query')}")
#         logger.info(f"Test request 2 ('other_query'): {test_req_2.execute('other_query')}")

#     # --- Custom Mode Example ---
#     def my_special_request_builder() -> APIRequest:
#         logger.info("Building my special custom request object...")
#         mock = MockRequest(default_response="Response from my special custom mock!")
#         mock.set_response_for_prompt("special_case", "Custom mock handles 'special_case'!")
#         return mock

#     custom_factory = RequestFactory(mode="custom", custom_factory_fn=my_special_request_builder)
#     custom_req = custom_factory.create_request()
#     logger.info(f"Custom request type: {type(custom_req)}")
#     logger.info(f"Custom request ('special_case'): {custom_req.execute('special_case')}")
#     logger.info(f"Custom request ('another_case'): {custom_req.execute('another_case')}")

#     # --- Error Mode Example ---
#     error_factory = RequestFactory(mode="unknown_mode") # type: ignore
#     error_req = error_factory.create_request()
#     logger.info(f"Error request type: {type(error_req)}")
#     logger.info(f"Error request response: {error_req.execute('any prompt')}")
#     # Production factory
#     prod_factory = RequestFactory(mode="production")
#     prod_request = prod_factory.create_request()
#     print(f"Prod request type: {type(prod_request)}") # Should be TogetherAIRequest

#     # Test factory
#     test_factory = RequestFactory(mode="test", default_mock_response="Test API says hi!")
#     test_request_1 = test_factory.create_request()
#     print(f"Test request type: {type(test_request_1)}") # Should be MockRequest
#     print(f"Test request 1 response: {test_request_1.execute('any prompt')}")

#     # Test factory creating another mock instance
#     test_request_2 = test_factory.create_request()
#     test_request_2.set_response_for_prompt("hello", "Mock says hello back")
#     print(f"Test request 2 response for 'hello': {test_request_2.execute('hello')}")
#     print(f"Test request 2 response for 'other': {test_request_2.execute('other')}") # Uses default

#     # Custom factory
#     def my_custom_req_builder() -> APIRequest:
#         mock = MockRequest("Custom built mock!")
#         mock.set_response_for_prompt("custom", "This is indeed custom.")
#         return mock

#     custom_factory = RequestFactory(mode="custom", custom_factory_fn=my_custom_req_builder)
#     custom_req = custom_factory.create_request()
#     print(f"Custom request type: {type(custom_req)}")
#     print(f"Custom request response for 'custom': {custom_req.execute('custom')}")
#     print(f"Custom request response for 'other': {custom_req.execute('other')}")
