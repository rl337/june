"""
Reflection Component

Evaluates execution results and determines if goals were achieved.
"""
import logging
from typing import Optional, List
from essence.agents.reasoning import Plan, ExecutionResult, ReflectionResult, ConversationContext
from essence.chat.utils.tracing import get_tracer
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class Reflector:
    """
    Evaluates execution results and determines next steps.
    
    Analyzes whether goals were achieved, identifies issues, and suggests plan adjustments.
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        min_confidence: float = 0.7,
    ):
        """
        Initialize the reflector.
        
        Args:
            llm_client: LLM client for reflection (optional)
            min_confidence: Minimum confidence threshold for goal achievement
        """
        self.llm_client = llm_client
        self.min_confidence = min_confidence
    
    def reflect(
        self,
        plan: Optional[Plan],
        execution_results: List[ExecutionResult],
        original_request: str,
    ) -> ReflectionResult:
        """
        Evaluate execution results and determine if goals were achieved.
        
        Args:
            plan: The execution plan that was executed
            execution_results: Results from executing the plan
            original_request: The original user request
            
        Returns:
            ReflectionResult with goal achievement status, issues, and next steps
        """
        with tracer.start_as_current_span("reflector.reflect") as span:
            try:
                span.set_attribute("plan_steps", len(plan.steps) if plan else 0)
                span.set_attribute("execution_results_count", len(execution_results))
                
                # If LLM client is available, use it for reflection
                if self.llm_client:
                    return self._reflect_with_llm(plan, execution_results, original_request, span)
                else:
                    return self._reflect_simple(plan, execution_results, original_request, span)
            
            except Exception as e:
                logger.error(f"Error in reflection: {e}", exc_info=True)
                span.record_exception(e)
                # Fallback to simple reflection
                return self._reflect_simple(plan, execution_results, original_request, span)
    
    def _reflect_with_llm(
        self,
        plan: Optional[Plan],
        execution_results: List[ExecutionResult],
        original_request: str,
        span: trace.Span,
    ) -> ReflectionResult:
        """Reflect using LLM (to be implemented)."""
        # TODO: Implement LLM-based reflection
        # For now, fall back to simple reflection
        logger.info("LLM-based reflection not yet implemented, using simple reflection")
        return self._reflect_simple(plan, execution_results, original_request, span)
    
    def _reflect_simple(
        self,
        plan: Optional[Plan],
        execution_results: List[ExecutionResult],
        original_request: str,
        span: trace.Span,
    ) -> ReflectionResult:
        """Simple reflection without LLM assistance."""
        # Analyze execution results
        successful_results = [r for r in execution_results if r.success]
        failed_results = [r for r in execution_results if not r.success]
        
        # Determine if goal was achieved
        goal_achieved = self._evaluate_goal_achievement(
            plan,
            successful_results,
            failed_results,
            original_request,
        )
        
        # Identify issues
        issues_found = []
        for result in failed_results:
            if result.error:
                issues_found.append(f"Step {result.step_id}: {result.error}")
        
        # Calculate confidence
        if execution_results:
            success_rate = len(successful_results) / len(execution_results)
            confidence = success_rate if goal_achieved else success_rate * 0.5
        else:
            confidence = 0.0
        
        # Determine if we should continue
        should_continue = not goal_achieved and len(failed_results) < len(execution_results)
        
        # Generate plan adjustments if needed
        plan_adjustments = None
        if not goal_achieved and failed_results:
            plan_adjustments = self._suggest_plan_adjustments(plan, failed_results)
        
        # Generate final response
        final_response = self._generate_response(
            plan,
            successful_results,
            failed_results,
            goal_achieved,
        )
        
        span.set_attribute("goal_achieved", goal_achieved)
        span.set_attribute("confidence", confidence)
        span.set_attribute("issues_count", len(issues_found))
        span.set_attribute("should_continue", should_continue)
        
        return ReflectionResult(
            goal_achieved=goal_achieved,
            issues_found=issues_found,
            plan_adjustments=plan_adjustments,
            should_continue=should_continue,
            final_response=final_response,
            confidence=confidence,
        )
    
    def _evaluate_goal_achievement(
        self,
        plan: Optional[Plan],
        successful_results: List[ExecutionResult],
        failed_results: List[ExecutionResult],
        original_request: str,
    ) -> bool:
        """Evaluate if the goal was achieved."""
        if not plan:
            # No plan means we can't evaluate
            return len(failed_results) == 0
        
        # Check if all steps succeeded
        if len(failed_results) == 0:
            return True
        
        # Check success criteria
        if plan.success_criteria:
            # Simple check: if most steps succeeded, consider goal achieved
            total_steps = len(successful_results) + len(failed_results)
            if total_steps > 0:
                success_rate = len(successful_results) / total_steps
                return success_rate >= self.min_confidence
        
        # Default: goal achieved if no failures
        return len(failed_results) == 0
    
    def _suggest_plan_adjustments(
        self,
        plan: Optional[Plan],
        failed_results: List[ExecutionResult],
    ) -> Optional[Plan]:
        """Suggest adjustments to the plan based on failures."""
        if not plan or not failed_results:
            return None
        
        # Simple adjustment: retry failed steps
        # TODO: Implement more sophisticated plan adjustments
        
        # For now, return None (no adjustments)
        # In a real system, this would create a new plan that addresses the failures
        return None
    
    def _generate_response(
        self,
        plan: Optional[Plan],
        successful_results: List[ExecutionResult],
        failed_results: List[ExecutionResult],
        goal_achieved: bool,
    ) -> str:
        """Generate a response based on execution results."""
        response_parts = []
        
        if goal_achieved:
            response_parts.append("✓ Successfully completed your request.")
            
            if successful_results:
                response_parts.append("\nCompleted steps:")
                for result in successful_results:
                    response_parts.append(f"  • {result.output}")
        else:
            response_parts.append("⚠ Partially completed your request.")
            
            if successful_results:
                response_parts.append("\nCompleted steps:")
                for result in successful_results:
                    response_parts.append(f"  • {result.output}")
            
            if failed_results:
                response_parts.append("\nIssues encountered:")
                for result in failed_results:
                    response_parts.append(f"  • Step {result.step_id}: {result.error}")
        
        return "\n".join(response_parts)
