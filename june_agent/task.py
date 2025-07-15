import uuid
import logging
from .request import APIRequest # Relative import for APIRequest from request.py within the same package
from .message import Message
from . import tools
import json

# Configure logging for this module (similar note as in request.py regarding configuration)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
# logger = logging.getLogger(__name__) # Alternative for library modules

class Task:
    """
    Represents a single task to be processed by the agent.
    A task has a description, status, and can hold one or more APIRequest objects
    that define the actual work to be done.
    """
    def __init__(self, description: str):
        """
        Initializes a new Task.

        Args:
            description (str): The description of the task.
        """
        self.id: str = uuid.uuid4().hex
        self.description: str = description
        self.status: str = "pending"  # Possible statuses: "pending", "processing", "completed", "failed"
        self.result: str | None = None
        self.requests: list[APIRequest] = []
        self.error_message: str | None = None
        logging.info(f"Task created with ID: {self.id}, Description: '{self.description[:50]}...'")

    def add_request(self, request_obj: APIRequest) -> None:
        """
        Adds an APIRequest object to this task.

        Args:
            request_obj (APIRequest): The API request to add.
        """
        if not isinstance(request_obj, APIRequest):
            logging.warning(f"Attempted to add an invalid request object to task {self.id}.")
            # Optionally raise an error here: raise TypeError("request_obj must be an instance of APIRequest")
            return
        self.requests.append(request_obj)
        logging.info(f"Request added to task {self.id}. Total requests: {len(self.requests)}")

    def process(self) -> None:
        """
        Processes the task by executing its associated API requests.
        Currently, it processes only the first request in the list.
        """
        if self.status != "pending":
            logging.warning(f"Task {self.id} cannot be processed because its status is '{self.status}', not 'pending'.")
            return

        if not self.requests:
            logging.warning(f"Task {self.id} has no requests to process. Setting status to 'failed'.")
            self.status = "failed"
            self.error_message = "No requests to process for this task."
            return

        self.status = "processing"
        logging.info(f"Task {self.id} status changed to 'processing'. Starting to process requests.")

        # For now, we assume one primary request per task for simplicity.
        # Future enhancements could involve handling multiple requests, sequences, or DAGs.
        current_request = self.requests[0]

        try:
            logging.info(f"Executing request for task {self.id} with description: '{self.description[:50]}...'")
            # The description of the task is used as the prompt for the request.
            messages = [Message(role="user", content=self.description)]
            api_result = current_request.execute(messages)
            self.result = api_result

            # Check if the result is a tool call
            if isinstance(api_result, list) and len(api_result) > 0 and api_result[0].type == "function":
                tool_call = api_result[0]
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                if hasattr(tools, function_name):
                    function_to_call = getattr(tools, function_name)
                    try:
                        result = function_to_call(**function_args)
                        self.result = result
                        self.status = "completed"
                        logging.info(f"Task {self.id} completed successfully. Result: '{str(self.result)[:100]}...'")
                    except Exception as e:
                        self.status = "failed"
                        self.error_message = f"Error executing tool {function_name}: {e}"
                        logging.error(f"Task {self.id} failed. Error executing tool: {self.error_message}")
                else:
                    self.status = "failed"
                    self.error_message = f"Tool {function_name} not found."
                    logging.error(f"Task {self.id} failed. Tool not found: {function_name}")
            elif isinstance(api_result, str):
                if api_result.lower().startswith("error:"):
                    self.status = "failed"
                    self.error_message = api_result
                    logging.error(f"Task {self.id} failed. Error from API request: {self.error_message}")
                else:
                    self.result = api_result
                    self.status = "completed"
                    logging.info(f"Task {self.id} completed successfully. Result: '{str(self.result)[:100]}...'")
            else:
                self.status = "failed"
                self.error_message = "Invalid response from API."
                logging.error(f"Task {self.id} failed. Invalid response from API.")

        except Exception as e:
            logging.error(f"An unexpected error occurred while processing request for task {self.id}: {e}", exc_info=True)
            self.status = "failed"
            self.error_message = f"Unexpected error during task processing: {e}"
            self.result = None # Ensure result is cleared if an unexpected processing error occurs

        # Note: If multiple requests were to be processed, the logic for setting overall task status
        # based on individual request outcomes would need to be more sophisticated.
        # For now, we break after the first request (implicitly, as we only process self.requests[0]).

    def to_dict(self) -> dict:
        """
        Returns a dictionary representation of the task.
        """
        return {
            'id': self.id,
            'description': self.description,
            'status': self.status,
            'result': self.result,
            'error_message': self.error_message,
            'num_requests': len(self.requests),
            # Optionally, could include descriptions of requests if needed:
            # 'request_descriptions': [req.some_description_method() for req in self.requests if hasattr(req, 'some_description_method')]
        }
