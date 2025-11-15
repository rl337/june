"""Switchboard service main entry point."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import uuid

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from switchboard.agent_registry import AgentRegistry
from switchboard.session_lock import SessionLock
from switchboard.agents.base import AgentRequest, AgentStatus
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize components
app = FastAPI(title="Switchboard Service", version="0.1.0")
registry = AgentRegistry()
session_lock = SessionLock(Path(os.getenv("SWITCHBOARD_LOCK_DIR", "/tmp/switchboard/locks")))

# Load agent configuration
AGENT_CONFIG_FILE = Path(os.getenv("SWITCHBOARD_CONFIG", "/etc/switchboard/agents.json"))
agent_configs: Dict[str, Dict[str, Any]] = {}


def load_agent_configs():
    """Load agent configurations from file or environment."""
    global agent_configs
    
    if AGENT_CONFIG_FILE.exists():
        import json
        with open(AGENT_CONFIG_FILE) as f:
            agent_configs = json.load(f)
        logger.info(f"Loaded agent configs from {AGENT_CONFIG_FILE}")
    else:
        # Default configuration for telegram response agent
        agent_configs = {
            "telegram-response": {
                "type": "popen_cursor",
                "config": {
                    "script_path": os.getenv(
                        "TELEGRAM_AGENT_SCRIPT",
                        str(Path(__file__).parent.parent.parent / "agenticness" / "scripts" / "telegram_response_agent.sh")
                    ),
                    "script_simple_path": os.getenv(
                        "TELEGRAM_AGENT_SIMPLE_SCRIPT",
                        str(Path(__file__).parent.parent.parent / "agenticness" / "scripts" / "telegram_response_agent_simple.sh")
                    ),
                    "working_directory": os.getenv("AGENT_WORKING_DIR", str(Path.cwd())),
                    "timeout": int(os.getenv("AGENT_TIMEOUT", "3600")),
                    "use_simple": os.getenv("AGENT_USE_SIMPLE", "false").lower() == "true"
                }
            }
        }
        logger.info("Using default agent configuration")


# Request/Response models
class AgentExecuteRequest(BaseModel):
    """Request to execute an agent."""
    agent_id: str = Field(..., description="Agent identifier")
    session_id: str = Field(..., description="Session identifier for stateful execution")
    message: str = Field(..., description="Message/instruction for the agent")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context (user_id, chat_id, etc.)")
    timeout: Optional[int] = Field(None, description="Execution timeout in seconds")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class AgentStatusResponse(BaseModel):
    """Agent execution status response."""
    request_id: str
    agent_id: str
    session_id: str
    status: str
    message: str
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@app.on_event("startup")
async def startup():
    """Initialize service on startup."""
    load_agent_configs()
    
    # Create agents from configuration
    for agent_id, agent_config in agent_configs.items():
        try:
            agent_type = agent_config["type"]
            config = agent_config["config"]
            registry.create_agent(agent_id, agent_type, config)
            logger.info(f"Initialized agent: {agent_id}")
        except Exception as e:
            logger.error(f"Failed to initialize agent {agent_id}: {e}")
    
    # Clean up stale locks
    cleaned = await session_lock.cleanup_stale_locks()
    if cleaned > 0:
        logger.info(f"Cleaned up {cleaned} stale locks")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "switchboard",
        "agents": len(registry.list_agents())
    }


@app.get("/agents")
async def list_agents():
    """List all registered agents."""
    return {
        "agents": registry.list_agents()
    }


@app.post("/agents/{agent_id}/execute")
async def execute_agent(
    agent_id: str,
    request: AgentExecuteRequest,
    background_tasks: BackgroundTasks
):
    """Execute an agent with the given request.
    
    This endpoint streams responses as the agent executes.
    """
    # Get agent
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Acquire session lock
    lock_acquired = await session_lock.acquire(request.session_id, timeout=30.0)
    if not lock_acquired:
        raise HTTPException(
            status_code=409,
            detail=f"Session {request.session_id} is currently locked by another execution"
        )
    
    # Schedule lock release on completion
    async def release_lock():
        await session_lock.release(request.session_id)
    
    background_tasks.add_task(release_lock)
    
    # Create agent request
    agent_request = AgentRequest(
        agent_id=agent_id,
        session_id=request.session_id,
        message=request.message,
        context=request.context,
        timeout=request.timeout,
        metadata=request.metadata
    )
    
    # Stream responses
    async def generate_responses():
        try:
            async for response in agent.execute(agent_request):
                yield f"data: {response.model_dump_json()}\n\n"
        finally:
            # Ensure lock is released
            await session_lock.release(request.session_id)
    
    return StreamingResponse(
        generate_responses(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@app.post("/agents/{agent_id}/execute/sync")
async def execute_agent_sync(
    agent_id: str,
    request: AgentExecuteRequest
):
    """Execute an agent synchronously (waits for completion).
    
    Returns the final response.
    """
    # Get agent
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Acquire session lock
    lock_acquired = await session_lock.acquire(request.session_id, timeout=30.0)
    if not lock_acquired:
        raise HTTPException(
            status_code=409,
            detail=f"Session {request.session_id} is currently locked by another execution"
        )
    
    try:
        # Create agent request
        agent_request = AgentRequest(
            agent_id=agent_id,
            session_id=request.session_id,
            message=request.message,
            context=request.context,
            timeout=request.timeout,
            metadata=request.metadata
        )
        
        # Execute and collect final response
        final_response = None
        async for response in agent.execute(agent_request):
            final_response = response
            if response.status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED):
                break
        
        if not final_response:
            raise HTTPException(status_code=500, detail="No response from agent")
        
        return AgentStatusResponse(
            request_id=final_response.request_id,
            agent_id=final_response.agent_id,
            session_id=final_response.session_id,
            status=final_response.status.value,
            message=final_response.message,
            output=final_response.output,
            error=final_response.error,
            metadata=final_response.metadata
        )
    finally:
        await session_lock.release(request.session_id)


@app.post("/agents/{agent_id}/cancel/{request_id}")
async def cancel_agent(agent_id: str, request_id: str):
    """Cancel a running agent execution."""
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    cancelled = await agent.cancel(request_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found or not running")
    
    return {"status": "cancelled", "request_id": request_id}


@app.get("/agents/{agent_id}/status/{request_id}")
async def get_agent_status(agent_id: str, request_id: str):
    """Get the status of an agent execution."""
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    status = await agent.get_status(request_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    
    return AgentStatusResponse(
        request_id=status.request_id,
        agent_id=status.agent_id,
        session_id=status.session_id,
        status=status.status.value,
        message=status.message,
        output=status.output,
        error=status.error,
        metadata=status.metadata
    )


@app.get("/sessions/{session_id}/lock")
async def check_session_lock(session_id: str):
    """Check if a session is currently locked."""
    is_locked = await session_lock.is_locked(session_id)
    return {
        "session_id": session_id,
        "is_locked": is_locked
    }


def main():
    """Main entry point."""
    port = int(os.getenv("SWITCHBOARD_PORT", "8082"))
    host = os.getenv("SWITCHBOARD_HOST", "0.0.0.0")
    
    uvicorn.run(
        "switchboard.main:app",
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()

