"""Base agent interface for switchboard agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, AsyncIterator
from datetime import datetime


class AgentStatus(Enum):
    """Agent execution status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentRequest:
    """Request to execute an agent."""
    agent_id: str
    session_id: str
    message: str
    context: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AgentResponse:
    """Response from agent execution."""
    request_id: str
    agent_id: str
    session_id: str
    status: AgentStatus
    message: str
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class Agent(ABC):
    """Abstract base class for all agent types."""
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """Initialize agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            config: Agent-specific configuration
        """
        self.agent_id = agent_id
        self.config = config
        self.status = AgentStatus.IDLE
    
    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Return the type identifier for this agent."""
        pass
    
    @abstractmethod
    async def execute(
        self,
        request: AgentRequest
    ) -> AsyncIterator[AgentResponse]:
        """Execute the agent with the given request.
        
        This method should stream responses as the agent executes,
        yielding intermediate updates and a final response.
        
        Args:
            request: The agent request to execute
            
        Yields:
            AgentResponse objects with status updates and results
            
        Raises:
            AgentError: If execution fails
        """
        pass
    
    @abstractmethod
    async def cancel(self, request_id: str) -> bool:
        """Cancel a running agent execution.
        
        Args:
            request_id: The request ID to cancel
            
        Returns:
            True if cancellation was successful
        """
        pass
    
    @abstractmethod
    async def get_status(self, request_id: str) -> Optional[AgentResponse]:
        """Get the current status of an execution.
        
        Args:
            request_id: The request ID to check
            
        Returns:
            AgentResponse if found, None otherwise
        """
        pass
    
    def validate_request(self, request: AgentRequest) -> tuple[bool, Optional[str]]:
        """Validate a request before execution.
        
        Args:
            request: The request to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not request.agent_id:
            return False, "agent_id is required"
        if not request.session_id:
            return False, "session_id is required"
        if not request.message:
            return False, "message is required"
        return True, None

