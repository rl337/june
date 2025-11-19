"""
Coding Agent command - Interactive interface for coding tasks with Qwen3 model.

Usage:
    poetry run -m essence coding-agent [--task TASK] [--interactive] [--workspace-dir DIR]

This command provides an interface for sending coding tasks to the Qwen3 model.
All operations run in containers - no host system pollution.
"""
import argparse
import logging
import os
import sys
from pathlib import Path
import grpc

from essence.command import Command

logger = logging.getLogger(__name__)

# Import coding agent (may not be available in all environments)
try:
    from essence.agents.coding_agent import CodingAgent

    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    DEPENDENCIES_AVAILABLE = False
    IMPORT_ERROR = str(e)
    CodingAgent = None


class CodingAgentCommand(Command):
    """
    Command for interacting with the coding agent.

    Provides both single-task execution and interactive modes for sending
    coding tasks to the Qwen3 model via the inference API.
    """

    def __init__(self, args: argparse.Namespace):
        """
        Initialize command with parsed arguments.

        Args:
            args: Parsed command-line arguments
        """
        super().__init__(args)
        self._agent = None

    @classmethod
    def get_name(cls) -> str:
        """
        Get the command name.

        Returns:
            Command name: "coding-agent"
        """
        return "coding-agent"

    @classmethod
    def get_description(cls) -> str:
        """
        Get the command description.

        Returns:
            Description of what this command does
        """
        return "Interactive interface for coding tasks with Qwen3 model"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command-line arguments to the argument parser.

        Args:
            parser: Argument parser to add arguments to
        """
        parser.add_argument(
            "--task",
            type=str,
            default=None,
            help="Coding task to execute (if not provided, runs in interactive mode)",
        )
        parser.add_argument(
            "--interactive",
            action="store_true",
            default=False,
            help="Run in interactive mode (default: False, requires --task)",
        )
        parser.add_argument(
            "--workspace-dir",
            type=Path,
            default=Path(
                os.getenv("CODING_AGENT_WORKSPACE", "/tmp/coding_agent_workspace")
            ),
            help="Workspace directory for agent operations (default: /tmp/coding_agent_workspace)",
        )
        parser.add_argument(
            "--inference-api-url",
            default=os.getenv("INFERENCE_API_URL", "tensorrt-llm:8000"),
            help="gRPC endpoint for LLM inference service (default: tensorrt-llm:8000 for TensorRT-LLM, can use localhost:50051 for local testing)",
        )
        parser.add_argument(
            "--model-name",
            default=os.getenv("MODEL_NAME", "Qwen/Qwen3-30B-A3B-Thinking-2507"),
            help="Model name to use (default: Qwen/Qwen3-30B-A3B-Thinking-2507)",
        )
        parser.add_argument(
            "--max-context-length",
            type=int,
            default=int(os.getenv("MAX_CONTEXT_LENGTH", "131072")),
            help="Maximum context length (default: 131072)",
        )
        parser.add_argument(
            "--temperature",
            type=float,
            default=float(os.getenv("TEMPERATURE", "0.7")),
            help="Sampling temperature (default: 0.7)",
        )
        parser.add_argument(
            "--max-tokens",
            type=int,
            default=int(os.getenv("MAX_TOKENS", "2048")),
            help="Maximum tokens to generate (default: 2048)",
        )

    def init(self) -> None:
        """
        Initialize coding agent.

        Sets up the coding agent with the configured parameters and creates
        the workspace directory if it doesn't exist.

        Raises:
            RuntimeError: If required dependencies are not available
        """
        if not DEPENDENCIES_AVAILABLE:
            raise RuntimeError(
                f"Required dependencies not available: {IMPORT_ERROR}\n"
                "Make sure essence.agents.coding_agent is available."
            )

        # Create workspace directory
        self.args.workspace_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace directory: {self.args.workspace_dir}")

        # Initialize coding agent
        self._agent = CodingAgent(
            inference_api_url=self.args.inference_api_url,
            model_name=self.args.model_name,
            max_context_length=self.args.max_context_length,
            temperature=self.args.temperature,
            max_tokens=self.args.max_tokens,
        )

        # Set workspace directory
        self._agent.set_workspace(str(self.args.workspace_dir))

        logger.info("Coding agent initialized")
        logger.info(f"  Inference API: {self.args.inference_api_url}")
        logger.info(f"  Model: {self.args.model_name}")
        logger.info(f"  Workspace: {self.args.workspace_dir}")

    def run(self) -> None:
        """
        Run the coding agent.

        Executes either a single task (if --task is provided) or starts
        interactive mode (if --interactive is provided).

        Exits:
            sys.exit(1): If neither --task nor --interactive is provided
        """
        if self.args.task:
            # Execute single task
            self._execute_task(self.args.task)
        elif self.args.interactive:
            # Interactive mode
            self._run_interactive()
        else:
            # Default: show help if no task provided
            logger.error("Either --task or --interactive must be provided")
            logger.info("Use --help for usage information")
            sys.exit(1)

    def _execute_task(self, task: str) -> None:
        """
        Execute a single coding task.

        Args:
            task: The coding task description to execute
        """
        logger.info(f"Executing task: {task}")
        print(f"\n📝 Task: {task}\n")
        print("🤖 Agent response:\n")

        try:
            # Send task and stream response
            response_text = ""
            for chunk in self._agent.send_coding_task(task, reset_conversation=True):
                print(chunk, end="", flush=True)
                response_text += chunk

            print("\n\n✅ Task completed")

        except grpc.RpcError as e:
            logger.error(f"gRPC error executing task: {e}", exc_info=True)
            print(f"\n❌ gRPC Error: {e.code()} - {e.details()}")
            print(
                "💡 Tip: Check that the LLM inference service (TensorRT-LLM) is running and accessible"
            )
            sys.exit(1)
        except ConnectionError as e:
            logger.error(f"Connection error executing task: {e}", exc_info=True)
            print(f"\n❌ Connection Error: {e}")
            print(
                f"💡 Tip: Verify that the LLM inference service is running at {self.args.inference_api_url}"
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error executing task: {e}", exc_info=True)
            print(f"\n❌ Error: {e}")
            print(
                "💡 Tip: Use 'help' to see available commands or check logs for details"
            )
            sys.exit(1)

    def _run_interactive(self) -> None:
        """
        Run in interactive mode.

        Provides an interactive REPL-like interface for executing multiple
        coding tasks in sequence with conversation history maintained.
        Supports special commands: help, reset, quit/exit/q.
        """
        print("\n🤖 Coding Agent - Interactive Mode")
        print("=" * 50)
        print("Enter coding tasks or commands:")
        print("  - Type a coding task to execute it")
        print("  - 'help' or '?' - Show this help message")
        print("  - 'reset' - Reset conversation history")
        print("  - 'quit', 'exit', or 'q' - Exit interactive mode")
        print("=" * 50)

        try:
            while True:
                print("\n> ", end="", flush=True)
                task = input().strip()

                if not task:
                    continue

                task_lower = task.lower()

                if task_lower in ["quit", "exit", "q"]:
                    print("\n👋 Goodbye!")
                    break

                if task_lower in ["help", "?"]:
                    self._show_help()
                    continue

                if task_lower == "reset":
                    self._agent.reset_conversation()
                    print("✅ Conversation reset")
                    continue

                # Execute task
                print("\n🤖 Agent response:\n")
                try:
                    response_text = ""
                    for chunk in self._agent.send_coding_task(task):
                        print(chunk, end="", flush=True)
                        response_text += chunk
                    print("\n")
                except grpc.RpcError as e:
                    logger.error(f"gRPC error executing task: {e}", exc_info=True)
                    print(f"\n❌ gRPC Error: {e.code()} - {e.details()}")
                    print(
                        "💡 Tip: Check that the LLM inference service (TensorRT-LLM) is running and accessible"
                    )
                except ConnectionError as e:
                    logger.error(f"Connection error executing task: {e}", exc_info=True)
                    print(f"\n❌ Connection Error: {e}")
                    print(
                        f"💡 Tip: Verify that the LLM inference service is running at {self.args.inference_api_url}"
                    )
                except Exception as e:
                    logger.error(f"Error executing task: {e}", exc_info=True)
                    print(f"\n❌ Error: {e}")
                    print(
                        "💡 Tip: Use 'help' to see available commands or check logs for details"
                    )

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user")
        except EOFError:
            print("\n\n👋 Goodbye!")

    def _show_help(self) -> None:
        """Show help message for interactive mode."""
        print("\n" + "=" * 50)
        print("📖 Coding Agent - Help")
        print("=" * 50)
        print("\nCommands:")
        print("  help, ?          Show this help message")
        print("  reset            Reset conversation history (start fresh)")
        print("  quit, exit, q    Exit interactive mode")
        print("\nUsage:")
        print("  Simply type a coding task and press Enter.")
        print("  The agent will process your task and provide a response.")
        print("\nExamples:")
        print("  > Write a Python function to calculate factorial")
        print("  > Create a REST API endpoint for user authentication")
        print("  > Implement a binary search tree in Python")
        print("\n" + "=" * 50)

    def cleanup(self) -> None:
        """
        Clean up coding agent resources.

        Closes gRPC connections and releases any resources held by the
        coding agent. Should be called when the command is finished.
        """
        if self._agent:
            # Close gRPC connection if needed
            if hasattr(self._agent, "_channel") and self._agent._channel:
                self._agent._channel.close()
            logger.info("Coding agent cleanup complete")
