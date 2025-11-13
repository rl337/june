"""
June Agent State - Models and data structures for agent state management.

This package provides data models and persistence for managing agent state, including:
- AgentState: Current state of an agent
- AgentCapabilities: Agent tools and capabilities
- AgentMetrics: Performance metrics
- AgentExecutionRecord: Individual action records
- AgentPlan: Execution plans and strategies
- AgentStateStorage: Persistence layer for agent state
- AgentRegistry: Agent registration and lifecycle management
- AgentCoordination: Coordination mechanisms to prevent conflicts
- AgentMonitor: Monitoring and activity tracking
"""

from june_agent_state.models import (
    AgentCapabilities,
    AgentExecutionOutcome,
    AgentExecutionRecord,
    AgentMetrics,
    AgentPlan,
    AgentState,
    AgentStatus,
)
from june_agent_state.coordination import AgentCoordination
from june_agent_state.learning import (
    AdaptivePlanning,
    AgentLearningSystem,
    FeedbackIntegration,
    KnowledgeSharing,
    LearningMetrics,
    PatternRecognition,
)
from june_agent_state.monitoring import AgentMonitor
from june_agent_state.registry import AgentRegistry
from june_agent_state.storage import AgentStateStorage

__version__ = "0.1.0"

__all__ = [
    "AgentState",
    "AgentStatus",
    "AgentCapabilities",
    "AgentMetrics",
    "AgentExecutionRecord",
    "AgentExecutionOutcome",
    "AgentPlan",
    "AgentStateStorage",
    "AgentRegistry",
    "AgentCoordination",
    "AgentMonitor",
    "AgentLearningSystem",
    "PatternRecognition",
    "KnowledgeSharing",
    "AdaptivePlanning",
    "FeedbackIntegration",
    "LearningMetrics",
]
