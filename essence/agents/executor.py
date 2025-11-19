"""
Execution Component

Executes planned steps using available tools.
"""
import logging
import time
from typing import Any, Dict, List, Optional

from opentelemetry import trace

from essence.agents.reasoning import ConversationContext, ExecutionResult, Step
from essence.chat.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class Executor:
    """
    Executes planned steps using available tools.

    Handles tool invocation, error handling, and result collection.
    """

    def __init__(
        self,
        available_tools: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
    ):
        """
        Initialize the executor.

        Args:
            available_tools: Dictionary mapping tool names to tool instances
            max_retries: Maximum number of retries for failed steps
        """
        self.available_tools = available_tools or {}
        self.max_retries = max_retries

    def execute_step(
        self,
        step: Step,
        context: ConversationContext,
    ) -> ExecutionResult:
        """
        Execute a single step from the plan.

        Args:
            step: The step to execute
            context: Execution context (conversation state, tool state, etc.)

        Returns:
            ExecutionResult with success status, output, and error information
        """
        with tracer.start_as_current_span("executor.execute_step") as span:
            try:
                span.set_attribute("step_id", step.step_id)
                span.set_attribute("step_description", step.description)
                span.set_attribute("tool_name", step.tool_name or "none")

                start_time = time.time()

                # Check if step has dependencies that need to be satisfied first
                if step.dependencies:
                    # TODO: Check if dependencies are satisfied
                    pass

                # Execute the step
                if step.tool_name and step.tool_name in self.available_tools:
                    # Use tool to execute step
                    tool = self.available_tools[step.tool_name]
                    result = self._execute_with_tool(step, tool, context, span)
                else:
                    # No tool specified, execute as a general instruction
                    result = self._execute_general(step, context, span)

                execution_time = time.time() - start_time
                result.execution_time = execution_time

                span.set_attribute("success", result.success)
                span.set_attribute("execution_time", execution_time)

                if result.error:
                    span.set_attribute("error", result.error)

                return result

            except Exception as e:
                logger.error(f"Error executing step {step.step_id}: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                return ExecutionResult(
                    step_id=step.step_id,
                    success=False,
                    error=str(e),
                    execution_time=time.time() - start_time
                    if "start_time" in locals()
                    else 0.0,
                )

    def _execute_with_tool(
        self,
        step: Step,
        tool: Any,
        context: ConversationContext,
        span: trace.Span,
    ) -> ExecutionResult:
        """Execute step using a specific tool."""
        try:
            # Prepare tool arguments
            tool_args = step.tool_args or {}

            # Merge with context tool_state if available
            if step.tool_name and step.tool_name in context.tool_state:
                tool_args = {**context.tool_state[step.tool_name], **tool_args}

            span.set_attribute("tool_args", str(tool_args))

            # Call the tool
            if hasattr(tool, "call") or hasattr(tool, "__call__"):
                # Tool has a call method or is callable
                if hasattr(tool, "call"):
                    output = tool.call(**tool_args)
                else:
                    output = tool(**tool_args)
            elif hasattr(tool, "execute"):
                # Tool has an execute method
                output = tool.execute(**tool_args)
            else:
                # Try to call tool directly with description
                output = f"Tool '{step.tool_name}' executed: {step.description}"

            # Update tool state in context
            if step.tool_name:
                context.tool_state[step.tool_name] = tool_args

            return ExecutionResult(
                step_id=step.step_id,
                success=True,
                output=str(output) if output is not None else "Step completed",
                tool_used=step.tool_name,
            )

        except Exception as e:
            logger.error(f"Error executing tool {step.tool_name}: {e}", exc_info=True)
            return ExecutionResult(
                step_id=step.step_id,
                success=False,
                error=f"Tool execution failed: {str(e)}",
                tool_used=step.tool_name,
            )

    def _execute_general(
        self,
        step: Step,
        context: ConversationContext,
        span: trace.Span,
    ) -> ExecutionResult:
        """Execute step as a general instruction (no specific tool)."""
        try:
            # For general instructions, we can't actually execute them
            # This is a placeholder for future implementation
            # In a real system, this might involve LLM-based execution

            output = f"Processed instruction: {step.description}"

            return ExecutionResult(
                step_id=step.step_id,
                success=True,
                output=output,
            )

        except Exception as e:
            logger.error(f"Error executing general step: {e}", exc_info=True)
            return ExecutionResult(
                step_id=step.step_id,
                success=False,
                error=f"General execution failed: {str(e)}",
            )

    def execute_plan(
        self,
        steps: List[Step],
        context: ConversationContext,
    ) -> List[ExecutionResult]:
        """
        Execute multiple steps in sequence.

        Args:
            steps: List of steps to execute
            context: Execution context

        Returns:
            List of ExecutionResult objects
        """
        results = []

        for step in steps:
            result = self.execute_step(step, context)
            results.append(result)

            # Stop execution if a critical step fails
            if not result.success and step.step_id == 1:  # First step failure
                logger.warning(
                    f"Critical step {step.step_id} failed, stopping execution"
                )
                break

        return results
