"""Agent monitoring and activity tracking for June.

Provides monitoring capabilities including activity logging, health monitoring,
performance metrics, and alerting.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from june_agent_state.models import (
    AgentExecutionOutcome,
    AgentExecutionRecord,
    AgentStatus,
)
from june_agent_state.registry import AgentRegistry
from june_agent_state.storage import AgentStateStorage

logger = logging.getLogger(__name__)


class AgentMonitor:
    """Monitors agent activity, health, and performance."""

    def __init__(self, registry: AgentRegistry, storage: AgentStateStorage):
        """
        Initialize agent monitor.

        Args:
            registry: AgentRegistry instance
            storage: AgentStateStorage instance
        """
        self.registry = registry
        self.storage = storage

    async def log_agent_activity(
        self,
        agent_id: str,
        action_type: str,
        task_id: Optional[str] = None,
        outcome: Optional[AgentExecutionOutcome] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Log an agent activity/action.

        Args:
            agent_id: Agent ID
            action_type: Type of action (e.g., 'task_started', 'task_completed', 'tool_used')
            task_id: Optional task ID
            outcome: Optional execution outcome
            duration_ms: Optional duration in milliseconds
            metadata: Optional additional metadata

        Returns:
            True if logged successfully, False otherwise
        """
        try:
            record = AgentExecutionRecord(
                agent_id=agent_id,
                task_id=task_id,
                action_type=action_type,
                outcome=outcome,
                duration_ms=duration_ms,
                metadata=metadata or {},
                created_at=datetime.utcnow(),
            )
            await self.storage.save_execution_record(record)
            logger.debug(f"Logged activity for agent {agent_id}: {action_type}")
            return True
        except Exception as e:
            logger.error(
                f"Error logging activity for agent {agent_id}: {e}", exc_info=True
            )
            return False

    async def get_agent_activity(
        self,
        agent_id: str,
        time_range: Optional[timedelta] = None,
        action_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get agent activity within a time range.

        Args:
            agent_id: Agent ID
            time_range: Optional time range (default: last 24 hours)
            action_types: Optional filter by action types
            limit: Maximum number of records to return

        Returns:
            List of activity records
        """
        try:
            if time_range is None:
                time_range = timedelta(hours=24)

            start_time = datetime.utcnow() - time_range

            records = await self.storage.query_execution_history(
                agent_id=agent_id,
                start_time=start_time,
                limit=limit,
            )

            # Filter by action types if provided
            if action_types:
                records = [r for r in records if r.action_type in action_types]

            return [
                {
                    "agent_id": r.agent_id,
                    "task_id": r.task_id,
                    "action_type": r.action_type,
                    "outcome": r.outcome.value if r.outcome else None,
                    "duration_ms": r.duration_ms,
                    "metadata": r.metadata,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
        except Exception as e:
            logger.error(
                f"Error getting activity for agent {agent_id}: {e}", exc_info=True
            )
            return []

    async def get_agent_metrics(self, agent_id: str) -> Dict[str, Any]:
        """
        Get performance metrics for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Dictionary with metrics (tasks_completed, success_rate, avg_execution_time, etc.)
        """
        try:
            agent_state = await self.registry.get_agent(agent_id)
            if agent_state is None:
                return {}

            metrics = agent_state.metrics

            # Calculate additional metrics from execution history
            time_range = timedelta(days=7)  # Last 7 days
            start_time = datetime.utcnow() - time_range
            records = await self.storage.list_execution_history(
                agent_id=agent_id,
                start_time=start_time,
                limit=1000,
            )

            # Calculate metrics from history
            task_records = [r for r in records if r.task_id is not None]
            completed_tasks = [
                r
                for r in task_records
                if r.action_type == "task_completed"
                and r.outcome == AgentExecutionOutcome.SUCCESS
            ]
            failed_tasks = [
                r
                for r in task_records
                if r.action_type == "task_completed"
                and r.outcome == AgentExecutionOutcome.FAILURE
            ]

            total_tasks = len(completed_tasks) + len(failed_tasks)
            success_rate = (
                len(completed_tasks) / total_tasks if total_tasks > 0 else 0.0
            )

            durations = [
                r.duration_ms / 1000.0
                for r in completed_tasks
                if r.duration_ms is not None
            ]
            avg_execution_time = (
                sum(durations) / len(durations) if durations else 0.0
            )

            return {
                "agent_id": agent_id,
                "status": agent_state.status.value,
                "current_task_id": agent_state.current_task_id,
                "tasks_completed": metrics.tasks_completed,
                "tasks_failed": metrics.tasks_failed,
                "success_rate": metrics.success_rate,
                "avg_execution_time_seconds": metrics.avg_execution_time,
                "total_execution_time_seconds": metrics.total_execution_time,
                # Recent metrics (last 7 days)
                "recent_tasks_completed": len(completed_tasks),
                "recent_tasks_failed": len(failed_tasks),
                "recent_success_rate": success_rate,
                "recent_avg_execution_time_seconds": avg_execution_time,
                "last_activity": records[0].created_at.isoformat() if records else None,
            }
        except Exception as e:
            logger.error(
                f"Error getting metrics for agent {agent_id}: {e}", exc_info=True
            )
            return {}

    async def get_agent_health(self, agent_id: str) -> Dict[str, Any]:
        """
        Get agent health status.

        Args:
            agent_id: Agent ID

        Returns:
            Dictionary with health information
        """
        try:
            agent_state = await self.registry.get_agent(agent_id)
            if agent_state is None:
                return {
                    "agent_id": agent_id,
                    "status": "unknown",
                    "healthy": False,
                    "reason": "Agent not found",
                }

            # Check status
            healthy = agent_state.status in (AgentStatus.ACTIVE, AgentStatus.IDLE)
            status = agent_state.status.value

            # Check recent activity
            time_range = timedelta(hours=1)
            start_time = datetime.utcnow() - time_range
            recent_activity = await self.storage.query_execution_history(
                agent_id=agent_id,
                start_time=start_time,
                limit=10,
            )

            # Check for recent failures
            recent_failures = [
                r
                for r in recent_activity
                if r.outcome == AgentExecutionOutcome.FAILURE
            ]

            # Health check based on status and recent failures
            if agent_state.status == AgentStatus.ERROR:
                healthy = False
                reason = "Agent in ERROR state"
            elif len(recent_failures) > 5:  # More than 5 failures in last hour
                healthy = False
                reason = f"High failure rate: {len(recent_failures)} failures in last hour"
            elif agent_state.status == AgentStatus.IDLE and len(recent_activity) == 0:
                # Agent idle and no activity - might be fine or might be stuck
                healthy = True
                reason = "Agent idle, no recent activity"
            else:
                healthy = True
                reason = "Agent operating normally"

            return {
                "agent_id": agent_id,
                "status": status,
                "healthy": healthy,
                "reason": reason,
                "current_task_id": agent_state.current_task_id,
                "recent_activity_count": len(recent_activity),
                "recent_failures": len(recent_failures),
                "last_activity": (
                    recent_activity[0].created_at.isoformat()
                    if recent_activity
                    else None
                ),
            }
        except Exception as e:
            logger.error(
                f"Error getting health for agent {agent_id}: {e}", exc_info=True
            )
            return {
                "agent_id": agent_id,
                "status": "unknown",
                "healthy": False,
                "reason": f"Error checking health: {str(e)}",
            }

    async def list_all_agent_status(self) -> List[Dict[str, Any]]:
        """
        List status for all agents.

        Returns:
            List of agent status dictionaries
        """
        try:
            agents = await self.registry.list_agents()
            statuses = []

            for agent in agents:
                health = await self.get_agent_health(agent.agent_id)
                metrics = await self.get_agent_metrics(agent.agent_id)

                statuses.append(
                    {
                        "agent_id": agent.agent_id,
                        "status": agent.status.value,
                        "healthy": health.get("healthy", False),
                        "current_task_id": agent.current_task_id,
                        "tasks_completed": metrics.get("tasks_completed", 0),
                        "success_rate": metrics.get("success_rate", 0.0),
                        "last_activity": metrics.get("last_activity"),
                    }
                )

            return statuses
        except Exception as e:
            logger.error(f"Error listing agent status: {e}", exc_info=True)
            return []

    async def check_agent_failures(
        self, time_range: Optional[timedelta] = None
    ) -> List[Dict[str, Any]]:
        """
        Check for agent failures within a time range.

        Args:
            time_range: Optional time range (default: last hour)

        Returns:
            List of failure records
        """
        try:
            if time_range is None:
                time_range = timedelta(hours=1)

            start_time = datetime.utcnow() - time_range

            # Get all agents
            agents = await self.registry.list_agents()
            failures = []

            for agent in agents:
                records = await self.storage.query_execution_history(
                    agent_id=agent.agent_id,
                    start_time=start_time,
                    limit=100,
                )

                # Filter by action types
                records = [
                    r
                    for r in records
                    if r.action_type in ["agent_failure", "task_completed"]
                ]

                failure_records = [
                    r
                    for r in records
                    if r.outcome == AgentExecutionOutcome.FAILURE
                    or r.action_type == "agent_failure"
                ]

                if failure_records:
                    failures.append(
                        {
                            "agent_id": agent.agent_id,
                            "status": agent.status.value,
                            "failures": [
                                {
                                    "action_type": r.action_type,
                                    "task_id": r.task_id,
                                    "metadata": r.metadata,
                                    "created_at": (
                                        r.created_at.isoformat()
                                        if r.created_at
                                        else None
                                    ),
                                }
                                for r in failure_records
                            ],
                        }
                    )

            return failures
        except Exception as e:
            logger.error(f"Error checking agent failures: {e}", exc_info=True)
            return []

    async def alert_on_failures(
        self, threshold: int = 3, time_range: Optional[timedelta] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate alerts for agents with excessive failures.

        Args:
            threshold: Number of failures to trigger alert
            time_range: Optional time range (default: last hour)

        Returns:
            List of alert dictionaries
        """
        try:
            failures = await self.check_agent_failures(time_range=time_range)
            alerts = []

            for failure_info in failures:
                failure_count = len(failure_info["failures"])
                if failure_count >= threshold:
                    alerts.append(
                        {
                            "alert_type": "agent_failure_threshold",
                            "agent_id": failure_info["agent_id"],
                            "status": failure_info["status"],
                            "failure_count": failure_count,
                            "threshold": threshold,
                            "failures": failure_info["failures"],
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

            if alerts:
                logger.warning(
                    f"Generated {len(alerts)} failure alert(s): "
                    f"{', '.join(a['agent_id'] for a in alerts)}"
                )

            return alerts
        except Exception as e:
            logger.error(f"Error generating failure alerts: {e}", exc_info=True)
            return []

    async def track_agent_state_transition(
        self,
        agent_id: str,
        old_status: AgentStatus,
        new_status: AgentStatus,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Track agent state transitions.

        Args:
            agent_id: Agent ID
            old_status: Previous status
            new_status: New status
            reason: Optional reason for transition

        Returns:
            True if tracked successfully, False otherwise
        """
        return await self.log_agent_activity(
            agent_id=agent_id,
            action_type="state_transition",
            task_id=None,
            outcome=None,
            duration_ms=None,
            metadata={
                "old_status": old_status.value,
                "new_status": new_status.value,
                "reason": reason,
            },
        )

    async def get_performance_degradation_alerts(
        self, threshold_decrease: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Generate alerts for agents with performance degradation.

        Args:
            threshold_decrease: Minimum decrease in success rate to trigger alert

        Returns:
            List of performance degradation alerts
        """
        try:
            agents = await self.registry.list_agents()
            alerts = []

            for agent in agents:
                metrics = await self.get_agent_metrics(agent.agent_id)

                # Compare recent vs overall success rate
                overall_success_rate = metrics.get("success_rate", 1.0)
                recent_success_rate = metrics.get("recent_success_rate", 1.0)

                if (
                    overall_success_rate > 0
                    and recent_success_rate
                    < overall_success_rate - threshold_decrease
                ):
                    alerts.append(
                        {
                            "alert_type": "performance_degradation",
                            "agent_id": agent.agent_id,
                            "overall_success_rate": overall_success_rate,
                            "recent_success_rate": recent_success_rate,
                            "degradation": overall_success_rate - recent_success_rate,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

            if alerts:
                logger.warning(
                    f"Generated {len(alerts)} performance degradation alert(s)"
                )

            return alerts
        except Exception as e:
            logger.error(
                f"Error checking performance degradation: {e}", exc_info=True
            )
            return []
