"""Agent registry for managing agent instances."""

import logging
from pathlib import Path
from typing import Dict, Optional, Type
from datetime import datetime

from switchboard.agents.base import Agent
from switchboard.agents.popen_cursor import PopenCursorAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry for managing agent instances."""
    
    # Map of agent type to agent class
    _agent_classes: Dict[str, Type[Agent]] = {
        "popen_cursor": PopenCursorAgent,
    }
    
    def __init__(self):
        """Initialize agent registry."""
        self._agents: Dict[str, Agent] = {}
    
    def register_agent_type(self, agent_type: str, agent_class: Type[Agent]):
        """Register a new agent type.
        
        Args:
            agent_type: Type identifier
            agent_class: Agent class
        """
        self._agent_classes[agent_type] = agent_class
        logger.info(f"Registered agent type: {agent_type}")
    
    def create_agent(
        self,
        agent_id: str,
        agent_type: str,
        config: Dict
    ) -> Agent:
        """Create a new agent instance.
        
        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent to create
            config: Agent configuration
            
        Returns:
            Agent instance
            
        Raises:
            ValueError: If agent type is not registered
        """
        if agent_type not in self._agent_classes:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        agent_class = self._agent_classes[agent_type]
        agent = agent_class(agent_id=agent_id, config=config)
        self._agents[agent_id] = agent
        logger.info(f"Created agent {agent_id} of type {agent_type}")
        return agent
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Agent instance or None
        """
        return self._agents.get(agent_id)
    
    def list_agents(self) -> Dict[str, Dict]:
        """List all registered agents.
        
        Returns:
            Dictionary mapping agent_id to agent info
        """
        return {
            agent_id: {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "status": agent.status.value,
                "config": agent.config
            }
            for agent_id, agent in self._agents.items()
        }
    
    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            True if agent was removed
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Removed agent {agent_id}")
            return True
        return False



