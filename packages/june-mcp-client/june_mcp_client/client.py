"""
MCP Client for TODO MCP Service.

Provides a Python client library that implements the Model Context Protocol (MCP)
using JSON-RPC 2.0 to interact with the TODO MCP Service.
"""
import json
import logging
import uuid
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass

import httpx

from .types import Task, TaskContext, AgentPerformance, Project

logger = logging.getLogger(__name__)


@dataclass
class MCPError:
    """MCP error response."""
    code: int
    message: str
    data: Optional[Any] = None


class MCPClientError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPConnectionError(MCPClientError):
    """Connection error to MCP service."""
    pass


class MCPProtocolError(MCPClientError):
    """JSON-RPC protocol error."""
    pass


class MCPServiceError(MCPClientError):
    """Service error from MCP server."""
    def __init__(self, error: MCPError):
        self.error = error
        super().__init__(f"MCP Error {error.code}: {error.message}")


class MCPClient:
    """
    MCP Client for TODO MCP Service.
    
    Connects to TODO MCP Service using JSON-RPC 2.0 protocol over HTTP POST.
    Supports both SSE and HTTP POST endpoints.
    
    Example:
        ```python
        from june_mcp_client import MCPClient
        
        client = MCPClient(base_url="http://localhost:8000/mcp/todo-mcp-service")
        
        # List available tasks
        tasks = client.list_available_tasks(agent_type="implementation", limit=10)
        
        # Reserve a task
        result = client.reserve_task(task_id=123, agent_id="my-agent")
        
        # Complete a task
        client.complete_task(task_id=123, agent_id="my-agent", notes="Done!")
        ```
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize MCP client.
        
        Args:
            base_url: Base URL of TODO MCP Service (defaults to TODO_SERVICE_URL env var or http://localhost:8000/mcp/todo-mcp-service)
            api_key: API key for authentication (optional, defaults to TODO_API_KEY env var)
            timeout: Request timeout in seconds (default: 30.0)
            max_retries: Maximum number of retry attempts for transient failures (default: 3)
            retry_delay: Delay between retries in seconds (default: 1.0)
        """
        if base_url is None:
            import os
            base_url = os.getenv("TODO_SERVICE_URL", "http://localhost:8000/mcp/todo-mcp-service")
        self.base_url = base_url.rstrip("/")
        
        if api_key is None:
            import os
            api_key = os.getenv("TODO_API_KEY")
        self.api_key = api_key
        
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # MCP endpoint - use /mcp/sse for POST requests
        self.mcp_endpoint = f"{self.base_url}/mcp/sse"
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers
    
    def _make_jsonrpc_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Make a JSON-RPC 2.0 request to the MCP service.
        
        Args:
            method: JSON-RPC method name
            params: Method parameters
            request_id: Request ID (generated if not provided)
            
        Returns:
            Response result
            
        Raises:
            MCPConnectionError: If connection fails
            MCPProtocolError: If protocol error occurs
            MCPServiceError: If service returns an error
        """
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }
        
        if params:
            payload["params"] = params
        
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        self.mcp_endpoint,
                        json=payload,
                        headers=self._get_headers()
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    # Check for JSON-RPC error
                    if "error" in result:
                        error = result["error"]
                        mcp_error = MCPError(
                            code=error.get("code", -1),
                            message=error.get("message", "Unknown error"),
                            data=error.get("data")
                        )
                        raise MCPServiceError(mcp_error)
                    
                    # Return result
                    if "result" in result:
                        return result["result"]
                    else:
                        raise MCPProtocolError(f"Invalid JSON-RPC response: missing 'result' or 'error'")
                        
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < self.max_retries:
                    # Server error - retry
                    import time
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise MCPConnectionError(f"HTTP error {e.response.status_code}: {e.response.text}")
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    # Connection error - retry
                    import time
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise MCPConnectionError(f"Connection error: {e}")
            except json.JSONDecodeError as e:
                raise MCPProtocolError(f"Invalid JSON response: {e}")
        
        raise MCPConnectionError(f"Failed after {self.max_retries + 1} attempts")
    
    def _call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result (parsed from JSON if possible)
        """
        result = self._make_jsonrpc_request(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments
            }
        )
        
        # Parse result content
        # MCP returns result as {"content": [{"type": "text", "text": "<json>"}]}
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list) and len(content) > 0:
                text_content = content[0].get("text", "")
                if text_content:
                    try:
                        return json.loads(text_content)
                    except json.JSONDecodeError:
                        return text_content
        
        return result
    
    # Task Management Methods
    
    def list_available_tasks(
        self,
        agent_type: Literal["breakdown", "implementation"],
        project_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Task]:
        """
        List available tasks for an agent type.
        
        Args:
            agent_type: 'breakdown' for abstract/epic tasks, 'implementation' for concrete tasks
            project_id: Optional project ID to filter tasks
            limit: Maximum number of tasks to return
            
        Returns:
            List of Task objects
        """
        result = self._call_tool(
            "list_available_tasks",
            {
                "agent_type": agent_type,
                "project_id": project_id,
                "limit": limit
            }
        )
        
        # Handle both list and dict response formats
        if isinstance(result, dict) and "tasks" in result:
            tasks = result["tasks"]
        elif isinstance(result, list):
            tasks = result
        else:
            tasks = []
        
        return [Task.from_dict(task) if isinstance(task, dict) else task for task in tasks]
    
    def reserve_task(
        self,
        task_id: int,
        agent_id: str
    ) -> TaskContext:
        """
        Reserve (lock) a task for an agent.
        
        Args:
            task_id: Task ID to reserve
            agent_id: Agent ID reserving the task
            
        Returns:
            TaskContext with full task information
            
        Raises:
            MCPServiceError: If task not found or already locked
        """
        result = self._call_tool(
            "reserve_task",
            {
                "task_id": task_id,
                "agent_id": agent_id
            }
        )
        
        # Check for error response
        if isinstance(result, dict) and not result.get("success", True):
            error_msg = result.get("error", "Unknown error")
            raise MCPServiceError(MCPError(code=-1, message=error_msg))
        
        # Parse task context
        if isinstance(result, dict) and "task" in result:
            # Full context returned
            return TaskContext.from_dict(result)
        elif isinstance(result, dict):
            # Try to parse as task context
            return TaskContext.from_dict(result)
        else:
            raise MCPProtocolError(f"Unexpected response format: {result}")
    
    def get_task_context(self, task_id: int) -> TaskContext:
        """
        Get full context for a task (project, updates, ancestry).
        
        Args:
            task_id: Task ID
            
        Returns:
            TaskContext with full information
        """
        result = self._call_tool(
            "get_task_context",
            {
                "task_id": task_id
            }
        )
        
        if isinstance(result, dict):
            return TaskContext.from_dict(result)
        else:
            raise MCPProtocolError(f"Unexpected response format: {result}")
    
    def complete_task(
        self,
        task_id: int,
        agent_id: str,
        notes: Optional[str] = None,
        actual_hours: Optional[float] = None,
        followup_title: Optional[str] = None,
        followup_task_type: Optional[Literal["concrete", "abstract", "epic"]] = None,
        followup_instruction: Optional[str] = None,
        followup_verification: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete a task.
        
        Args:
            task_id: Task ID to complete
            agent_id: Agent ID completing the task
            notes: Optional completion notes
            actual_hours: Optional actual hours spent
            followup_title: Optional followup task title
            followup_task_type: Optional followup task type
            followup_instruction: Optional followup task instruction
            followup_verification: Optional followup task verification
            
        Returns:
            Completion result with optional followup_task_id
        """
        arguments = {
            "task_id": task_id,
            "agent_id": agent_id
        }
        
        if notes is not None:
            arguments["notes"] = notes
        if actual_hours is not None:
            arguments["actual_hours"] = actual_hours
        if followup_title is not None:
            arguments["followup_title"] = followup_title
        if followup_task_type is not None:
            arguments["followup_task_type"] = followup_task_type
        if followup_instruction is not None:
            arguments["followup_instruction"] = followup_instruction
        if followup_verification is not None:
            arguments["followup_verification"] = followup_verification
        
        return self._call_tool("complete_task", arguments)
    
    def unlock_task(
        self,
        task_id: int,
        agent_id: str
    ) -> Dict[str, Any]:
        """
        Unlock a task (release reservation).
        
        Args:
            task_id: Task ID to unlock
            agent_id: Agent ID unlocking the task
            
        Returns:
            Unlock result
        """
        return self._call_tool(
            "unlock_task",
            {
                "task_id": task_id,
                "agent_id": agent_id
            }
        )
    
    def add_task_update(
        self,
        task_id: int,
        agent_id: str,
        content: str,
        update_type: Literal["progress", "note", "blocker", "question", "finding"],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add an update to a task.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID making the update
            content: Update content
            update_type: Type of update
            metadata: Optional metadata
            
        Returns:
            Update result with update_id
        """
        arguments = {
            "task_id": task_id,
            "agent_id": agent_id,
            "content": content,
            "update_type": update_type
        }
        
        if metadata is not None:
            arguments["metadata"] = metadata
        
        return self._call_tool("add_task_update", arguments)
    
    def create_task(
        self,
        title: str,
        task_type: Literal["concrete", "abstract", "epic"],
        task_instruction: str,
        verification_instruction: str,
        agent_id: str,
        project_id: Optional[int] = None,
        parent_task_id: Optional[int] = None,
        relationship_type: Optional[Literal["subtask", "blocking", "blocked_by", "related"]] = None,
        notes: Optional[str] = None,
        priority: Optional[Literal["low", "medium", "high", "critical"]] = None,
        estimated_hours: Optional[float] = None,
        due_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new task.
        
        Args:
            title: Task title
            task_type: Task type
            task_instruction: Task instruction
            verification_instruction: Verification instruction
            agent_id: Agent ID creating the task
            project_id: Optional project ID
            parent_task_id: Optional parent task ID
            relationship_type: Optional relationship type if parent_task_id is set
            notes: Optional notes
            priority: Optional priority
            estimated_hours: Optional estimated hours
            due_date: Optional due date (ISO format)
            
        Returns:
            Created task result with task_id
        """
        arguments = {
            "title": title,
            "task_type": task_type,
            "task_instruction": task_instruction,
            "verification_instruction": verification_instruction,
            "agent_id": agent_id
        }
        
        if project_id is not None:
            arguments["project_id"] = project_id
        if parent_task_id is not None:
            arguments["parent_task_id"] = parent_task_id
        if relationship_type is not None:
            arguments["relationship_type"] = relationship_type
        if notes is not None:
            arguments["notes"] = notes
        if priority is not None:
            arguments["priority"] = priority
        if estimated_hours is not None:
            arguments["estimated_hours"] = estimated_hours
        if due_date is not None:
            arguments["due_date"] = due_date
        
        return self._call_tool("create_task", arguments)
    
    def query_tasks(
        self,
        project_id: Optional[int] = None,
        task_type: Optional[Literal["concrete", "abstract", "epic"]] = None,
        task_status: Optional[Literal["available", "in_progress", "complete", "blocked", "cancelled"]] = None,
        agent_id: Optional[str] = None,
        priority: Optional[Literal["low", "medium", "high", "critical"]] = None,
        tag_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        limit: int = 100
    ) -> List[Task]:
        """
        Query tasks with filters.
        
        Args:
            project_id: Filter by project ID
            task_type: Filter by task type
            task_status: Filter by task status
            agent_id: Filter by assigned agent
            priority: Filter by priority
            tag_id: Filter by tag ID
            tag_ids: Filter by multiple tag IDs (all must match)
            limit: Maximum number of results
            
        Returns:
            List of Task objects
        """
        arguments = {"limit": limit}
        
        if project_id is not None:
            arguments["project_id"] = project_id
        if task_type is not None:
            arguments["task_type"] = task_type
        if task_status is not None:
            arguments["task_status"] = task_status
        if agent_id is not None:
            arguments["agent_id"] = agent_id
        if priority is not None:
            arguments["priority"] = priority
        if tag_id is not None:
            arguments["tag_id"] = tag_id
        if tag_ids is not None:
            arguments["tag_ids"] = tag_ids
        
        result = self._call_tool("query_tasks", arguments)
        
        # Handle both list and dict response formats
        if isinstance(result, dict) and "tasks" in result:
            tasks = result["tasks"]
        elif isinstance(result, list):
            tasks = result
        else:
            tasks = []
        
        return [Task.from_dict(task) if isinstance(task, dict) else task for task in tasks]
    
    def get_agent_performance(
        self,
        agent_id: str,
        task_type: Optional[Literal["concrete", "abstract", "epic"]] = None
    ) -> AgentPerformance:
        """
        Get agent performance statistics.
        
        Args:
            agent_id: Agent ID
            task_type: Optional filter by task type
            
        Returns:
            AgentPerformance statistics
        """
        arguments = {"agent_id": agent_id}
        
        if task_type is not None:
            arguments["task_type"] = task_type
        
        result = self._call_tool("get_agent_performance", arguments)
        
        if isinstance(result, dict):
            return AgentPerformance.from_dict(result)
        else:
            raise MCPProtocolError(f"Unexpected response format: {result}")
    
    def get_task_statistics(
        self,
        project_id: Optional[int] = None,
        task_type: Optional[Literal["concrete", "abstract", "epic"]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get task statistics.
        
        Args:
            project_id: Optional filter by project ID
            task_type: Optional filter by task type
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
            
        Returns:
            Statistics dictionary
        """
        arguments = {}
        
        if project_id is not None:
            arguments["project_id"] = project_id
        if task_type is not None:
            arguments["task_type"] = task_type
        if start_date is not None:
            arguments["start_date"] = start_date
        if end_date is not None:
            arguments["end_date"] = end_date
        
        return self._call_tool("get_task_statistics", arguments)
