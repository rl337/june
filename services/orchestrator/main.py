"""
Orchestration Service - Manages agent lifecycle, task distribution, and coordination.

This service provides the control plane for the agentic system:
- Orchestration: Start/stop agents, manage lifecycle
- Task Distribution: Assign tasks to agents, balance workload
- Coordination: Prevent conflicts, manage shared resources
- Monitoring: Track agent health, system metrics
- Configuration: Manage agent and system settings
"""
import asyncio
import json
import os
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
import uuid

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field
import httpx
import sys
from pathlib import Path

# Add june-agent-state package to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "packages" / "june-agent-state"))

# Setup logging first (before imports that might log)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Try to import monitoring infrastructure
try:
    from june_agent_state.monitoring import AgentMonitor
    from june_agent_state.registry import AgentRegistry
    from june_agent_state.storage import AgentStateStorage
except ImportError as e:
    logger.warning(f"Could not import june-agent-state monitoring: {e}. Monitoring endpoints will be disabled.")
    AgentMonitor = None
    AgentRegistry = None
    AgentStateStorage = None

# Prometheus metrics
REGISTRY = CollectorRegistry()
AGENT_START_COUNT = Counter('orchestrator_agent_starts_total', 'Total agent starts', ['agent_id'], registry=REGISTRY)
AGENT_STOP_COUNT = Counter('orchestrator_agent_stops_total', 'Total agent stops', ['agent_id'], registry=REGISTRY)
TASK_ASSIGN_COUNT = Counter('orchestrator_task_assignments_total', 'Task assignments', ['agent_id', 'status'], registry=REGISTRY)
ACTIVE_AGENTS = Gauge('orchestrator_active_agents', 'Currently active agents', registry=REGISTRY)
PENDING_TASKS = Gauge('orchestrator_pending_tasks', 'Pending tasks awaiting assignment', registry=REGISTRY)

# Agent monitoring metrics
AGENT_TASKS_COMPLETED = Counter('agent_tasks_completed_total', 'Total tasks completed per agent', ['agent_id'], registry=REGISTRY)
AGENT_TASKS_FAILED = Counter('agent_tasks_failed_total', 'Total tasks failed per agent', ['agent_id'], registry=REGISTRY)
AGENT_SUCCESS_RATE = Gauge('agent_success_rate', 'Success rate per agent (0.0-1.0)', ['agent_id'], registry=REGISTRY)
AGENT_AVG_EXECUTION_TIME = Histogram('agent_avg_execution_time_seconds', 'Average execution time per agent', ['agent_id'], registry=REGISTRY)
AGENT_UPTIME = Gauge('agent_uptime_seconds', 'Agent uptime in seconds', ['agent_id'], registry=REGISTRY)


class AgentStatus(str, Enum):
    """Agent status enumeration."""
    INIT = "init"
    STARTING = "starting"
    ACTIVE = "active"
    IDLE = "idle"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class AgentInfo:
    """Information about a registered agent."""
    agent_id: str
    agent_type: str  # 'implementation' or 'breakdown'
    status: AgentStatus = AgentStatus.INIT
    capabilities: Set[str] = field(default_factory=set)
    current_task_id: Optional[int] = None
    project_id: Optional[int] = None
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    task_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['status'] = self.status.value
        data['capabilities'] = list(self.capabilities)
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.last_heartbeat:
            data['last_heartbeat'] = self.last_heartbeat.isoformat()
        return data


class TaskAssignmentRequest(BaseModel):
    """Request to assign a task to an agent."""
    task_id: int
    agent_id: Optional[str] = None
    priority: int = Field(default=0, ge=0, le=10)
    force: bool = False  # Force assignment even if agent is busy


