"""
Planning Component

Creates execution plans from user requests by breaking them down into steps.
"""
import logging
from typing import Optional, List, Dict, Any
from essence.agents.reasoning import Plan, Step, ConversationContext
from essence.chat.utils.tracing import get_tracer
from opentelemetry import trace

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
    ):
        """
        Initialize the planner.
        
        Args:
            llm_client: LLM client for generating plans (optional)
            max_steps: Maximum number of steps in a plan
        """
        self.llm_client = llm_client
        self.max_steps = max_steps
    
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
                
                # If LLM client is available, use it for planning
                if self.llm_client:
                    return self._create_plan_with_llm(user_request, available_tools, context, span)
                else:
                    return self._create_simple_plan(user_request, available_tools, context, span)
            
            except Exception as e:
                logger.error(f"Error creating plan: {e}", exc_info=True)
                span.record_exception(e)
                # Fallback to simple plan
                return self._create_simple_plan(user_request, available_tools, context, span)
    
    def _create_plan_with_llm(
        self,
        user_request: str,
        available_tools: List[Any],
        context: ConversationContext,
        span: trace.Span,
    ) -> Plan:
        """Create plan using LLM (to be implemented)."""
        # TODO: Implement LLM-based planning
        # For now, fall back to simple planning
        logger.info("LLM-based planning not yet implemented, using simple planning")
        return self._create_simple_plan(user_request, available_tools, context, span)
    
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
            steps = steps[:self.max_steps]
        
        # Define success criteria
        success_criteria = self._define_success_criteria(user_request)
        
        span.set_attribute("complexity", complexity)
        span.set_attribute("steps_count", len(steps))
        span.set_attribute("required_tools_count", len(required_tools))
        
        return Plan(
            steps=steps,
            estimated_complexity=complexity,
            success_criteria=success_criteria,
            required_tools=[tool.name if hasattr(tool, 'name') else str(tool) for tool in required_tools],
        )
    
    def _estimate_complexity(self, user_request: str) -> str:
        """Estimate the complexity of a request."""
        request_lower = user_request.lower()
        
        # Count complexity indicators
        complex_keywords = ["multiple", "several", "complex", "advanced", "sophisticated"]
        moderate_keywords = ["create", "modify", "update", "analyze", "process"]
        
        complex_count = sum(1 for keyword in complex_keywords if keyword in request_lower)
        moderate_count = sum(1 for keyword in moderate_keywords if keyword in request_lower)
        
        if complex_count >= 2 or len(user_request) > 500:
            return "complex"
        elif moderate_count >= 1 or len(user_request) > 200:
            return "moderate"
        else:
            return "simple"
    
    def _identify_tools(self, user_request: str, available_tools: List[Any]) -> List[Any]:
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
            tool_name = tool.name if hasattr(tool, 'name') else str(tool).lower()
            
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
            tool_name = tool.name if hasattr(tool, 'name') else str(tool)
            # Try to extract arguments from request
            tool_args = self._extract_tool_args(user_request, tool)
        
        steps.append(Step(
            step_id=1,
            description=step_description,
            tool_name=tool_name,
            tool_args=tool_args,
        ))
        
        return steps
    
    def _extract_tool_args(self, user_request: str, tool: Any) -> Optional[Dict[str, Any]]:
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
                r'([a-zA-Z0-9_/]+\.(py|txt|md|json|yaml|yml))',
            ]
            for pattern in file_patterns:
                matches = re.findall(pattern, user_request)
                if matches:
                    args['file_path'] = matches[0][0] if isinstance(matches[0], tuple) else matches[0]
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
