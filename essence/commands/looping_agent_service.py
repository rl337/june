"""
Looping agent service command implementation.

This service runs a looping agent that interacts with the Switchboard service
to execute tasks. It runs for a specified number of iterations and then exits.
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Dict, Optional

import httpx

from essence.command import Command

# Setup tracing early
tracer = None
try:
    from opentelemetry import trace

    from essence.chat.utils.tracing import get_tracer, setup_tracing

    setup_tracing(service_name="june-looping-agent")
    tracer = get_tracer(__name__)
except ImportError:
    pass

logger = logging.getLogger(__name__)


class LoopingAgentServiceCommand(Command):
    """
    Command for running the looping agent service.

    This service:
    - Connects to the Switchboard service via REST API
    - Retrieves available tasks from Todorama
    - Executes agents via Switchboard to complete tasks
    - Runs for a specified number of iterations and exits
    """

    @classmethod
    def get_name(cls) -> str:
        """Get the command name."""
        return "looping-agent-service"

    @classmethod
    def get_description(cls) -> str:
        """Get the command description."""
        return "Run the looping agent service that executes tasks via Switchboard"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """Add command-line arguments."""
        parser.add_argument(
            "--iterations",
            type=int,
            default=int(os.getenv("LOOPING_AGENT_ITERATIONS", "50")),
            help="Number of iterations to run (default: 50, 0 = infinite)",
        )
        parser.add_argument(
            "--sleep-interval",
            type=int,
            default=int(os.getenv("LOOPING_AGENT_SLEEP_INTERVAL", "60")),
            help="Sleep time between iterations in seconds (default: 60)",
        )
        parser.add_argument(
            "--agent-mode",
            type=str,
            default=os.getenv("AGENT_MODE", "lifecycle"),
            choices=["normal", "architect", "refactor-planner", "project-cleanup", "precommit", "lifecycle"],
            help="Agent mode/role to use. 'lifecycle' cycles through all roles (default: lifecycle)",
        )
        parser.add_argument(
            "--lifecycle-roles",
            type=str,
            default=os.getenv("LIFECYCLE_ROLES", "architect,implementation,precommit,refactor-planner,project-cleanup"),
            help="Comma-separated list of roles to cycle through in lifecycle mode (default: architect,implementation,precommit,refactor-planner,project-cleanup)",
        )
        parser.add_argument(
            "--role-priority",
            type=str,
            default=os.getenv("ROLE_PRIORITY", "architect,precommit,implementation,refactor-planner,project-cleanup"),
            help="Priority order for role selection when multiple tasks available (default: architect,precommit,implementation,refactor-planner,project-cleanup)",
        )
        parser.add_argument(
            "--switchboard-url",
            type=str,
            default=os.getenv("SWITCHBOARD_URL", "http://june-switchboard:8082"),
            help="Switchboard service URL (default: http://june-switchboard:8082)",
        )
        parser.add_argument(
            "--todo-service-url",
            type=str,
            default=os.getenv("TODO_SERVICE_URL", "http://todorama-mcp-service-todo:8004"),
            help="Todorama service URL (default: http://todorama-mcp-service-todo:8004)",
        )
        parser.add_argument(
            "--api-key",
            type=str,
            default=os.getenv("TODO_API_KEY", "test-key"),
            help="Todorama API key (default: test-key)",
        )

    def init(self) -> None:
        """Initialize the looping agent service."""
        self.setup_signal_handlers()

        # Agent role mapping
        # Maps agent mode to the role name used in switchboard
        self.agent_role_map: Dict[str, str] = {
            "normal": "implementation",  # Normal agent has roles: ["implementation", "task-worker"]
            "architect": "architect",
            "refactor-planner": "refactor-planner",
            "project-cleanup": "project-cleanup",
            "precommit": "testing",  # Precommit agent has role "testing"
            "lifecycle": "lifecycle",  # Special mode that cycles through roles
        }
        
        # Lifecycle role configuration
        if self.args.agent_mode == "lifecycle":
            self.lifecycle_roles = [r.strip() for r in self.args.lifecycle_roles.split(",")]
            self.role_priority = [r.strip() for r in self.args.role_priority.split(",")]
            self.current_lifecycle_role_index = 0
            logger.info(f"Lifecycle mode enabled with roles: {self.lifecycle_roles}")
            logger.info(f"Role priority: {self.role_priority}")

        # HTTP client will be created in async context
        self.client: Optional[httpx.AsyncClient] = None

        # Session tracking
        self.session_id: Optional[str] = None
        self.agent_id: Optional[str] = None
        self.iteration_count = 0
        self._shutdown_requested = False
        
        # Lifecycle mode state
        self.current_lifecycle_role_index = 0
        self.lifecycle_roles: list = []
        self.role_priority: list = []

        logger.info("Looping agent service initialized")

    async def get_agent_id_by_role(self, role: str) -> Optional[str]:
        """Get agent ID by role from Switchboard."""
        span = None
        if tracer:
            span = tracer.start_span("get_agent_id_by_role")
            span.set_attribute("agent.role", role)
        try:
            response = await self.client.get(f"{self.args.switchboard_url}/agents")
            response.raise_for_status()
            agents_data = response.json()

            if "agents" in agents_data and isinstance(agents_data["agents"], dict):
                # Find agent with matching role
                for agent_id, agent_info in agents_data["agents"].items():
                    if isinstance(agent_info, dict) and "roles" in agent_info:
                        roles = agent_info.get("roles", [])
                        if isinstance(roles, list) and role in roles:
                            return agent_id

            logger.warning(f"No agent found with role: {role}")
            if span:
                span.set_attribute("agent.found", False)
                span.end()
            return None
        except Exception as e:
            logger.error(f"Failed to get agent by role {role}: {e}", exc_info=True)
            if span:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.end()
            return None
        finally:
            if span:
                span.set_attribute("agent.found", True)
                span.end()

    async def execute_agent(
        self, agent_id: str, session_id: str, message: str, context: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Execute agent via Switchboard."""
        span = None
        if tracer:
            span = tracer.start_span("execute_agent")
            span.set_attribute("agent.id", agent_id)
            span.set_attribute("agent.session_id", session_id)
            span.set_attribute("message.length", len(message))

        if context is None:
            context = {}

        payload = {
            "agent_id": agent_id,
            "session_id": session_id,
            "message": message,
            "context": context,
        }

        try:
            response = await self.client.post(
                f"{self.args.switchboard_url}/agents/{agent_id}/execute/sync",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            if span:
                span.set_attribute("agent.execution.status", result.get("status", "unknown"))
                span.end()
            return result
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error executing agent: {e.response.status_code} - {e.response.text}")
            if span:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, f"HTTP {e.response.status_code}"))
                span.end()
            return None
        except Exception as e:
            logger.error(f"Failed to execute agent: {e}", exc_info=True)
            if span:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.end()
            return None

    async def get_available_tasks(self) -> list:
        """Get available tasks from Todorama."""
        try:
            response = await self.client.post(
                f"{self.args.todo_service_url}/mcp/list_available_tasks",
                headers={"X-API-Key": self.args.api_key},
                json={"agent_type": "implementation", "limit": 50},
            )
            response.raise_for_status()
            data = response.json()
            tasks = data.get("tasks", [])
            # Filter for concrete tasks that are available
            available = [
                t
                for t in tasks
                if t.get("task_type") == "concrete" and t.get("effective_status") == "available"
            ]
            return available
        except Exception as e:
            logger.error(f"Failed to get available tasks: {e}", exc_info=True)
            return []

    async def run_iteration(self) -> bool:
        """Run a single iteration of the loop."""
        self.iteration_count += 1
        span = None
        if tracer:
            span = tracer.start_span("run_iteration")
            span.set_attribute("iteration.number", self.iteration_count)
        
        logger.info(f"Starting iteration {self.iteration_count}")

        # Get agent ID if we don't have it yet
        if not self.agent_id:
            role = self.agent_role_map.get(self.args.agent_mode, "normal")
            self.agent_id = await self.get_agent_id_by_role(role)
            if not self.agent_id:
                logger.error(f"Failed to get agent ID for role: {role}")
                return False

            # Use role as session ID for persistence
            self.session_id = role
            logger.info(f"Using agent ID: {self.agent_id}, session ID: {self.session_id}")

        # Get available tasks
        tasks = await self.get_available_tasks()
        if not tasks:
            logger.info("No available tasks found, skipping iteration")
            return True

        # Select first available task
        task = tasks[0]
        task_id = task.get("task_id", "unknown")
        task_description = task.get("description", "No description")

        logger.info(f"Processing task {task_id}: {task_description}")

        # Build message for agent
        message = f"Please work on this task: {task_description}\n\nTask ID: {task_id}"

        # Execute agent
        response = await self.execute_agent(
            self.agent_id,
            self.session_id,
            message,
            context={"task_id": task_id, "task": task},
        )

        if response:
            logger.info(f"Agent execution completed for task {task_id}")
            logger.debug(f"Agent response: {response}")
            if span:
                span.set_attribute("iteration.success", True)
                span.set_attribute("task.id", task_id)
        else:
            logger.warning(f"Agent execution failed for task {task_id}")
            if span:
                span.set_attribute("iteration.success", False)
                span.set_status(trace.Status(trace.StatusCode.ERROR, "Agent execution failed"))

        if span:
            span.end()
        return True

    def run(self) -> None:
        """Run the looping agent service."""
        iterations = self.args.iterations
        sleep_interval = self.args.sleep_interval

        logger.info(
            f"Starting looping agent service: mode={self.args.agent_mode}, "
            f"iterations={'infinite' if iterations == 0 else iterations}, "
            f"sleep_interval={sleep_interval}s"
        )

        async def run_loop():
            # Create HTTP client in async context
            self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout for agent execution
            try:
                while True:
                    # Check if we should stop
                    if iterations > 0 and self.iteration_count >= iterations:
                        logger.info(f"Reached iteration limit ({iterations}), stopping")
                        break

                    # Check shutdown event
                    if self._shutdown_requested or (
                        self._shutdown_event and self._shutdown_event.is_set()
                    ):
                        logger.info("Shutdown requested, stopping")
                        break

                    # Run iteration
                    success = await self.run_iteration()
                    if not success:
                        logger.error("Iteration failed, continuing...")

                    # Sleep between iterations (unless shutting down)
                    if not (self._shutdown_requested or (
                        self._shutdown_event and self._shutdown_event.is_set()
                    )):
                        if iterations == 0 or self.iteration_count < iterations:
                            logger.info(f"Sleeping for {sleep_interval} seconds...")
                            # Sleep in small chunks to check for shutdown
                            for _ in range(sleep_interval):
                                if self._shutdown_requested or (
                                    self._shutdown_event and self._shutdown_event.is_set()
                                ):
                                    break
                                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in run loop: {e}", exc_info=True)
                raise
            finally:
                # Clean up HTTP client
                if self.client:
                    await self.client.aclose()

        # Run the async loop
        try:
            asyncio.run(run_loop())
        except KeyboardInterrupt:
            logger.info("Loop interrupted by user")
            self._shutdown_requested = True

    def cleanup(self) -> None:
        """Clean up resources."""
        # Client cleanup is handled in the async run_loop finally block
        logger.info(f"Looping agent service completed {self.iteration_count} iterations")

