"""
Command pattern for June services.

All services are implemented as commands that follow a consistent lifecycle:
- init(): Initialize the service (setup, configuration, etc.)
- run(): Run the service (main event loop)
- cleanup(): Clean up resources (graceful shutdown)
"""
import argparse
import logging
import signal
import sys
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class Command(ABC):
    """
    Base class for all June service commands.
    
    Each service implements a command that follows this lifecycle:
    1. init() - Initialize resources, configuration, etc.
    2. run() - Main service loop (blocking)
    3. cleanup() - Clean up resources on shutdown
    """
    
    def __init__(self, args: argparse.Namespace):
        """
        Initialize command with parsed arguments.
        
        Args:
            args: Parsed command-line arguments
        """
        self.args = args
        self._shutdown_event = None
        self._initialized = False
    
    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """
        Get the command name (used as subcommand).
        
        Returns:
            Command name string (e.g., "telegram-service", "tts", "stt")
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_description(cls) -> str:
        """
        Get command description for help text.
        
        Returns:
            Description string
        """
        pass
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-specific arguments to the argument parser.
        
        Override this method to add service-specific arguments.
        
        Args:
            parser: Argument parser to add arguments to
        """
        pass
    
    @abstractmethod
    def init(self) -> None:
        """
        Initialize the service.
        
        This method should:
        - Load configuration
        - Initialize resources (database connections, clients, etc.)
        - Set up signal handlers if needed
        - Perform any one-time setup
        
        Raises:
            Exception: If initialization fails
        """
        pass
    
    @abstractmethod
    def run(self) -> None:
        """
        Run the service main loop.
        
        This method should:
        - Start the main service loop
        - Block until service should stop
        - Handle the primary service functionality
        
        This method should check self._shutdown_event periodically
        and exit gracefully when shutdown is requested.
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """
        Clean up resources on shutdown.
        
        This method should:
        - Close database connections
        - Stop background tasks
        - Clean up any resources
        - Perform graceful shutdown
        
        This is called after run() completes or on error.
        """
        pass
    
    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            if self._shutdown_event:
                self._shutdown_event.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    def execute(self) -> int:
        """
        Execute the command lifecycle.
        
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            # Initialize
            logger.info(f"Initializing {self.get_name()}...")
            self.init()
            self._initialized = True
            logger.info(f"{self.get_name()} initialized successfully")
            
            # Run
            logger.info(f"Starting {self.get_name()}...")
            self.run()
            logger.info(f"{self.get_name()} stopped")
            
            return 0
            
        except KeyboardInterrupt:
            logger.info(f"{self.get_name()} interrupted by user")
            return 130  # Standard exit code for SIGINT
        except Exception as e:
            logger.error(f"Error in {self.get_name()}: {e}", exc_info=True)
            return 1
        finally:
            # Cleanup
            if self._initialized:
                try:
                    logger.info(f"Cleaning up {self.get_name()}...")
                    self.cleanup()
                    logger.info(f"{self.get_name()} cleanup complete")
                except Exception as e:
                    logger.error(f"Error during cleanup: {e}", exc_info=True)

