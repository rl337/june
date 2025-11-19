"""
Integration test service command implementation.
"""
import argparse
import logging
import os

from essence.command import Command

logger = logging.getLogger(__name__)


class IntegrationTestServiceCommand(Command):
    """
    Command for running the integration test service.

    Provides a REST API for managing and monitoring integration test runs.
    Allows starting tests in the background, checking status, retrieving results,
    viewing logs, and managing test execution without blocking the main process.

    The service runs pytest-based integration tests asynchronously and provides
    comprehensive test management capabilities via HTTP endpoints.
    """

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "integration-test-service"
        """
        return "integration-test-service"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Run the integration test service (REST API for managing test runs)"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Configures HTTP server port and host binding for the REST API.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("INTEGRATION_TEST_SERVICE_PORT", "8082")),
            help="HTTP port for REST API (default: 8082)",
        )
        parser.add_argument(
            "--host",
            type=str,
            default=os.getenv("INTEGRATION_TEST_SERVICE_HOST", "0.0.0.0"),
            help="Host to bind to (default: 0.0.0.0)",
        )

    def init(self) -> None:
        """
        Initialize integration test service.

        Sets up signal handlers for graceful shutdown and initializes the
        IntegrationTestService with the configured port. The service will
        be started when run() is called.
        """
        # Setup signal handlers
        self.setup_signal_handlers()

        # Import the service class
        from essence.services.integration_test.main import IntegrationTestService

        self.service = IntegrationTestService(port=self.args.port)
        logger.info("Integration test service initialized")

    def run(self) -> None:
        """
        Run the integration test service.

        Starts the HTTP REST API server for managing integration test runs.
        This method blocks until the service is stopped (via signal handler).
        The service provides endpoints for starting tests, checking status,
        retrieving results, and viewing logs.
        """
        # Run the service (this will block)
        self.service.run(host=self.args.host)

    def cleanup(self) -> None:
        """
        Clean up integration test service resources.

        Releases any resources held by the integration test service, including
        HTTP server connections and background test processes. Actual cleanup
        is handled by the service's shutdown logic when signals are received.
        """
        logger.info("Integration test service cleanup complete")
