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
    """Command for interacting with the coding agent."""
    
    def __init__(self, args: argparse.Namespace):
        """Initialize command with parsed arguments."""
        super().__init__(args)
        self._agent = None
    
    @classmethod
    def get_name(cls) -> str:
        return "coding-agent"
    
    @classmethod
    def get_description(cls) -> str:
        return "Interactive interface for coding tasks with Qwen3 model"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
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
            default=Path(os.getenv("CODING_AGENT_WORKSPACE", "/tmp/coding_agent_workspace")),
            help="Workspace directory for agent operations (default: /tmp/coding_agent_workspace)",
        )
        parser.add_argument(
            "--inference-api-url",
            default=os.getenv("INFERENCE_API_URL", "localhost:50051"),
            help="gRPC endpoint for inference API (default: localhost:50051)",
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
        """Initialize coding agent."""
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
        """Run the coding agent."""
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
        """Execute a single coding task."""
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
            
        except Exception as e:
            logger.error(f"Error executing task: {e}", exc_info=True)
            print(f"\n❌ Error: {e}")
            sys.exit(1)
    
    def _run_interactive(self) -> None:
        """Run in interactive mode."""
        print("\n🤖 Coding Agent - Interactive Mode")
        print("=" * 50)
        print("Enter coding tasks (or 'quit' to exit)")
        print("=" * 50)
        
        try:
            while True:
                print("\n> ", end="", flush=True)
                task = input().strip()
                
                if not task:
                    continue
                
                if task.lower() in ["quit", "exit", "q"]:
                    print("\n👋 Goodbye!")
                    break
                
                if task.lower() == "reset":
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
                except Exception as e:
                    logger.error(f"Error executing task: {e}", exc_info=True)
                    print(f"\n❌ Error: {e}")
        
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user")
        except EOFError:
            print("\n\n👋 Goodbye!")
    
    def cleanup(self) -> None:
        """Clean up coding agent resources."""
        if self._agent:
            # Close gRPC connection if needed
            if hasattr(self._agent, '_channel') and self._agent._channel:
                self._agent._channel.close()
            logger.info("Coding agent cleanup complete")