class AgentRegistrationRequest(BaseModel):
    """Request to register a new agent."""
    agent_id: str
    agent_type: str = Field(..., pattern="^(implementation|breakdown)$")
    capabilities: List[str] = Field(default_factory=list)
    project_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Agent configuration."""
    max_concurrent_tasks: int = Field(default=1, ge=1)
    heartbeat_interval_seconds: int = Field(default=60, ge=10)
    task_timeout_seconds: int = Field(default=3600, ge=60)
    auto_restart: bool = True
    resource_limits: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationService:
    """Main orchestration service class."""
    
    def __init__(self):
        self.app = FastAPI(
            title="June Agent Orchestrator",
            description="Orchestration and coordination service for June agents",
            version="0.1.0"
        )
        
        # Agent registry
        self.agents: Dict[str, AgentInfo] = {}
        self.agent_configs: Dict[str, AgentConfig] = {}
        
        # Task queue
        self.pending_tasks: List[Dict[str, Any]] = []
        self.assigned_tasks: Dict[int, str] = {}  # task_id -> agent_id
        
        # Coordination
        self.resource_locks: Dict[str, str] = {}  # resource -> agent_id
        
        # Configuration
        self.todo_service_url = os.getenv("TODO_SERVICE_URL", "http://localhost:8000/mcp/todo-mcp-service")
        self.gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000")
        
        # MCP client for TODO service
        self.mcp_client: Optional[httpx.AsyncClient] = None
        
        # Monitoring infrastructure
        self.monitor: Optional[AgentMonitor] = None
        self.registry: Optional[AgentRegistry] = None
        self.storage: Optional[AgentStateStorage] = None
        self._monitoring_enabled = AgentMonitor is not None
        
        self._setup_middleware()
        self._setup_routes()
        self._start_background_tasks()
    
    def _setup_middleware(self):
        """Setup middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            healthy_agents = sum(1 for a in self.agents.values() if a.status == AgentStatus.ACTIVE)
            total_agents = len(self.agents)
            return {
                "status": "healthy" if total_agents > 0 or healthy_agents > 0 else "degraded",
                "active_agents": healthy_agents,
                "total_agents": total_agents,
                "pending_tasks": len(self.pending_tasks),
            }
        
        @self.app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return Response(
                content=generate_latest(REGISTRY),
                media_type=CONTENT_TYPE_LATEST
            )
        
        # Monitoring API endpoints
        if self._monitoring_enabled:
            @self.app.get("/monitoring/agents/{agent_id}/activity")
            async def get_agent_activity(
                agent_id: str = Path(..., description="Agent ID"),
                time_range_hours: Optional[int] = Query(None, description="Time range in hours (default: 24)")
            ):
                """Get agent activity within a time range."""
                if not self.monitor:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Monitoring not initialized"
                    )
                
                time_range = timedelta(hours=time_range_hours) if time_range_hours else timedelta(hours=24)
                activity = await self.monitor.get_agent_activity(agent_id, time_range=time_range)
                
                return {
                    "agent_id": agent_id,
                    "time_range_hours": time_range_hours or 24,
                    "activity": activity,
                    "count": len(activity)
                }
            
            @self.app.get("/monitoring/agents/{agent_id}/metrics")
            async def get_agent_metrics(agent_id: str = Path(..., description="Agent ID")):
                """Get performance metrics for an agent."""
                if not self.monitor:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Monitoring not initialized"
                    )
                
                metrics_data = await self.monitor.get_agent_metrics(agent_id)
                
                if not metrics_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Agent {agent_id} not found or has no metrics"
                    )
                
                return metrics_data
            
            @self.app.get("/monitoring/agents/{agent_id}/health")
            async def get_agent_health(agent_id: str = Path(..., description="Agent ID")):
                """Get agent health status."""
                if not self.monitor:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Monitoring not initialized"
                    )
                
                health = await self.monitor.get_agent_health(agent_id)
                return health
            
            @self.app.get("/monitoring/agents/status")
            async def list_all_agent_status():
                """List status for all agents."""
                if not self.monitor:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Monitoring not initialized"
                    )
                
                statuses = await self.monitor.list_all_agent_status()
                return {
                    "agents": statuses,
                    "count": len(statuses)
                }
            
            @self.app.post("/monitoring/alerts/check-failures")
            async def check_failure_alerts(
                threshold: int = Query(3, ge=1, description="Failure threshold"),
                time_range_hours: Optional[int] = Query(None, description="Time range in hours (default: 1)")
            ):
                """Check for agent failures and generate alerts."""
                if not self.monitor:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Monitoring not initialized"
                    )
                
                time_range = timedelta(hours=time_range_hours) if time_range_hours else timedelta(hours=1)
                alerts = await self.monitor.alert_on_failures(threshold=threshold, time_range=time_range)
                
                return {
                    "alerts": alerts,
                    "count": len(alerts),
                    "threshold": threshold,
                    "time_range_hours": time_range_hours or 1
                }
            
            @self.app.post("/monitoring/alerts/check-degradation")
            async def check_performance_degradation_alerts(
                threshold_decrease: float = Query(0.2, ge=0.0, le=1.0, description="Minimum success rate decrease to trigger alert")
            ):
                """Check for agent performance degradation and generate alerts."""
                if not self.monitor:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Monitoring not initialized"
                    )
                
                alerts = await self.monitor.get_performance_degradation_alerts(threshold_decrease=threshold_decrease)
                
                return {
                    "alerts": alerts,
                    "count": len(alerts),
                    "threshold_decrease": threshold_decrease
                }
        
        @self.app.post("/agents/register")
        async def register_agent(request: AgentRegistrationRequest):
            """Register a new agent."""
            if request.agent_id in self.agents:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Agent {request.agent_id} already registered"
                )
            
            agent = AgentInfo(
                agent_id=request.agent_id,
                agent_type=request.agent_type,
                status=AgentStatus.STARTING,
                capabilities=set(request.capabilities),
                project_id=request.project_id,
                started_at=datetime.now(),
                last_heartbeat=datetime.now(),
                metadata=request.metadata
            )
            
            self.agents[request.agent_id] = agent
            self.agent_configs[request.agent_id] = AgentConfig()
            
            ACTIVE_AGENTS.set(len([a for a in self.agents.values() if a.status in (AgentStatus.ACTIVE, AgentStatus.IDLE)]))
            AGENT_START_COUNT.labels(agent_id=request.agent_id).inc()
            
            logger.info(f"Registered agent: {request.agent_id} (type: {request.agent_type})")
            
            return {
                "agent_id": request.agent_id,
                "status": "registered",
                "message": f"Agent {request.agent_id} registered successfully"
            }
        
        @self.app.post("/agents/{agent_id}/start")
        async def start_agent(agent_id: str):
            """Start an agent."""
            if agent_id not in self.agents:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent {agent_id} not found"
                )
            
            agent = self.agents[agent_id]
            if agent.status in (AgentStatus.ACTIVE, AgentStatus.STARTING):
                return {"status": "already_active", "message": f"Agent {agent_id} is already active or starting"}
            
            agent.status = AgentStatus.STARTING
            agent.started_at = datetime.now()
            agent.last_heartbeat = datetime.now()
            
            # In a real implementation, this would start the agent process
            # For now, we just mark it as active
            agent.status = AgentStatus.ACTIVE
            ACTIVE_AGENTS.set(len([a for a in self.agents.values() if a.status in (AgentStatus.ACTIVE, AgentStatus.IDLE)]))
            AGENT_START_COUNT.labels(agent_id=agent_id).inc()
            
            logger.info(f"Started agent: {agent_id}")
            
            return {
                "agent_id": agent_id,
                "status": "started",
                "message": f"Agent {agent_id} started successfully"
            }
        
        @self.app.post("/agents/{agent_id}/stop")
        async def stop_agent(agent_id: str):
            """Stop an agent."""
            if agent_id not in self.agents:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent {agent_id} not found"
                )
            
            agent = self.agents[agent_id]
            if agent.status == AgentStatus.STOPPED:
                return {"status": "already_stopped", "message": f"Agent {agent_id} is already stopped"}
            
            agent.status = AgentStatus.STOPPING
            
            # Release current task
            if agent.current_task_id:
                task_id = agent.current_task_id
                agent.current_task_id = None
                if task_id in self.assigned_tasks:
                    del self.assigned_tasks[task_id]
                logger.info(f"Released task {task_id} from agent {agent_id}")
            
            agent.status = AgentStatus.STOPPED
            ACTIVE_AGENTS.set(len([a for a in self.agents.values() if a.status in (AgentStatus.ACTIVE, AgentStatus.IDLE)]))
            AGENT_STOP_COUNT.labels(agent_id=agent_id).inc()
            
            logger.info(f"Stopped agent: {agent_id}")
            
            return {
                "agent_id": agent_id,
                "status": "stopped",
                "message": f"Agent {agent_id} stopped successfully"
            }
        
        @self.app.get("/agents")
        async def list_agents():
            """List all registered agents."""
            return {
                "agents": [agent.to_dict() for agent in self.agents.values()],
                "total": len(self.agents),
                "active": len([a for a in self.agents.values() if a.status == AgentStatus.ACTIVE])
            }
        
        @self.app.get("/agents/{agent_id}")
        async def get_agent(agent_id: str):
            """Get agent information."""
            if agent_id not in self.agents:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent {agent_id} not found"
                )
            return self.agents[agent_id].to_dict()
        
        @self.app.post("/agents/{agent_id}/heartbeat")
        async def agent_heartbeat(agent_id: str):
            """Agent heartbeat to indicate it's alive."""
            if agent_id not in self.agents:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent {agent_id} not found"
                )
            
            agent = self.agents[agent_id]
            agent.last_heartbeat = datetime.now()
            
            # If agent was in error state and now sending heartbeat, mark as active
            if agent.status == AgentStatus.ERROR:
                agent.status = AgentStatus.ACTIVE
                logger.info(f"Agent {agent_id} recovered from error state")
            
            return {"status": "ok", "timestamp": agent.last_heartbeat.isoformat()}
        
        @self.app.post("/tasks/assign")
        async def assign_task(request: TaskAssignmentRequest):
            """Assign a task to an agent."""
            # Check if task is already assigned
            if request.task_id in self.assigned_tasks:
                assigned_agent = self.assigned_tasks[request.task_id]
                if not request.force:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Task {request.task_id} already assigned to agent {assigned_agent}"
                    )
                # Force assignment - release from current agent
                if assigned_agent in self.agents:
                    self.agents[assigned_agent].current_task_id = None
            
            # Select agent
            if request.agent_id:
                if request.agent_id not in self.agents:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Agent {request.agent_id} not found"
                    )
                agent = self.agents[request.agent_id]
            else:
                # Auto-select best available agent
                agent = self._select_agent_for_task(request.task_id)
                if not agent:
                    # No available agent, add to pending queue
                    self.pending_tasks.append({
                        "task_id": request.task_id,
                        "priority": request.priority,
                        "requested_at": datetime.now().isoformat()
                    })
                    PENDING_TASKS.set(len(self.pending_tasks))
                    return {
                        "status": "queued",
                        "message": f"Task {request.task_id} queued - no available agents",
                        "task_id": request.task_id
                    }
            
            # Check if agent can take task
            config = self.agent_configs[agent.agent_id]
            if agent.current_task_id and not request.force:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Agent {agent.agent_id} is already working on task {agent.current_task_id}"
                )
            
            # Assign task
            agent.current_task_id = request.task_id
            agent.status = AgentStatus.ACTIVE
            self.assigned_tasks[request.task_id] = agent.agent_id
            agent.task_count += 1
            
            TASK_ASSIGN_COUNT.labels(agent_id=agent.agent_id, status="assigned").inc()
            PENDING_TASKS.set(len(self.pending_tasks))
            
            logger.info(f"Assigned task {request.task_id} to agent {agent.agent_id}")
            
            return {
                "status": "assigned",
                "task_id": request.task_id,
                "agent_id": agent.agent_id,
                "message": f"Task {request.task_id} assigned to agent {agent.agent_id}"
            }
        
        @self.app.post("/tasks/{task_id}/complete")
        async def complete_task(task_id: int, agent_id: str):
            """Mark a task as complete and release agent."""
            if task_id not in self.assigned_tasks:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Task {task_id} not assigned"
                )
            
            assigned_agent_id = self.assigned_tasks[task_id]
            if assigned_agent_id != agent_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Task {task_id} is assigned to agent {assigned_agent_id}, not {agent_id}"
                )
            
            agent = self.agents[assigned_agent_id]
            agent.current_task_id = None
            agent.success_count += 1
            agent.status = AgentStatus.IDLE
            
            del self.assigned_tasks[task_id]
            TASK_ASSIGN_COUNT.labels(agent_id=agent_id, status="completed").inc()
            
            # Assign next pending task if available
            await self._process_pending_tasks()
            
            logger.info(f"Task {task_id} completed by agent {agent_id}")
            
            return {
                "status": "completed",
                "task_id": task_id,
                "agent_id": agent_id,
                "message": f"Task {task_id} marked as complete"
            }
        
        @self.app.get("/tasks/pending")
        async def list_pending_tasks():
            """List pending tasks."""
            return {
                "pending_tasks": self.pending_tasks,
                "count": len(self.pending_tasks)
            }
        
        @self.app.get("/stats")
        async def get_statistics():
            """Get orchestration statistics."""
            active_agents = [a for a in self.agents.values() if a.status == AgentStatus.ACTIVE]
            idle_agents = [a for a in self.agents.values() if a.status == AgentStatus.IDLE]
            
            return {
                "total_agents": len(self.agents),
                "active_agents": len(active_agents),
                "idle_agents": len(idle_agents),
                "pending_tasks": len(self.pending_tasks),
                "assigned_tasks": len(self.assigned_tasks),
                "total_tasks_completed": sum(a.success_count for a in self.agents.values()),
                "total_tasks_failed": sum(a.failure_count for a in self.agents.values()),
            }
    
    def _select_agent_for_task(self, task_id: int) -> Optional[AgentInfo]:
        """Select the best available agent for a task."""
        available_agents = [
            a for a in self.agents.values()
            if a.status in (AgentStatus.ACTIVE, AgentStatus.IDLE)
            and not a.current_task_id
        ]
        
        if not available_agents:
            return None
        
        # Simple selection: prefer idle agents, then by least tasks
        available_agents.sort(
            key=lambda a: (
                0 if a.status == AgentStatus.IDLE else 1,  # Prefer idle
                a.task_count  # Then by task count
            )
        )
        
        return available_agents[0]
    
    async def _process_pending_tasks(self):
        """Process pending tasks and assign to available agents."""
        if not self.pending_tasks:
            return
        
        # Sort by priority (higher priority first)
        self.pending_tasks.sort(key=lambda t: t.get("priority", 0), reverse=True)
        
        # Try to assign each pending task
        remaining = []
        for task_info in self.pending_tasks:
            task_id = task_info["task_id"]
            agent = self._select_agent_for_task(task_id)
            
            if agent:
                agent.current_task_id = task_id
                agent.status = AgentStatus.ACTIVE
                self.assigned_tasks[task_id] = agent.agent_id
                agent.task_count += 1
                TASK_ASSIGN_COUNT.labels(agent_id=agent.agent_id, status="assigned").inc()
                logger.info(f"Assigned pending task {task_id} to agent {agent.agent_id}")
            else:
                remaining.append(task_info)
        
        self.pending_tasks = remaining
        PENDING_TASKS.set(len(self.pending_tasks))
    
    def _start_background_tasks(self):
        """Start background tasks for monitoring and health checks."""
        
        @self.app.on_event("startup")
        async def startup():
            """Initialize on startup."""
            logger.info("Orchestration service starting...")
            self.mcp_client = httpx.AsyncClient(
                base_url=self.todo_service_url,
                timeout=30.0
            )
            logger.info("MCP client initialized")
            
            # Initialize monitoring infrastructure if available
            if self._monitoring_enabled:
                try:
                    # Get PostgreSQL connection details from environment
                    db_host = os.getenv("POSTGRES_HOST", "localhost")
                    db_port = int(os.getenv("POSTGRES_PORT", "5432"))
                    db_name = os.getenv("POSTGRES_DB", "june")
                    db_user = os.getenv("POSTGRES_USER", "postgres")
                    db_password = os.getenv("POSTGRES_PASSWORD", "")
                    
                    # Initialize storage
                    self.storage = AgentStateStorage(
                        host=db_host,
                        port=db_port,
                        database=db_name,
                        user=db_user,
                        password=db_password if db_password else None
                    )
                    await self.storage.connect()
                    logger.info("Agent state storage connected")
                    
                    # Initialize registry
                    self.registry = AgentRegistry(self.storage)
                    logger.info("Agent registry initialized")
                    
                    # Initialize monitor
                    self.monitor = AgentMonitor(self.registry, self.storage)
                    logger.info("Agent monitor initialized")
                    
                    logger.info("Monitoring infrastructure ready")
                except Exception as e:
                    logger.error(f"Failed to initialize monitoring infrastructure: {e}", exc_info=True)
                    logger.warning("Monitoring endpoints will be unavailable")
                    self._monitoring_enabled = False
                    self.monitor = None
                    self.registry = None
                    self.storage = None
        
        @self.app.on_event("shutdown")
        async def shutdown():
            """Cleanup on shutdown."""
            logger.info("Orchestration service shutting down...")
            if self.mcp_client:
                await self.mcp_client.aclose()
            if self.storage:
                await self.storage.disconnect()
                logger.info("Agent state storage disconnected")
        
        # Background task: Check agent health
        async def check_agent_health():
            """Periodically check agent health."""
            while True:
                await asyncio.sleep(60)  # Check every minute
                
                now = datetime.now()
                for agent_id, agent in list(self.agents.items()):
                    if agent.status in (AgentStatus.ACTIVE, AgentStatus.IDLE):
                        if agent.last_heartbeat:
                            time_since_heartbeat = (now - agent.last_heartbeat).total_seconds()
                            config = self.agent_configs.get(agent_id, AgentConfig())
                            
                            # If heartbeat is too old, mark as error
                            if time_since_heartbeat > config.heartbeat_interval_seconds * 3:
                                logger.warning(f"Agent {agent_id} has not sent heartbeat in {time_since_heartbeat:.0f}s")
                                agent.status = AgentStatus.ERROR
                                ACTIVE_AGENTS.set(len([a for a in self.agents.values() if a.status in (AgentStatus.ACTIVE, AgentStatus.IDLE)]))
        
        # Start background task
        asyncio.create_task(check_agent_health())


# Create service instance
service = OrchestrationService()
app = service.app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("ORCHESTRATOR_PORT", "8005"))
    uvicorn.run(app, host="0.0.0.0", port=port)
