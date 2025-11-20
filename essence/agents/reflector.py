"""
Reflection Component

Evaluates execution results and determines if goals were achieved.
"""
import logging
from typing import Any, List, Optional

from opentelemetry import trace

from essence.agents.reasoning import (
    ConversationContext,
    ExecutionResult,
    Plan,
    ReflectionResult,
    Step,
)
from essence.agents.reasoning_cache import ReasoningCache, get_reasoning_cache
from essence.chat.utils.tracing import get_tracer

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
        cache: Optional[ReasoningCache] = None,
        enable_cache: bool = True,
    ):
        """
        Initialize the reflector.

        Args:
            llm_client: LLM client for reflection (optional)
            min_confidence: Minimum confidence threshold for goal achievement
            cache: Reasoning cache instance (optional, uses global cache if None)
            enable_cache: Whether to enable caching
        """
        self.llm_client = llm_client
        self.min_confidence = min_confidence
        self.cache = cache or (get_reasoning_cache() if enable_cache else None)
        self.enable_cache = enable_cache

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

                # Check cache first (for similar execution patterns)
                if self.cache:
                    cache_key_data = {
                        "request": original_request,
                        "results_summary": [
                            {"success": r.success, "step_id": r.step_id}
                            for r in execution_results
                        ],
                    }
                    cached_reflection = self.cache.get("reflect", cache_key_data)
                    if cached_reflection:
                        span.set_attribute("cache_hit", True)
                        logger.debug("Using cached reflection")
                        return cached_reflection
                    span.set_attribute("cache_hit", False)

                # Generate reflection
                if self.llm_client:
                    reflection = self._reflect_with_llm(
                        plan, execution_results, original_request, span
                    )
                else:
                    reflection = self._reflect_simple(
                        plan, execution_results, original_request, span
                    )

                # Cache the reflection
                if self.cache and reflection:
                    cache_key_data = {
                        "request": original_request,
                        "results_summary": [
                            {"success": r.success, "step_id": r.step_id}
                            for r in execution_results
                        ],
                    }
                    self.cache.put("reflect", cache_key_data, reflection)

                return reflection

            except Exception as e:
                logger.error(f"Error in reflection: {e}", exc_info=True)
                span.record_exception(e)
                # Fallback to simple reflection
                return self._reflect_simple(
                    plan, execution_results, original_request, span
                )

    def _reflect_with_llm(
        self,
        plan: Optional[Plan],
        execution_results: List[ExecutionResult],
        original_request: str,
        span: trace.Span,
    ) -> ReflectionResult:
        """Reflect using LLM."""
        try:
            # Convert plan to string
            plan_text = str(plan) if plan else "No plan available"

            # Convert execution results to dict format
            results_dict = [
                {
                    "success": r.success,
                    "output": str(r.output) if r.output else "No output",
                    "error": r.error,
                    "step_id": r.step_id,
                }
                for r in execution_results
            ]

            # Generate reflection using LLM
            reflection_text = self.llm_client.reflect(
                original_request=original_request,
                plan=plan_text,
                execution_results=results_dict,
            )

            # Parse reflection text to extract key information
            goal_achieved = self._parse_goal_achievement(reflection_text)
            issues_found = self._parse_issues(reflection_text)
            should_continue = self._parse_should_continue(reflection_text)
            confidence = self._parse_confidence(reflection_text)

            # Generate plan adjustments if needed
            plan_adjustments = None
            if not goal_achieved and should_continue and self.llm_client:
                plan_adjustments = self._generate_plan_adjustments(
                    plan, reflection_text, issues_found, original_request, span
                )

            span.set_attribute("llm_reflection_used", True)
            span.set_attribute("reflection_text_length", len(reflection_text))

            return ReflectionResult(
                goal_achieved=goal_achieved,
                issues_found=issues_found,
                plan_adjustments=plan_adjustments,
                should_continue=should_continue,
                final_response=reflection_text,
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"Error reflecting with LLM: {e}", exc_info=True)
            span.record_exception(e)
            # Fall back to simple reflection
            logger.info("LLM reflection failed, falling back to simple reflection")
            return self._reflect_simple(plan, execution_results, original_request, span)

    def _parse_goal_achievement(self, reflection_text: str) -> bool:
        """Parse goal achievement status from reflection text."""
        text_lower = reflection_text.lower()
        positive_indicators = [
            "goal achieved",
            "successfully completed",
            "task completed",
            "done",
            "finished",
        ]
        negative_indicators = [
            "goal not achieved",
            "failed",
            "error",
            "issue",
            "problem",
        ]

        positive_count = sum(
            1 for indicator in positive_indicators if indicator in text_lower
        )
        negative_count = sum(
            1 for indicator in negative_indicators if indicator in text_lower
        )

        return positive_count > negative_count

    def _parse_issues(self, reflection_text: str) -> List[str]:
        """Parse issues from reflection text."""
        import re

        issues = []

        # Look for issue patterns
        issue_patterns = [
            r"issue[s]?:\s*(.+?)(?=\n|$)",
            r"error[s]?:\s*(.+?)(?=\n|$)",
            r"problem[s]?:\s*(.+?)(?=\n|$)",
        ]

        for pattern in issue_patterns:
            matches = re.finditer(
                pattern, reflection_text, re.IGNORECASE | re.MULTILINE
            )
            for match in matches:
                issue = match.group(1).strip()
                if issue and issue not in issues:
                    issues.append(issue)

        return issues

    def _parse_should_continue(self, reflection_text: str) -> bool:
        """Parse whether to continue from reflection text."""
        text_lower = reflection_text.lower()
        continue_indicators = ["should continue", "retry", "adjust", "fix", "try again"]
        stop_indicators = ["complete", "finished", "done", "successful"]

        continue_count = sum(
            1 for indicator in continue_indicators if indicator in text_lower
        )
        stop_count = sum(1 for indicator in stop_indicators if indicator in text_lower)

        return continue_count > stop_count

    def _parse_confidence(self, reflection_text: str) -> float:
        """Parse confidence level from reflection text."""
        import re

        # Look for confidence indicators
        confidence_patterns = [
            r"confidence[:\s]+(\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s*%",
        ]

        for pattern in confidence_patterns:
            match = re.search(pattern, reflection_text, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                # Normalize to 0.0-1.0 range
                if value > 1.0:
                    value = value / 100.0
                return min(max(value, 0.0), 1.0)

        # Default confidence based on keywords
        text_lower = reflection_text.lower()
        if any(
            word in text_lower
            for word in ["high confidence", "very confident", "certain"]
        ):
            return 0.9
        elif any(
            word in text_lower for word in ["low confidence", "uncertain", "unsure"]
        ):
            return 0.3
        else:
            return 0.7

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
        should_continue = not goal_achieved and len(failed_results) < len(
            execution_results
        )

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

    def _generate_plan_adjustments(
        self,
        plan: Optional[Plan],
        reflection_text: str,
        issues_found: List[str],
        original_request: str,
        span: trace.Span,
    ) -> Optional[Plan]:
        """
        Generate plan adjustments from LLM reflection.

        Creates a new plan that addresses the issues found during reflection.
        """
        if not plan or not self.llm_client:
            return None

        try:
            # Prepare context for plan adjustment
            plan_summary = str(plan) if plan else "No previous plan"
            issues_summary = (
                "\n".join(f"- {issue}" for issue in issues_found)
                if issues_found
                else "No specific issues identified"
            )

            # Use LLM to generate an adjusted plan
            # We'll use the plan method but with adjusted context
            analysis = f"""Previous plan that didn't fully achieve the goal:
{plan_summary}

Issues encountered:
{issues_summary}

Reflection:
{reflection_text}

Please create an adjusted plan that addresses these issues and better achieves the original goal: {original_request}"""

            available_tools = plan.required_tools if plan else []

            adjusted_plan_text = self.llm_client.plan(
                user_request=original_request,
                analysis=analysis,
                available_tools=available_tools,
            )

            # Parse the adjusted plan text into Steps
            steps = self._parse_plan_text(adjusted_plan_text, available_tools)

            if not steps:
                logger.warning("Failed to parse adjusted plan from LLM response")
                return None

            # Create adjusted plan
            adjusted_plan = Plan(
                steps=steps,
                estimated_complexity=plan.estimated_complexity if plan else "moderate",
                success_criteria=plan.success_criteria if plan else [],
                required_tools=available_tools,
            )

            span.set_attribute("plan_adjustments_generated", True)
            span.set_attribute("adjusted_plan_steps", len(steps))
            logger.info(f"Generated adjusted plan with {len(steps)} steps")

            return adjusted_plan

        except Exception as e:
            logger.error(f"Error generating plan adjustments: {e}", exc_info=True)
            span.record_exception(e)
            return None

    def _parse_plan_text(
        self, plan_text: str, available_tools: List[str]
    ) -> List[Step]:
        """Parse LLM-generated plan text into Step objects."""
        import re

        steps = []
        step_id = 1

        # Try to extract numbered steps from plan text
        # Pattern: "1. Step description" or "Step 1: description"
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

        # If no steps found, create a single step from the plan text
        if not steps:
            steps.append(
                Step(
                    step_id=1,
                    description=plan_text[:200] + "..."
                    if len(plan_text) > 200
                    else plan_text,
                )
            )

        return steps

    def _suggest_plan_adjustments(
        self,
        plan: Optional[Plan],
        failed_results: List[ExecutionResult],
    ) -> Optional[Plan]:
        """
        Suggest adjustments to the plan based on failures.

        This is a fallback method used when LLM is not available.
        Creates a simple adjusted plan that retries failed steps.
        """
        if not plan or not failed_results:
            return None

        # Simple adjustment: create a new plan that retries failed steps
        # Extract failed step IDs
        failed_step_ids = {result.step_id for result in failed_results}

        # Find the corresponding steps in the original plan
        steps_to_retry = [
            step for step in plan.steps if step.step_id in failed_step_ids
        ]

        if not steps_to_retry:
            return None

        # Create adjusted plan with retry steps
        # Re-number the steps starting from 1
        adjusted_steps = []
        for idx, step in enumerate(steps_to_retry, start=1):
            adjusted_steps.append(
                Step(
                    step_id=idx,
                    description=f"Retry: {step.description}",
                    tool_name=step.tool_name,
                    tool_args=step.tool_args,
                    dependencies=step.dependencies,  # Preserve dependencies
                )
            )

        if adjusted_steps:
            from essence.agents.reasoning import Plan

            adjusted_plan = Plan(steps=adjusted_steps)
            logger.info(f"Created adjusted plan with {len(adjusted_steps)} retry steps")
            return adjusted_plan

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
