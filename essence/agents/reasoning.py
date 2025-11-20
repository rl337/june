"""
Agentic Reasoning Service

Core reasoning loop implementation for structured agentic reasoning/planning.
Implements the think → plan → execute → reflect loop.
"""
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from opentelemetry import trace

from essence.agents.reasoning_cache import ReasoningCache, get_reasoning_cache
from essence.chat.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class ReasoningStep(str, Enum):
    """Steps in the reasoning loop"""

    THINK = "think"
    PLAN = "plan"
    EXECUTE = "execute"
    REFLECT = "reflect"
    COMPLETE = "complete"


@dataclass
class Step:
    """Represents a single step in an execution plan"""

    step_id: int
    description: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    expected_output: Optional[str] = None
    dependencies: List[int] = field(default_factory=list)


@dataclass
class Plan:
    """Represents an execution plan"""

    steps: List[Step] = field(default_factory=list)
    estimated_complexity: str = "simple"  # "simple", "moderate", "complex"
    success_criteria: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        step_descriptions = "\n".join(
            f"  {i+1}. {step.description}" for i, step in enumerate(self.steps)
        )
        return f"Plan ({self.estimated_complexity}):\n{step_descriptions}"


@dataclass
class ExecutionResult:
    """Result of executing a step"""

    step_id: int
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    tool_used: Optional[str] = None

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} Step {self.step_id}: {self.output if self.success else self.error}"


@dataclass
class ReflectionResult:
    """Result of reflection phase"""

    goal_achieved: bool
    issues_found: List[str] = field(default_factory=list)
    plan_adjustments: Optional[Plan] = None
    should_continue: bool = False
    final_response: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0

    def __str__(self) -> str:
        status = "✓ Goal achieved" if self.goal_achieved else "✗ Goal not achieved"
        issues = (
            f"\n  Issues: {', '.join(self.issues_found)}" if self.issues_found else ""
        )
        return f"{status}{issues}"


@dataclass
class ReasoningState:
    """Tracks state through reasoning loop"""

    current_step: ReasoningStep = ReasoningStep.THINK
    plan: Optional[Plan] = None
    execution_results: List[ExecutionResult] = field(default_factory=list)
    reflection: Optional[ReflectionResult] = None
    iteration: int = 0
    start_time: float = field(default_factory=time.time)
    total_time: float = 0.0

    def update_time(self) -> None:
        """Update total time elapsed"""
        self.total_time = time.time() - self.start_time


@dataclass
class ReasoningResult:
    """Final result of reasoning loop"""

    success: bool
    final_response: str
    iterations: int
    total_time: float
    plan: Optional[Plan] = None
    execution_results: List[ExecutionResult] = field(default_factory=list)
    reflection: Optional[ReflectionResult] = None
    error: Optional[str] = None


@dataclass
class ConversationContext:
    """Manages conversation state"""

    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_history: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_history: List[ReasoningResult] = field(default_factory=list)
    tool_state: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)


