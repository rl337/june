"""
Planning Component

Creates execution plans from user requests by breaking them down into steps.
"""
import logging
from typing import Any, Dict, List, Optional

from opentelemetry import trace

from essence.agents.reasoning import ConversationContext, Plan, Step
from essence.agents.reasoning_cache import ReasoningCache, get_reasoning_cache
from essence.chat.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class Planner:
    """
    Creates execution plans from user requests.

    Analyzes the request, identifies required tools, and creates a step-by-step plan.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        max_steps: int = 10,
        cache: Optional[ReasoningCache] = None,
        enable_cache: bool = True,
    ):
        """
        Initialize the planner.

        Args:
            llm_client: LLM client for generating plans (optional)
            max_steps: Maximum number of steps in a plan
            cache: Reasoning cache instance (optional, uses global cache if None)
            enable_cache: Whether to enable caching
        """
        self.llm_client = llm_client
        self.max_steps = max_steps
        self.cache = cache or (get_reasoning_cache() if enable_cache else None)
        self.enable_cache = enable_cache

    def create_plan(
        self,
        user_request: str,
        available_tools: List[Any],
        context: ConversationContext,
    ) -> Plan:
        """
        Generate a step-by-step plan from a user request.

        Args:
            user_request: The user's request/message
            available_tools: List of available tools for execution
            context: Conversation context

        Returns:
            Plan object with steps, complexity, and success criteria
        """
        with tracer.start_as_current_span("planner.create_plan") as span:
            try:
                span.set_attribute("request_length", len(user_request))
                span.set_attribute("available_tools_count", len(available_tools))

                # Check cache first
                if self.cache:
                    cache_key_data = {
                        "request": user_request,
                        "tools": [str(tool) for tool in available_tools],
                    }
                    cached_plan = self.cache.get("plan", cache_key_data)
                    if cached_plan:
                        span.set_attribute("cache_hit", True)
                        logger.debug("Using cached plan")
                        return cached_plan
                    span.set_attribute("cache_hit", False)

                # Generate plan
                if self.llm_client:
                    plan = self._create_plan_with_llm(
                        user_request, available_tools, context, span
                    )
                else:
                    plan = self._create_simple_plan(
                        user_request, available_tools, context, span
                    )

                # Cache the plan
                if self.cache and plan:
                    cache_key_data = {
                        "request": user_request,
                        "tools": [str(tool) for tool in available_tools],
                    }
                    self.cache.put("plan", cache_key_data, plan)

                return plan

            except Exception as e:
                logger.error(f"Error creating plan: {e}", exc_info=True)
                span.record_exception(e)
                # Fallback to simple plan
                return self._create_simple_plan(
                    user_request, available_tools, context, span
                )

    def _create_plan_with_llm(
        self,
        user_request: str,
        available_tools: List[Any],
        context: ConversationContext,
        span: trace.Span,
    ) -> Plan:
        """Create plan using LLM."""
        try:
            # Get analysis from conversation history if available
            analysis = ""
            if context.reasoning_history:
                last_reasoning = context.reasoning_history[-1]
                if hasattr(last_reasoning, "plan") and last_reasoning.plan:
                    # Use previous plan as context
                    analysis = f"Previous plan: {str(last_reasoning.plan)}"

            # Get tool names
            tool_names = [
                tool.name if hasattr(tool, "name") else str(tool)
                for tool in available_tools
            ]

            # Generate plan using LLM
            plan_text = self.llm_client.plan(
                user_request=user_request,
                analysis=analysis or f"Request: {user_request}",
                available_tools=tool_names,
            )

            # Parse plan text into Plan object
            # Supports multiple formats: JSON, markdown lists, numbered lists
            steps = self._parse_plan_text(plan_text, tool_names)

            complexity = self._estimate_complexity(user_request)
            success_criteria = self._define_success_criteria(user_request)

            span.set_attribute("llm_plan_used", True)
            span.set_attribute("plan_text_length", len(plan_text))

            return Plan(
                steps=steps,
                estimated_complexity=complexity,
                success_criteria=success_criteria,
                required_tools=tool_names,
            )

        except Exception as e:
            logger.error(f"Error creating plan with LLM: {e}", exc_info=True)
            span.record_exception(e)
            # Fall back to simple planning
            logger.info("LLM planning failed, falling back to simple planning")
            return self._create_simple_plan(
                user_request, available_tools, context, span
            )

    def _parse_plan_text(
        self, plan_text: str, available_tools: List[str]
    ) -> List[Step]:
        """
        Parse LLM-generated plan text into Step objects.

        Supports multiple formats:
        - JSON format: {"steps": [{"description": "...", "tool": "...", "args": {...}}]}
        - Markdown lists: - Step description or * Step description
        - Numbered lists: 1. Step description or Step 1: description
        """
        import json
        import re

        steps = []
        step_id = 1

        # Try to parse as JSON first (most structured format)
        try:
            # Look for JSON in the text (might be wrapped in markdown code blocks)
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", plan_text, re.DOTALL
            )
            if json_match:
                plan_text_json = json_match.group(1)
            else:
                # Try to find JSON object directly
                json_match = re.search(r"\{.*\}", plan_text, re.DOTALL)
                if json_match:
                    plan_text_json = json_match.group(0)
                else:
                    raise ValueError("No JSON found")

            plan_data = json.loads(plan_text_json)

            # Handle different JSON structures
            if isinstance(plan_data, dict):
                if "steps" in plan_data:
                    # Format: {"steps": [{"description": "...", ...}]}
                    plan_steps = plan_data["steps"]
                elif "plan" in plan_data:
                    # Format: {"plan": {"steps": [...]}}
                    plan_steps = plan_data["plan"].get("steps", [])
                else:
                    # Try to use the dict itself as a single step
                    plan_steps = [plan_data]
            elif isinstance(plan_data, list):
                # Format: [{"description": "...", ...}, ...]
                plan_steps = plan_data
            else:
                raise ValueError("Unexpected JSON structure")

            for step_data in plan_steps:
                if isinstance(step_data, dict):
                    description = step_data.get(
                        "description", step_data.get("step", "")
                    )
                    tool_name = step_data.get("tool", step_data.get("tool_name"))
                    tool_args = step_data.get("args", step_data.get("tool_args", {}))
                    expected_output = step_data.get("expected_output")

                    # Validate tool name
                    if tool_name and tool_name not in available_tools:
                        # Try to find matching tool by name similarity
                        for tool in available_tools:
                            if tool.lower() == tool_name.lower():
                                tool_name = tool
                                break
                        else:
                            tool_name = None  # Tool not found, will be None

                    steps.append(
                        Step(
                            step_id=step_id,
                            description=description,
                            tool_name=tool_name,
                            tool_args=tool_args
                            if isinstance(tool_args, dict)
                            else None,
                            expected_output=expected_output,
                        )
                    )
                    step_id += 1

            if steps:
                logger.info(f"Parsed {len(steps)} steps from JSON format")
                return steps
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.debug(f"Failed to parse as JSON: {e}, trying other formats")

        # Try markdown list format: - Step or * Step
        markdown_patterns = [
            r"^[-*]\s+(.+?)(?=\n[-*]|\n\n|$)",
            r"^\s*[-*]\s+(.+?)(?=\n\s*[-*]|\n\n|$)",
        ]

        for pattern in markdown_patterns:
            matches = re.finditer(pattern, plan_text, re.MULTILINE)
            for match in matches:
                description = match.group(1).strip()

                # Try to identify tool from description
                tool_name = None
                tool_args = None
                for tool in available_tools:
                    if tool.lower() in description.lower():
                        tool_name = tool
                        break

                steps.append(
                    Step(
                        step_id=step_id,
                        description=description,
                        tool_name=tool_name,
                        tool_args=tool_args,
                    )
                )
                step_id += 1

            if steps:
                logger.info(f"Parsed {len(steps)} steps from markdown list format")
                return steps

        # Try numbered list format: "1. Step description" or "Step 1: description"
        step_patterns = [
            r"^\s*(\d+)\.\s+(.+?)(?=\n\s*\d+\.|\n\n|$)",
            r"Step\s+(\d+):\s+(.+?)(?=\n\s*Step\s+\d+:|$)",
        ]

        for pattern in step_patterns:
            matches = re.finditer(pattern, plan_text, re.MULTILINE | re.DOTALL)
            for match in matches:
                step_num = int(match.group(1))
                description = match.group(2).strip()

                # Try to identify tool from description
                tool_name = None
                tool_args = None
                for tool in available_tools:
                    if tool.lower() in description.lower():
                        tool_name = tool
                        break

                steps.append(
                    Step(
                        step_id=step_id,
                        description=description,
                        tool_name=tool_name,
                        tool_args=tool_args,
                    )
                )
                step_id += 1

            if steps:
                logger.info(f"Parsed {len(steps)} steps from numbered list format")
                return steps

        # If no steps found, create a single step from the plan text
        if not steps:
            logger.warning(
                "Could not parse plan text, creating single step from full text"
            )
            steps.append(
                Step(
                    step_id=1,
                    description=plan_text[:200] + "..."
                    if len(plan_text) > 200
                    else plan_text,
                )
            )

        return steps

    def _create_simple_plan(
        self,
        user_request: str,
        available_tools: List[Any],
        context: ConversationContext,
        span: trace.Span,
    ) -> Plan:
        """Create a simple plan without LLM assistance."""
        # Analyze request to determine complexity
        complexity = self._estimate_complexity(user_request)

        # Identify required tools
        required_tools = self._identify_tools(user_request, available_tools)

        # Create steps based on request
        steps = self._create_steps(user_request, required_tools)

        # Limit steps to max_steps
        if len(steps) > self.max_steps:
            logger.warning(f"Plan has {len(steps)} steps, limiting to {self.max_steps}")
            steps = steps[: self.max_steps]

        # Define success criteria
        success_criteria = self._define_success_criteria(user_request)

        span.set_attribute("complexity", complexity)
        span.set_attribute("steps_count", len(steps))
        span.set_attribute("required_tools_count", len(required_tools))

        return Plan(
            steps=steps,
            estimated_complexity=complexity,
            success_criteria=success_criteria,
            required_tools=[
                tool.name if hasattr(tool, "name") else str(tool)
                for tool in required_tools
            ],
        )

    def _estimate_complexity(self, user_request: str) -> str:
        """Estimate the complexity of a request."""
        request_lower = user_request.lower()

        # Count complexity indicators
        complex_keywords = [
            "multiple",
            "several",
            "complex",
            "advanced",
            "sophisticated",
        ]
        moderate_keywords = ["create", "modify", "update", "analyze", "process"]

        complex_count = sum(
            1 for keyword in complex_keywords if keyword in request_lower
        )
        moderate_count = sum(
            1 for keyword in moderate_keywords if keyword in request_lower
        )

        if complex_count >= 2 or len(user_request) > 500:
            return "complex"
        elif moderate_count >= 1 or len(user_request) > 200:
            return "moderate"
        else:
            return "simple"

    def _identify_tools(
        self, user_request: str, available_tools: List[Any]
    ) -> List[Any]:
        """Identify which tools are needed for the request."""
        request_lower = user_request.lower()
        required_tools = []

        # Simple keyword-based tool identification
        tool_keywords = {
            "file": ["read", "write", "create", "delete", "file", "directory"],
            "code": ["code", "function", "class", "implement", "write code"],
            "execute": ["run", "execute", "test", "execute code"],
        }

        for tool in available_tools:
            tool_name = tool.name if hasattr(tool, "name") else str(tool).lower()

            # Check if request mentions tool-related keywords
            for category, keywords in tool_keywords.items():
                if category in tool_name or any(kw in request_lower for kw in keywords):
                    if tool not in required_tools:
                        required_tools.append(tool)
                        break

        return required_tools

    def _create_steps(self, user_request: str, required_tools: List[Any]) -> List[Step]:
        """Create execution steps from the request."""
        steps = []

        # Simple step creation: break request into logical parts
        # For now, create a single step
        # TODO: Implement more sophisticated step breakdown

        step_description = user_request
        tool_name = None
        tool_args = None

        # Try to extract tool information
        if required_tools:
            tool = required_tools[0]
            tool_name = tool.name if hasattr(tool, "name") else str(tool)
            # Try to extract arguments from request
            tool_args = self._extract_tool_args(user_request, tool)

        steps.append(
            Step(
                step_id=1,
                description=step_description,
                tool_name=tool_name,
                tool_args=tool_args,
            )
        )

        return steps

    def _extract_tool_args(
        self, user_request: str, tool: Any
    ) -> Optional[Dict[str, Any]]:
        """Extract tool arguments from the request."""
        # Simple extraction: look for common patterns
        # TODO: Implement more sophisticated argument extraction

        args = {}

        # Look for file paths
        if "file" in user_request.lower():
            # Try to find file path patterns
            import re

            file_patterns = [
                r'["\']([^"\']+\.(py|txt|md|json|yaml|yml))["\']',
                r"([a-zA-Z0-9_/]+\.(py|txt|md|json|yaml|yml))",
            ]
            for pattern in file_patterns:
                matches = re.findall(pattern, user_request)
                if matches:
                    args["file_path"] = (
                        matches[0][0] if isinstance(matches[0], tuple) else matches[0]
                    )
                    break

        return args if args else None

    def _define_success_criteria(self, user_request: str) -> List[str]:
        """Define success criteria for the plan."""
        criteria = []

        # Basic success criteria
        if "create" in user_request.lower():
            criteria.append("Created successfully")
        if "modify" in user_request.lower() or "update" in user_request.lower():
            criteria.append("Modified successfully")
        if "execute" in user_request.lower() or "run" in user_request.lower():
            criteria.append("Executed successfully")

        # Default criterion
        if not criteria:
            criteria.append("Request completed successfully")

        return criteria
