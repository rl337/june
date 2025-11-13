"""
Agent learning and improvement system for June.

This module implements a comprehensive learning system that enables agents to:
1. Track experiences and learn from successes/failures
2. Recognize patterns in successful strategies
3. Share knowledge between agents
4. Adapt planning based on past results
5. Integrate feedback from users and code reviews
6. Provide metrics and trend analysis

The system builds on top of the existing agent_state, agent_execution_history,
agent_plans, and agent_knowledge_cache infrastructure.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from june_agent_state.models import (
    AgentExecutionOutcome,
    AgentExecutionRecord,
    AgentPlan,
)
from june_agent_state.storage import AgentStateStorage

logger = logging.getLogger(__name__)


class PatternRecognition:
    """Identifies patterns in successful and failed agent strategies."""

    def __init__(self, storage: AgentStateStorage):
        """Initialize pattern recognition with storage backend."""
        self.storage = storage

    async def identify_successful_patterns(
        self,
        agent_id: Optional[str] = None,
        task_type: Optional[str] = None,
        min_success_rate: float = 0.7,
        min_executions: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Identify successful patterns from execution history.

        Args:
            agent_id: Filter by agent ID (None for all agents)
            task_type: Filter by task type (from metadata)
            min_success_rate: Minimum success rate to consider pattern successful
            min_executions: Minimum number of executions to consider

        Returns:
            List of pattern dictionaries with success metrics
        """
        # Query execution history
        records = await self.storage.query_execution_history(
            agent_id=agent_id, limit=1000
        )

        # Group by action_type and analyze outcomes
        patterns: Dict[str, Dict[str, Any]] = {}
        for record in records:
            if record.outcome is None:
                continue

            # Extract pattern key from action_type and metadata
            pattern_key = self._extract_pattern_key(record, task_type)
            if pattern_key is None:
                continue

            if pattern_key not in patterns:
                patterns[pattern_key] = {
                    "pattern": pattern_key,
                    "total_executions": 0,
                    "successful_executions": 0,
                    "failed_executions": 0,
                    "avg_duration_ms": 0,
                    "total_duration_ms": 0,
                    "metadata_samples": [],
                }

            pattern = patterns[pattern_key]
            pattern["total_executions"] += 1
            pattern["total_duration_ms"] += record.duration_ms or 0

            if record.outcome == AgentExecutionOutcome.SUCCESS:
                pattern["successful_executions"] += 1
            elif record.outcome == AgentExecutionOutcome.FAILURE:
                pattern["failed_executions"] += 1

            # Store sample metadata
            if len(pattern["metadata_samples"]) < 5:
                pattern["metadata_samples"].append(record.metadata)

        # Calculate success rates and filter
        successful_patterns = []
        for pattern_key, pattern in patterns.items():
            if pattern["total_executions"] < min_executions:
                continue

            success_rate = pattern["successful_executions"] / pattern["total_executions"]
            pattern["success_rate"] = success_rate
            pattern["avg_duration_ms"] = (
                pattern["total_duration_ms"] / pattern["total_executions"]
            )

            if success_rate >= min_success_rate:
                successful_patterns.append(pattern)

        # Sort by success rate and execution count
        successful_patterns.sort(
            key=lambda p: (p["success_rate"], p["total_executions"]), reverse=True
        )

        logger.info(
            f"Identified {len(successful_patterns)} successful patterns "
            f"(from {len(patterns)} total patterns)"
        )
        return successful_patterns

    async def identify_failure_patterns(
        self,
        agent_id: Optional[str] = None,
        task_type: Optional[str] = None,
        min_failures: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Identify common failure patterns to avoid.

        Args:
            agent_id: Filter by agent ID (None for all agents)
            task_type: Filter by task type (from metadata)
            min_failures: Minimum number of failures to consider a pattern

        Returns:
            List of failure pattern dictionaries
        """
        records = await self.storage.query_execution_history(
            agent_id=agent_id, limit=1000
        )

        # Group failures by pattern
        failure_patterns: Dict[str, Dict[str, Any]] = {}
        for record in records:
            if record.outcome != AgentExecutionOutcome.FAILURE:
                continue

            pattern_key = self._extract_pattern_key(record, task_type)
            if pattern_key is None:
                continue

            if pattern_key not in failure_patterns:
                failure_patterns[pattern_key] = {
                    "pattern": pattern_key,
                    "failure_count": 0,
                    "failure_samples": [],
                    "common_errors": defaultdict(int),
                }

            pattern = failure_patterns[pattern_key]
            pattern["failure_count"] += 1

            # Extract error information from metadata
            if "error" in record.metadata:
                error_msg = str(record.metadata["error"])
                pattern["common_errors"][error_msg] += 1

            if len(pattern["failure_samples"]) < 5:
                pattern["failure_samples"].append(record.metadata)

        # Filter and format
        significant_failures = []
        for pattern_key, pattern in failure_patterns.items():
            if pattern["failure_count"] < min_failures:
                continue

            # Get top 3 most common errors
            top_errors = sorted(
                pattern["common_errors"].items(), key=lambda x: x[1], reverse=True
            )[:3]
            pattern["top_errors"] = [{"error": err, "count": cnt} for err, cnt in top_errors]

            significant_failures.append(pattern)

        significant_failures.sort(key=lambda p: p["failure_count"], reverse=True)

        logger.info(
            f"Identified {len(significant_failures)} failure patterns "
            f"(from {len(failure_patterns)} total patterns)"
        )
        return significant_failures

    def _extract_pattern_key(
        self, record: AgentExecutionRecord, task_type: Optional[str] = None
    ) -> Optional[str]:
        """Extract a pattern key from an execution record."""
        # Use action_type as base
        key_parts = [record.action_type]

        # Add task type if specified and available
        if task_type:
            if "task_type" in record.metadata:
                if record.metadata["task_type"] != task_type:
                    return None
            key_parts.append(f"task_type:{task_type}")

        # Add tools used if available
        if "tools_used" in record.metadata:
            tools = sorted(record.metadata["tools_used"])
            key_parts.append(f"tools:{','.join(tools)}")

        return "|".join(key_parts)


class KnowledgeSharing:
    """Manages knowledge sharing between agents."""

    def __init__(self, storage: AgentStateStorage):
        """Initialize knowledge sharing with storage backend."""
        self.storage = storage

    async def share_pattern(
        self,
        pattern: Dict[str, Any],
        pattern_type: str = "success",
        shared_by_agent: str = "system",
    ) -> str:
        """
        Share a pattern with all agents.

        Args:
            pattern: Pattern dictionary to share
            pattern_type: Type of pattern ('success', 'failure', 'strategy')
            shared_by_agent: Agent ID that discovered the pattern

        Returns:
            Knowledge key for the shared pattern
        """
        knowledge_key = f"shared_pattern:{pattern_type}:{pattern.get('pattern', 'unknown')}"

        knowledge_value = {
            "pattern": pattern,
            "pattern_type": pattern_type,
            "shared_by": shared_by_agent,
            "shared_at": datetime.now().isoformat(),
            "access_count": 0,
        }

        # Store in knowledge cache for a special "shared" agent ID
        # All agents can access this by querying with agent_id="shared"
        await self.storage.save_knowledge("shared", knowledge_key, knowledge_value)

        logger.info(
            f"Shared {pattern_type} pattern '{pattern.get('pattern')}' "
            f"by agent {shared_by_agent}"
        )
        return knowledge_key

    async def get_shared_patterns(
        self,
        pattern_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get shared patterns from the knowledge base.

        Args:
            pattern_type: Filter by pattern type (None for all)
            limit: Maximum number of patterns to return

        Returns:
            List of shared pattern dictionaries
        """
        # Query shared knowledge cache
        # Note: This requires a method to list knowledge keys, which we'll implement
        # For now, we'll use a convention-based approach
        patterns = []

        # In a full implementation, we'd query all knowledge keys starting with "shared_pattern:"
        # For now, return empty list - this would be enhanced with a list_knowledge_keys method
        logger.debug(f"Retrieved {len(patterns)} shared patterns")
        return patterns

    async def share_solution(
        self,
        problem: str,
        solution: Dict[str, Any],
        shared_by_agent: str = "system",
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Share a solution to a common problem.

        Args:
            problem: Description of the problem
            solution: Solution dictionary
            shared_by_agent: Agent ID that discovered the solution
            tags: Optional tags for categorization

        Returns:
            Knowledge key for the shared solution
        """
        knowledge_key = f"shared_solution:{problem.lower().replace(' ', '_')}"

        knowledge_value = {
            "problem": problem,
            "solution": solution,
            "shared_by": shared_by_agent,
            "shared_at": datetime.now().isoformat(),
            "tags": tags or [],
            "access_count": 0,
        }

        await self.storage.save_knowledge("shared", knowledge_key, knowledge_value)

        logger.info(f"Shared solution for '{problem}' by agent {shared_by_agent}")
        return knowledge_key

    async def find_similar_solutions(
        self, problem: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find similar solutions to a problem.

        Args:
            problem: Problem description
            limit: Maximum number of solutions to return

        Returns:
            List of similar solution dictionaries
        """
        # In a full implementation, this would use semantic search or keyword matching
        # For now, return empty list
        return []


class AdaptivePlanning:
    """Improves planning based on past execution results."""

    def __init__(self, storage: AgentStateStorage):
        """Initialize adaptive planning with storage backend."""
        self.storage = storage

    async def get_optimal_plan(
        self,
        task_id: str,
        task_type: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the optimal plan for a task based on past results.

        Args:
            task_id: Task ID (may be used for similar task matching)
            task_type: Task type for filtering
            agent_id: Agent ID (None for any agent)

        Returns:
            Optimal plan dictionary or None if no suitable plan found
        """
        # Query plans with high success rates
        plans = await self.storage.query_plans(
            agent_id=agent_id,
            task_id=task_id,
            min_success_rate=0.6,
            limit=10,
        )

        if not plans:
            return None

        # Find the plan with highest success rate and sufficient executions
        best_plan = None
        best_score = 0.0

        for plan in plans:
            # Score combines success rate and execution count
            score = plan.success_rate * min(plan.execution_count / 10.0, 1.0)
            if score > best_score:
                best_score = score
                best_plan = plan

        if best_plan:
            logger.info(
                f"Found optimal plan for task {task_id}: "
                f"success_rate={best_plan.success_rate}, "
                f"executions={best_plan.execution_count}"
            )
            # Note: plan_id needs to be retrieved from storage query result
            # For now, return None as we'd need to modify storage to return IDs
            return {
                "plan_id": None,  # Would need plan_id from query_plans result
                "plan_type": best_plan.plan_type,
                "plan_data": best_plan.plan_data,
                "success_rate": best_plan.success_rate,
                "execution_count": best_plan.execution_count,
            }

        return None

    async def update_plan_success(
        self,
        plan_id: str,
        success: bool,
        execution_time: Optional[float] = None,
    ) -> None:
        """
        Update plan success metrics after execution.

        Args:
            plan_id: Plan ID
            success: Whether execution was successful
            execution_time: Execution time in seconds (optional)
        """
        plan = await self.storage.load_plan(plan_id)
        if not plan:
            logger.warning(f"Plan {plan_id} not found for success update")
            return

        # Update plan using increment_execution method
        plan.increment_execution(success)

        # Update in storage
        await self.storage.update_plan(
            plan_id,
            {
                "plan_data": plan.plan_data,
                "success_rate": plan.success_rate,
                "execution_count": plan.execution_count,
            },
        )

        logger.debug(
            f"Updated plan {plan_id}: success={success}, "
            f"new_rate={plan.success_rate}, count={plan.execution_count}"
        )

    async def suggest_plan_improvements(
        self, plan_id: str
    ) -> List[Dict[str, Any]]:
        """
        Suggest improvements to a plan based on execution history.

        Args:
            plan_id: Plan ID to analyze

        Returns:
            List of improvement suggestions
        """
        plan = await self.storage.load_plan(plan_id)
        if not plan:
            return []

        suggestions = []

        # Analyze success rate
        if plan.success_rate < 0.5 and plan.execution_count >= 3:
            suggestions.append(
                {
                    "type": "low_success_rate",
                    "severity": "high",
                    "message": f"Plan has low success rate ({plan.success_rate:.2%}). "
                    "Consider revising strategy.",
                    "current_rate": plan.success_rate,
                }
            )

        # Check execution count
        if plan.execution_count == 0:
            suggestions.append(
                {
                    "type": "untested",
                    "severity": "medium",
                    "message": "Plan has not been executed yet. Test before relying on it.",
                }
            )

        return suggestions

    async def estimate_task_duration(
        self,
        task_type: Optional[str] = None,
        task_complexity: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Estimate task duration based on historical data.

        Args:
            task_type: Task type for filtering
            task_complexity: Task complexity level (optional)

        Returns:
            Duration estimate dictionary with mean, median, min, max
        """
        # Query execution history for similar tasks
        records = await self.storage.query_execution_history(limit=1000)

        # Filter by task type if provided
        if task_type:
            records = [
                r
                for r in records
                if r.metadata.get("task_type") == task_type
            ]

        if not records:
            return None

        # Calculate statistics
        durations = [
            r.duration_ms / 1000.0
            for r in records
            if r.duration_ms is not None and r.outcome == AgentExecutionOutcome.SUCCESS
        ]

        if not durations:
            return None

        durations.sort()
        n = len(durations)

        estimate = {
            "mean": sum(durations) / n,
            "median": durations[n // 2],
            "min": durations[0],
            "max": durations[-1],
            "sample_size": n,
        }

        logger.debug(
            f"Estimated duration for task_type={task_type}: "
            f"mean={estimate['mean']:.2f}s, median={estimate['median']:.2f}s"
        )
        return estimate


class FeedbackIntegration:
    """Integrates feedback from users, code reviews, and test results."""

    def __init__(self, storage: AgentStateStorage):
        """Initialize feedback integration with storage backend."""
        self.storage = storage

    async def record_feedback(
        self,
        agent_id: str,
        task_id: Optional[str],
        feedback_type: str,
        feedback_content: Dict[str, Any],
        source: str = "user",
    ) -> str:
        """
        Record feedback for an agent or task.

        Args:
            agent_id: Agent ID that received feedback
            task_id: Task ID (if feedback is task-specific)
            feedback_type: Type of feedback ('code_review', 'user_feedback', 'test_result')
            feedback_content: Feedback content dictionary
            source: Source of feedback ('user', 'system', 'reviewer')

        Returns:
            Feedback record ID (knowledge key)
        """
        knowledge_key = f"feedback:{agent_id}:{task_id or 'general'}:{datetime.now().isoformat()}"

        feedback_value = {
            "agent_id": agent_id,
            "task_id": task_id,
            "feedback_type": feedback_type,
            "feedback_content": feedback_content,
            "source": source,
            "recorded_at": datetime.now().isoformat(),
        }

        await self.storage.save_knowledge(agent_id, knowledge_key, feedback_value)

        logger.info(
            f"Recorded {feedback_type} feedback for agent {agent_id}, "
            f"task {task_id}, source {source}"
        )
        return knowledge_key

    async def get_feedback_for_agent(
        self, agent_id: str, feedback_type: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get feedback for a specific agent.

        Args:
            agent_id: Agent ID
            feedback_type: Filter by feedback type (None for all)
            limit: Maximum number of feedback records to return

        Returns:
            List of feedback dictionaries
        """
        # In a full implementation, we'd query knowledge cache with prefix "feedback:"
        # For now, return empty list
        return []

    async def apply_feedback_to_plan(
        self, plan_id: str, feedback: Dict[str, Any]
    ) -> bool:
        """
        Apply feedback to improve a plan.

        Args:
            plan_id: Plan ID to update
            feedback: Feedback dictionary

        Returns:
            True if plan was updated, False otherwise
        """
        plan = await self.storage.load_plan(plan_id)
        if not plan:
            return False

        # Extract improvement suggestions from feedback
        if "suggestions" in feedback.get("feedback_content", {}):
            suggestions = feedback["feedback_content"]["suggestions"]
            # Update plan_data with improvements
            if "improvements" not in plan.plan_data:
                plan.plan_data["improvements"] = []
            plan.plan_data["improvements"].extend(suggestions)

            await self.storage.update_plan(plan_id, {"plan_data": plan.plan_data})

            logger.info(f"Applied feedback to plan {plan_id}")
            return True

        return False


class LearningMetrics:
    """Provides metrics and analysis for agent learning."""

    def __init__(self, storage: AgentStateStorage):
        """Initialize learning metrics with storage backend."""
        self.storage = storage

    async def get_agent_learning_stats(
        self,
        agent_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get learning statistics for an agent.

        Args:
            agent_id: Agent ID
            days: Number of days to analyze

        Returns:
            Dictionary with learning statistics
        """
        start_time = datetime.now() - timedelta(days=days)

        # Query execution history
        records = await self.storage.query_execution_history(
            agent_id=agent_id, start_time=start_time, limit=10000
        )

        if not records:
            return {
                "agent_id": agent_id,
                "period_days": days,
                "total_executions": 0,
                "success_rate": 0.0,
                "improvement_trend": "insufficient_data",
            }

        # Calculate metrics
        total = len(records)
        successful = sum(
            1
            for r in records
            if r.outcome == AgentExecutionOutcome.SUCCESS
        )
        failed = sum(
            1
            for r in records
            if r.outcome == AgentExecutionOutcome.FAILURE
        )

        success_rate = successful / total if total > 0 else 0.0

        # Calculate improvement trend (compare first half vs second half)
        if total >= 10:
            midpoint = total // 2
            first_half = records[midpoint:]
            second_half = records[:midpoint]

            first_success = sum(
                1
                for r in first_half
                if r.outcome == AgentExecutionOutcome.SUCCESS
            )
            second_success = sum(
                1
                for r in second_half
                if r.outcome == AgentExecutionOutcome.SUCCESS
            )

            first_rate = first_success / len(first_half) if first_half else 0.0
            second_rate = second_success / len(second_half) if second_half else 0.0

            if second_rate > first_rate + 0.1:
                trend = "improving"
            elif second_rate < first_rate - 0.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        # Get plan statistics
        plans = await self.storage.query_plans(agent_id=agent_id, limit=100)
        avg_plan_success = (
            sum(p.success_rate for p in plans) / len(plans) if plans else 0.0
        )

        stats = {
            "agent_id": agent_id,
            "period_days": days,
            "total_executions": total,
            "successful_executions": successful,
            "failed_executions": failed,
            "success_rate": success_rate,
            "improvement_trend": trend,
            "avg_plan_success_rate": avg_plan_success,
            "total_plans": len(plans),
        }

        logger.debug(f"Calculated learning stats for agent {agent_id}: {stats}")
        return stats

    async def get_learning_trends(
        self,
        agent_id: Optional[str] = None,
        days: int = 90,
        interval_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Get learning trends over time.

        Args:
            agent_id: Agent ID (None for all agents)
            days: Total days to analyze
            interval_days: Interval for each data point

        Returns:
            List of trend data points
        """
        trends = []
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        current_time = start_time
        while current_time < end_time:
            interval_end = min(current_time + timedelta(days=interval_days), end_time)

            records = await self.storage.query_execution_history(
                agent_id=agent_id,
                start_time=current_time,
                end_time=interval_end,
                limit=10000,
            )

            if records:
                successful = sum(
                    1
                    for r in records
                    if r.outcome == AgentExecutionOutcome.SUCCESS
                )
                success_rate = successful / len(records)

                trends.append(
                    {
                        "period_start": current_time.isoformat(),
                        "period_end": interval_end.isoformat(),
                        "total_executions": len(records),
                        "success_rate": success_rate,
                    }
                )

            current_time = interval_end

        return trends

    async def identify_improvement_areas(
        self, agent_id: str
    ) -> List[Dict[str, Any]]:
        """
        Identify areas where an agent can improve.

        Args:
            agent_id: Agent ID

        Returns:
            List of improvement area dictionaries
        """
        # Get failure patterns
        pattern_recognition = PatternRecognition(self.storage)
        failure_patterns = await pattern_recognition.identify_failure_patterns(
            agent_id=agent_id, min_failures=2
        )

        improvement_areas = []
        for pattern in failure_patterns[:5]:  # Top 5 failure patterns
            improvement_areas.append(
                {
                    "area": pattern["pattern"],
                    "failure_count": pattern["failure_count"],
                    "top_errors": pattern.get("top_errors", []),
                    "recommendation": f"Review and improve strategy for: {pattern['pattern']}",
                }
            )

        return improvement_areas


class AgentLearningSystem:
    """
    Comprehensive agent learning and improvement system.

    This class integrates all learning components:
    - Experience tracking
    - Pattern recognition
    - Knowledge sharing
    - Adaptive planning
    - Feedback integration
    - Metrics and analysis
    """

    def __init__(self, storage: AgentStateStorage):
        """Initialize the learning system with storage backend."""
        self.storage = storage
        self.pattern_recognition = PatternRecognition(storage)
        self.knowledge_sharing = KnowledgeSharing(storage)
        self.adaptive_planning = AdaptivePlanning(storage)
        self.feedback_integration = FeedbackIntegration(storage)
        self.metrics = LearningMetrics(storage)

    async def record_experience(
        self,
        agent_id: str,
        task_id: Optional[str],
        action_type: str,
        outcome: AgentExecutionOutcome,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record an agent experience for learning.

        Args:
            agent_id: Agent ID
            task_id: Task ID (optional)
            action_type: Type of action performed
            outcome: Outcome of the action
            duration_ms: Duration in milliseconds (optional)
            metadata: Additional metadata (optional)

        Returns:
            Record ID
        """
        record = AgentExecutionRecord(
            agent_id=agent_id,
            task_id=task_id,
            action_type=action_type,
            outcome=outcome,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        record_id = await self.storage.save_execution_record(record)

        logger.info(
            f"Recorded experience for agent {agent_id}: "
            f"{action_type} -> {outcome.value}"
        )
        return record_id

    async def learn_from_experience(
        self, agent_id: str, days: int = 7
    ) -> Dict[str, Any]:
        """
        Perform learning analysis from recent experiences.

        Args:
            agent_id: Agent ID
            days: Number of days to analyze

        Returns:
            Learning insights dictionary
        """
        start_time = datetime.now() - timedelta(days=days)

        # Get recent execution history
        records = await self.storage.query_execution_history(
            agent_id=agent_id, start_time=start_time, limit=1000
        )

        # Identify patterns
        successful_patterns = await self.pattern_recognition.identify_successful_patterns(
            agent_id=agent_id, min_executions=2
        )
        failure_patterns = await self.pattern_recognition.identify_failure_patterns(
            agent_id=agent_id, min_failures=2
        )

        # Get learning stats
        stats = await self.metrics.get_agent_learning_stats(agent_id, days=days)

        # Get improvement areas
        improvement_areas = await self.metrics.identify_improvement_areas(agent_id)

        insights = {
            "agent_id": agent_id,
            "analysis_period_days": days,
            "total_experiences": len(records),
            "successful_patterns": successful_patterns[:5],  # Top 5
            "failure_patterns": failure_patterns[:5],  # Top 5
            "learning_stats": stats,
            "improvement_areas": improvement_areas,
            "recommendations": self._generate_recommendations(
                successful_patterns, failure_patterns, stats
            ),
        }

        logger.info(
            f"Generated learning insights for agent {agent_id}: "
            f"{len(successful_patterns)} success patterns, "
            f"{len(failure_patterns)} failure patterns"
        )
        return insights

    def _generate_recommendations(
        self,
        successful_patterns: List[Dict[str, Any]],
        failure_patterns: List[Dict[str, Any]],
        stats: Dict[str, Any],
    ) -> List[str]:
        """Generate recommendations based on learning analysis."""
        recommendations = []

        # Recommend reusing successful patterns
        if successful_patterns:
            top_pattern = successful_patterns[0]
            recommendations.append(
                f"Consider reusing pattern '{top_pattern['pattern']}' "
                f"(success rate: {top_pattern['success_rate']:.2%})"
            )

        # Recommend avoiding failure patterns
        if failure_patterns:
            top_failure = failure_patterns[0]
            recommendations.append(
                f"Avoid pattern '{top_failure['pattern']}' "
                f"(failed {top_failure['failure_count']} times)"
            )

        # Recommend based on trends
        if stats.get("improvement_trend") == "declining":
            recommendations.append(
                "Performance is declining. Review recent changes and failure patterns."
            )
        elif stats.get("improvement_trend") == "improving":
            recommendations.append(
                "Performance is improving. Continue using current successful strategies."
            )

        return recommendations