class AgenticReasoner:
    """
    Main reasoning orchestrator that executes the reasoning loop.

    Implements: think → plan → execute → reflect → (repeat if needed)
    """

    def __init__(
        self,
        planner: Optional[Any] = None,  # Planner instance
        executor: Optional[Any] = None,  # Executor instance
        reflector: Optional[Any] = None,  # Reflector instance
        llm_client: Optional[Any] = None,  # LLM client instance
        max_iterations: int = 5,
        think_timeout: float = 10.0,
        plan_timeout: float = 15.0,
        execute_timeout: float = 60.0,
        reflect_timeout: float = 10.0,
        total_timeout: float = 300.0,
        cache: Optional[ReasoningCache] = None,
        enable_cache: bool = True,
        enable_early_termination: bool = True,
        enable_agent_communication: bool = False,  # Enable agent-to-user communication
    ):
        """
        Initialize the agentic reasoner.

        Args:
            planner: Planner instance for creating execution plans
            executor: Executor instance for executing steps
            reflector: Reflector instance for evaluating results
            llm_client: LLM client for reasoning phases
            max_iterations: Maximum number of reasoning loop iterations
            think_timeout: Timeout for think phase (seconds)
            plan_timeout: Timeout for plan phase (seconds)
            execute_timeout: Timeout for execute phase (seconds)
            reflect_timeout: Timeout for reflect phase (seconds)
            total_timeout: Total timeout for entire reasoning loop (seconds)
            cache: Reasoning cache instance (optional, uses global cache if None)
            enable_cache: Whether to enable caching
            enable_early_termination: Whether to enable early termination for simple requests
            enable_agent_communication: Whether to enable agent-to-user communication during reasoning
        """
        self.planner = planner
        self.executor = executor
        self.reflector = reflector
        self.llm_client = llm_client
        self.max_iterations = max_iterations
        self.think_timeout = think_timeout
        self.plan_timeout = plan_timeout
        self.execute_timeout = execute_timeout
        self.reflect_timeout = reflect_timeout
        self.total_timeout = total_timeout
        self.cache = cache or (get_reasoning_cache() if enable_cache else None)
        self.enable_cache = enable_cache
        self.enable_early_termination = enable_early_termination
        self.enable_agent_communication = enable_agent_communication

    def reason(
        self,
        user_message: str,
        context: ConversationContext,
        available_tools: Optional[List[Any]] = None,
    ) -> ReasoningResult:
        """
        Execute reasoning loop: think → plan → execute → reflect.

        Args:
            user_message: The user's request/message
            context: Conversation context (history, state, etc.)
            available_tools: List of available tools for execution

        Returns:
            ReasoningResult with final response and execution details
        """
        with tracer.start_as_current_span("agentic_reasoner.reason") as span:
            try:
                span.set_attribute("user_message_length", len(user_message))
                span.set_attribute("max_iterations", self.max_iterations)
                span.set_attribute("user_id", context.user_id or "unknown")
                span.set_attribute("chat_id", context.chat_id or "unknown")

                # Early termination for simple requests
                if self.enable_early_termination and self._is_simple_request(
                    user_message, context
                ):
                    span.set_attribute("early_termination", True)
                    logger.debug("Early termination: simple request detected")
                    return self._handle_simple_request(user_message, context, span)

                state = ReasoningState()
                available_tools = available_tools or []

                # Main reasoning loop
                for iteration in range(self.max_iterations):
                    state.iteration = iteration + 1
                    state.update_time()

                    # Check total timeout
                    if state.total_time > self.total_timeout:
                        logger.warning(
                            f"Reasoning loop timed out after {state.total_time:.2f}s"
                        )
                        span.set_attribute("timeout", True)
                        span.set_attribute("timeout_time", state.total_time)
                        return ReasoningResult(
                            success=False,
                            final_response=(
                                "I'm sorry, but this request is taking too long to process. "
                                "Please try simplifying your request or breaking it into smaller parts."
                            ),
                            iterations=state.iteration,
                            total_time=state.total_time,
                            error=f"Total timeout exceeded ({self.total_timeout}s)",
                        )

                    span.set_attribute("iteration", state.iteration)
                    span.set_attribute("current_step", state.current_step.value)

                    logger.info(
                        f"Reasoning iteration {state.iteration}/{self.max_iterations}, step: {state.current_step.value}"
                    )

                    # THINK phase
                    if state.current_step == ReasoningStep.THINK:
                        analysis = self._think(user_message, context, span)
                        if analysis is None:
                            return ReasoningResult(
                                success=False,
                                final_response="I encountered an error while analyzing your request. Please try again.",
                                iterations=state.iteration,
                                total_time=state.total_time,
                                error="Think phase failed",
                            )
                        state.current_step = ReasoningStep.PLAN

                    # PLAN phase
                    elif state.current_step == ReasoningStep.PLAN:
                        plan = self._plan(user_message, context, available_tools, span)
                        if plan is None:
                            return ReasoningResult(
                                success=False,
                                final_response="I couldn't create a plan for your request. Please try rephrasing it.",
                                iterations=state.iteration,
                                total_time=state.total_time,
                                error="Plan phase failed",
                            )
                        state.plan = plan
                        state.current_step = ReasoningStep.EXECUTE
                        logger.info(f"Created plan with {len(plan.steps)} steps")

                    # EXECUTE phase
                    elif state.current_step == ReasoningStep.EXECUTE:
                        if state.plan is None:
                            return ReasoningResult(
                                success=False,
                                final_response="Execution failed: no plan available.",
                                iterations=state.iteration,
                                total_time=state.total_time,
                                error="No plan available for execution",
                            )

                        results = self._execute(state.plan, context, span)
                        state.execution_results.extend(results)
                        state.current_step = ReasoningStep.REFLECT
                        logger.info(f"Executed {len(results)} steps")

                    # REFLECT phase
                    elif state.current_step == ReasoningStep.REFLECT:
                        reflection = self._reflect(
                            user_message,
                            state.plan,
                            state.execution_results,
                            context,
                            span,
                        )
                        state.reflection = reflection

                        if reflection.goal_achieved or not reflection.should_continue:
                            # Goal achieved or no need to continue
                            state.current_step = ReasoningStep.COMPLETE
                            state.update_time()

                            final_response = (
                                reflection.final_response
                                or self._format_response(
                                    state.plan,
                                    state.execution_results,
                                    reflection,
                                )
                            )

                            span.set_attribute("success", True)
                            span.set_attribute("iterations", state.iteration)
                            span.set_attribute("total_time", state.total_time)

                            return ReasoningResult(
                                success=True,
                                final_response=final_response,
                                iterations=state.iteration,
                                total_time=state.total_time,
                                plan=state.plan,
                                execution_results=state.execution_results,
                                reflection=reflection,
                            )
                        else:
                            # Need to adjust plan and retry
                            if reflection.plan_adjustments:
                                state.plan = reflection.plan_adjustments
                                logger.info("Adjusting plan based on reflection")
                            state.current_step = (
                                ReasoningStep.THINK
                            )  # Start over with adjusted plan

                    # COMPLETE phase
                    elif state.current_step == ReasoningStep.COMPLETE:
                        break

                # Max iterations reached
                state.update_time()
                logger.warning(f"Reached max iterations ({self.max_iterations})")
                span.set_attribute("max_iterations_reached", True)

                final_response = self._format_response(
                    state.plan,
                    state.execution_results,
                    state.reflection,
                )

                return ReasoningResult(
                    success=state.reflection.goal_achieved
                    if state.reflection
                    else False,
                    final_response=final_response,
                    iterations=state.iteration,
                    total_time=state.total_time,
                    plan=state.plan,
                    execution_results=state.execution_results,
                    reflection=state.reflection,
                    error=f"Reached max iterations ({self.max_iterations})",
                )

            except Exception as e:
                logger.error(f"Error in reasoning loop: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

                return ReasoningResult(
                    success=False,
                    final_response="I encountered an unexpected error while processing your request. Please try again.",
                    iterations=state.iteration if "state" in locals() else 0,
                    total_time=state.total_time if "state" in locals() else 0.0,
                    error=str(e),
                )

    def _think(
        self,
        user_message: str,
        context: ConversationContext,
        span: trace.Span,
    ) -> Optional[str]:
        """Think phase: Analyze the user's request."""
        with tracer.start_as_current_span("reasoner.think") as think_span:
            try:
                think_span.set_attribute("user_message_length", len(user_message))

                # Check cache first
                if self.cache:
                    cache_key_data = {
                        "message": user_message,
                        "context_length": len(context.message_history)
                        if context.message_history
                        else 0,
                    }
                    cached_analysis = self.cache.get("think", cache_key_data)
                    if cached_analysis:
                        think_span.set_attribute("cache_hit", True)
                        logger.debug("Using cached think analysis")
                        return cached_analysis
                    think_span.set_attribute("cache_hit", False)

                # If LLM client is available, use it for thinking
                if self.llm_client:
                    try:
                        # Convert message history to format expected by LLM client
                        conversation_history = None
                        if context.message_history:
                            conversation_history = [
                                {
                                    "role": msg.get("role", "user"),
                                    "content": msg.get("content", ""),
                                }
                                for msg in context.message_history[
                                    -10:
                                ]  # Last 10 messages
                            ]

                        # Generate analysis using LLM
                        analysis = self.llm_client.think(
                            user_message=user_message,
                            conversation_history=conversation_history,
                        )

                        # Cache the analysis
                        if self.cache and analysis:
                            cache_key_data = {
                                "message": user_message,
                                "context_length": len(context.message_history)
                                if context.message_history
                                else 0,
                            }
                            self.cache.put("think", cache_key_data, analysis)

                        think_span.set_attribute("llm_think_used", True)
                        think_span.set_attribute("analysis_length", len(analysis))
                        return analysis

                    except Exception as e:
                        logger.error(f"Error in LLM think phase: {e}", exc_info=True)
                        think_span.record_exception(e)
                        # Fallback to simple analysis
                        analysis = f"Analyzing request: {user_message[:100]}..."
                        think_span.set_attribute("analysis_length", len(analysis))
                        return analysis
                else:
                    # Fallback: simple analysis
                    return f"Request analysis: {len(user_message)} characters"

            except Exception as e:
                logger.error(f"Error in think phase: {e}", exc_info=True)
                think_span.record_exception(e)
                return None

    def _plan(
        self,
        user_message: str,
        context: ConversationContext,
        available_tools: List[Any],
        span: trace.Span,
    ) -> Optional[Plan]:
        """Plan phase: Create an execution plan."""
        with tracer.start_as_current_span("reasoner.plan") as plan_span:
            try:
                if self.planner:
                    return self.planner.create_plan(
                        user_message, available_tools, context
                    )
                else:
                    # Fallback: create a simple plan
                    return Plan(
                        steps=[Step(step_id=1, description=user_message)],
                        estimated_complexity="simple",
                        success_criteria=["Complete the request"],
                    )

            except Exception as e:
                logger.error(f"Error in plan phase: {e}", exc_info=True)
                plan_span.record_exception(e)
                return None

    def _execute(
        self,
        plan: Plan,
        context: ConversationContext,
        span: trace.Span,
    ) -> List[ExecutionResult]:
        """Execute phase: Execute the plan step by step."""
        with tracer.start_as_current_span("reasoner.execute") as execute_span:
            try:
                results = []

                if self.executor:
                    for step in plan.steps:
                        result = self.executor.execute_step(step, context)
                        results.append(result)
                else:
                    # Fallback: create mock results
                    for step in plan.steps:
                        results.append(
                            ExecutionResult(
                                step_id=step.step_id,
                                success=True,
                                output=f"Executed: {step.description}",
                                execution_time=0.1,
                            )
                        )

                execute_span.set_attribute("steps_executed", len(results))
                execute_span.set_attribute(
                    "successful_steps", sum(1 for r in results if r.success)
                )

                return results

            except Exception as e:
                logger.error(f"Error in execute phase: {e}", exc_info=True)
                execute_span.record_exception(e)
                return []

    def _reflect(
        self,
        user_message: str,
        plan: Optional[Plan],
        execution_results: List[ExecutionResult],
        context: ConversationContext,
        span: trace.Span,
    ) -> ReflectionResult:
        """Reflect phase: Evaluate results and determine next steps."""
        with tracer.start_as_current_span("reasoner.reflect") as reflect_span:
            try:
                if self.reflector:
                    return self.reflector.reflect(plan, execution_results, user_message)
                else:
                    # Fallback: simple reflection
                    all_successful = all(r.success for r in execution_results)
                    return ReflectionResult(
                        goal_achieved=all_successful,
                        should_continue=not all_successful,
                        confidence=1.0 if all_successful else 0.5,
                    )

            except Exception as e:
                logger.error(f"Error in reflect phase: {e}", exc_info=True)
                reflect_span.record_exception(e)
                return ReflectionResult(
                    goal_achieved=False,
                    issues_found=[str(e)],
                    should_continue=False,
                    confidence=0.0,
                )

    def _format_response(
        self,
        plan: Optional[Plan],
        execution_results: List[ExecutionResult],
        reflection: Optional[ReflectionResult],
    ) -> str:
        """Format the final response from plan, results, and reflection."""
        if reflection and reflection.final_response:
            return reflection.final_response

        # Build response from execution results
        if execution_results:
            successful = [r for r in execution_results if r.success]
            failed = [r for r in execution_results if not r.success]

            response_parts = []
            if successful:
                response_parts.append("Completed the following steps:")
                for result in successful:
                    response_parts.append(f"  ✓ {result.output}")

            if failed:
                response_parts.append("\nEncountered issues:")
                for result in failed:
                    response_parts.append(f"  ✗ {result.error}")

            return "\n".join(response_parts)

        return "I've processed your request, but couldn't generate a detailed response."

    def _is_simple_request(
        self,
        user_message: str,
        context: ConversationContext,
    ) -> bool:
        """
        Determine if a request is simple enough to skip full reasoning loop.

        Args:
            user_message: The user's message
            context: Conversation context

        Returns:
            True if request is simple, False otherwise
        """
        # Simple requests are:
        # - Short messages (< 50 characters)
        # - No tool keywords
        # - No complex reasoning keywords
        # - No multi-turn conversation context

        if len(user_message) < 50:
            # Check for simple question patterns
            simple_patterns = [
                "hello",
                "hi",
                "hey",
                "thanks",
                "thank you",
                "yes",
                "no",
                "ok",
                "okay",
                "sure",
            ]
            if any(pattern in user_message.lower() for pattern in simple_patterns):
                return True

        # Check for tool keywords (indicates complexity)
        tool_keywords = ["file", "code", "write", "create", "modify", "execute", "run"]
        if any(keyword in user_message.lower() for keyword in tool_keywords):
            return False

        # Check for reasoning keywords (indicates need for planning)
        reasoning_keywords = ["plan", "step", "reason", "think", "break down", "how to"]
        if any(keyword in user_message.lower() for keyword in reasoning_keywords):
            return False

        # Check conversation history (multi-turn = more complex)
        if context.message_history and len(context.message_history) > 2:
            return False

        # Very short messages without complexity indicators are simple
        return len(user_message) < 100

    def _handle_simple_request(
        self,
        user_message: str,
        context: ConversationContext,
        span: trace.Span,
    ) -> ReasoningResult:
        """
        Handle simple requests without full reasoning loop.

        Args:
            user_message: The user's message
            context: Conversation context
            span: Tracing span

        Returns:
            ReasoningResult with direct response
        """
        # For simple requests, create a minimal plan and execute directly
        if self.planner:
            # Create a simple single-step plan
            simple_plan = Plan(
                steps=[Step(step_id=1, description=user_message)],
                estimated_complexity="simple",
                success_criteria=["Respond to user"],
            )

            # Execute the plan
            execution_results = []
            if self.executor:
                execution_results = self.executor.execute_plan(
                    simple_plan.steps, context
                )
            else:
                # Fallback: create mock result
                execution_results = [
                    ExecutionResult(
                        step_id=1,
                        success=True,
                        output=f"Response to: {user_message}",
                    )
                ]

            # Simple reflection
            reflection = ReflectionResult(
                goal_achieved=True,
                confidence=0.9,
                final_response=execution_results[0].output
                if execution_results
                else user_message,
            )

            span.set_attribute("simple_request", True)
            span.set_attribute("iterations", 1)

            return ReasoningResult(
                success=True,
                final_response=reflection.final_response or user_message,
                iterations=1,
                total_time=0.1,  # Minimal time for simple requests
                plan=simple_plan,
                execution_results=execution_results,
                reflection=reflection,
            )
        else:
            # No planner available, return direct response
            return ReasoningResult(
                success=True,
                final_response=user_message,
                iterations=0,
                total_time=0.0,
            )

    def _send_agent_message(
        self,
        context: ConversationContext,
        message: str,
        message_type: str = "text",
    ) -> bool:
        """
        Send a message to the user via agent communication interface.

        This is a helper method that wraps the agent communication interface,
        making it easy for the reasoning system to communicate with users.

        Args:
            context: Conversation context with user_id and chat_id
            message: Message text to send
            message_type: Type of message ("text", "error", "status", "clarification", "help_request", "progress")

        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enable_agent_communication:
            return False

        if not context.user_id or not context.chat_id:
            logger.debug(
                "Cannot send agent message: user_id or chat_id not set in context"
            )
            return False

        try:
            # Use Message API instead of direct function calls
            from essence.chat.message_api_client import send_message_via_api

            # Map CommunicationChannel.AUTO to "auto" string
            platform_str = "auto"  # AUTO tries Telegram first, falls back to Discord

            result = send_message_via_api(
                user_id=str(context.user_id),
                chat_id=str(context.chat_id),
                message=message,
                platform=platform_str,
                message_type=message_type,
            )

            if result.get("success"):
                logger.info(
                    f"Agent message sent to user {context.user_id}: {message_type}"
                )
                return True
            else:
                logger.warning(
                    f"Failed to send agent message: {result.get('error', 'Unknown error')}"
                )
                return False

        except Exception as e:
            logger.warning(f"Error sending agent message: {e}")
            return False

    def _ask_for_clarification(
        self,
        context: ConversationContext,
        question: str,
        context_info: Optional[str] = None,
    ) -> bool:
        """
        Ask user for clarification during reasoning.

        Args:
            context: Conversation context
            question: Question to ask the user
            context_info: Optional context about what needs clarification

        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enable_agent_communication:
            return False

        try:
            from essence.chat.message_api_client import send_message_via_api

            message = f"❓ **Clarification Needed**\n\n{question}"
            if context_info:
                message += f"\n\n_Context: {context_info}_"

            result = send_message_via_api(
                user_id=str(context.user_id) if context.user_id else "",
                chat_id=str(context.chat_id) if context.chat_id else "",
                message=message,
                platform="auto",
                message_type="clarification",
            )

            return result.get("success", False)

        except Exception as e:
            logger.warning(f"Error asking for clarification: {e}")
            return False

    def _request_help(
        self,
        context: ConversationContext,
        issue: str,
        blocker_description: Optional[str] = None,
    ) -> bool:
        """
        Request help from user when agent encounters a blocker.

        Args:
            context: Conversation context
            issue: Description of the issue/blocker
            blocker_description: Optional detailed description

        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enable_agent_communication:
            return False

        try:
            from essence.chat.message_api_client import send_message_via_api

            message = f"🆘 **Help Requested**\n\n{issue}"
            if blocker_description:
                message += f"\n\n_Details: {blocker_description}_"

            result = send_message_via_api(
                user_id=str(context.user_id) if context.user_id else "",
                chat_id=str(context.chat_id) if context.chat_id else "",
                message=message,
                platform="auto",
                message_type="help_request",
            )

            return result.get("success", False)

        except Exception as e:
            logger.warning(f"Error requesting help: {e}")
            return False

    def _report_progress(
        self,
        context: ConversationContext,
        progress_message: str,
        completion_percentage: Optional[int] = None,
    ) -> bool:
        """
        Report progress on a task to the user.

        Args:
            context: Conversation context
            progress_message: Progress update message
            completion_percentage: Optional completion percentage (0-100)

        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enable_agent_communication:
            return False

        try:
            from essence.chat.message_api_client import send_message_via_api

            message = f"📊 **Progress Update**\n\n{progress_message}"
            if completion_percentage is not None:
                message += f"\n\n_Completion: {completion_percentage}%_"

            result = send_message_via_api(
                user_id=str(context.user_id) if context.user_id else "",
                chat_id=str(context.chat_id) if context.chat_id else "",
                message=message,
                platform="auto",
                message_type="progress",
            )

            return result.get("success", False)

        except Exception as e:
            logger.warning(f"Error reporting progress: {e}")
            return False
