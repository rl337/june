"""
Integration test service command implementation.
"""
import argparse
import logging
import os

from essence.command import Command

logger = logging.getLogger(__name__)


class IntegrationTestServiceCommand(Command):
    """Command for running the integration test service."""
    
    @classmethod
    def get_name(cls) -> str:
        return "integration-test-service"
    
    @classmethod
    def get_description(cls) -> str:
        return "Run the integration test service (REST API for managing test runs)"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("INTEGRATION_TEST_SERVICE_PORT", "8082")),
            help="HTTP port for REST API (default: 8082)"
        )
        parser.add_argument(
            "--host",
            type=str,
            default=os.getenv("INTEGRATION_TEST_SERVICE_HOST", "0.0.0.0"),
            help="Host to bind to (default: 0.0.0.0)"
        )
    
    def init(self) -> None:
        """Initialize integration test service."""
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Import the service class
        from essence.services.integration_test.main import IntegrationTestService
        
        self.service = IntegrationTestService(port=self.args.port)
        logger.info("Integration test service initialized")
    
    def run(self) -> None:
        """Run the integration test service."""
        # Run the service (this will block)
        self.service.run(host=self.args.host)
    
    def cleanup(self) -> None:
        """Clean up integration test service resources."""
        logger.info("Integration test service cleanup complete")
