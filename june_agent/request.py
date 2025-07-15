import abc
import os
import together
import logging
from .message import Message

# Configure logging for this module if not configured globally elsewhere in a way that applies
# For simplicity, using basicConfig here. If a more complex logging setup is in __main__.py,
# this might lead to multiple basicConfig calls if this module is imported after initial logging setup.
# A better approach for libraries is to get a logger instance: logger = logging.getLogger(__name__)
# and let the application configure handlers. However, for this project structure, this is acceptable.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

class APIRequest(abc.ABC):
    """
    Abstract Base Class for making API requests.
    Defines a common interface for different API request types.
    """
    @abc.abstractmethod
    def execute(self, messages: list[Message]) -> str:
        """
        Executes the API request with the given messages.

        Args:
            messages (list[Message]): A list of Message objects.

        Returns:
            str: The response text from the API or an error message string.
        """
        pass

class TogetherAIRequest(APIRequest):
    """
    Concrete implementation of APIRequest for interacting with the Together AI API.
    """
    def __init__(self, model: str = 'togethercomputer/RedPajama-INCITE-7B-Instruct', max_tokens: int = 256, tools: list = []):
        """
        Initializes the TogetherAIRequest.

        Args:
            model (str): The model to use for the API call.
            max_tokens (int): The maximum number of tokens for the response.
            tools (list): A list of tools to make available to the model.
        """
        self.model = model
        self.max_tokens = max_tokens
        self.tools = tools
        # The API key is typically handled by the `together` library via the TOGETHER_API_KEY env var.
        # No explicit API key handling needed here unless overriding default behavior.

    def execute(self, messages: list[Message]) -> str:
        """
        Executes a request to the Together AI API using the configured model and messages.

        Args:
            messages (list[Message]): A list of Message objects.

        Returns:
            str: The AI's response text, or an error message if the request failed.
        """
        logging.info(f"Executing Together AI request with model {self.model} for messages: '{messages}'")
        try:
            # Initialize the Together client.
            # This will use the TOGETHER_API_KEY environment variable.
            client = together.Together()

            # Make the API call
            response = client.chat.completions.create(
                model=self.model,
                messages=[message.as_dict() for message in messages],
                tools=self.tools,
                tool_choice="auto",
            )

            if response and response.choices:
                choice = response.choices[0]
                if choice.message.tool_calls:
                    return choice.message.tool_calls
                else:
                    return choice.message.content.strip()
            else:
                logging.error(f"No valid response or choices found in Together AI output for messages: '{messages}'. Response: {response}")
                return "Error: No response or choices found from API."
        except Exception as e:
            logging.error(f"An unexpected error occurred while calling Together AI for messages: '{messages}': {e}", exc_info=True)
            return f"Error: Could not connect to or process response from Together AI. Details: {e}"
