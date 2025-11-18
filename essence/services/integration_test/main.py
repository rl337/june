"""
Integration Test Service - Runs integration tests in background and provides REST API.

This service:
- Runs integration tests in background (not blocking)
- Provides REST API for test management
- Stores test results and logs
- Provides health check endpoint
"""
import asyncio
import logging
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from essence.chat.utils.tracing import setup_tracing, get_tracer
from essence.services.shared_metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    SERVICE_HEALTH,
    REGISTRY
)
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

logger = logging.getLogger(__name__)

# Initialize tracing
try:
    setup_tracing(service_name="june-integration-test")
    tracer = get_tracer(__name__)
except ImportError:
    tracer = None


class TestRunStatus(str, Enum):
    """Status of a test run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TestRun:
    """Represents a test run."""
    run_id: str
    status: TestRunStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    output: str = ""
    error: Optional[str] = None
    test_path: Optional[str] = None
    test_name: Optional[str] = None


class IntegrationTestService:
    """Service for running integration tests in background."""
    
    def __init__(self, port: int = 8082):
        """Initialize the integration test service."""
        self.port = port
        self.app = FastAPI(title="June Integration Test Service")
        self._setup_middleware()
        self._setup_routes()
        
        # In-memory storage for test runs
        self.test_runs: Dict[str, TestRun] = {}
        self.test_processes: Dict[str, subprocess.Popen] = {}
        self.test_logs: Dict[str, List[str]] = {}
        
        # Lock for thread-safe operations
        self._lock = threading.Lock()
        
        logger.info(f"Integration test service initialized on port {self.port}")
    
    def _setup_middleware(self):
        """Setup FastAPI middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Setup REST API routes."""
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            SERVICE_HEALTH.labels(service="integration-test").set(1)
            return {"status": "healthy", "service": "integration-test"}
        
        @self.app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
        
        @self.app.post("/tests/run")
        async def start_test_run(
            test_path: Optional[str] = None,
            test_name: Optional[str] = None,
            background_tasks: BackgroundTasks = None
        ):
            """
            Start a new test run.
            
            Args:
                test_path: Optional path to specific test file or directory
                test_name: Optional specific test name to run
            
            Returns:
                Test run ID and status
            """
            HTTP_REQUESTS_TOTAL.labels(method="POST", endpoint="/tests/run", status_code=200).inc()
            
            run_id = str(uuid.uuid4())
            test_run = TestRun(
                run_id=run_id,
                status=TestRunStatus.PENDING,
                started_at=datetime.now(),
                test_path=test_path,
                test_name=test_name
            )
            
            with self._lock:
                self.test_runs[run_id] = test_run
                self.test_logs[run_id] = []
            
            # Start test run in background
            background_tasks.add_task(self._run_tests, run_id, test_path, test_name)
            
            return {
                "run_id": run_id,
                "status": test_run.status.value,
                "started_at": test_run.started_at.isoformat()
            }
        
        @self.app.get("/tests/status/{run_id}")
        async def get_test_status(run_id: str):
            """Get status of a test run."""
            HTTP_REQUESTS_TOTAL.labels(method="GET", endpoint="/tests/status", status_code=200).inc()
            
            with self._lock:
                test_run = self.test_runs.get(run_id)
            
            if not test_run:
                raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")
            
            return {
                "run_id": run_id,
                "status": test_run.status.value,
                "started_at": test_run.started_at.isoformat(),
                "completed_at": test_run.completed_at.isoformat() if test_run.completed_at else None,
                "exit_code": test_run.exit_code,
                "test_path": test_run.test_path,
                "test_name": test_run.test_name
            }
        
        @self.app.get("/tests/results/{run_id}")
        async def get_test_results(run_id: str):
            """Get results of a completed test run."""
            HTTP_REQUESTS_TOTAL.labels(method="GET", endpoint="/tests/results", status_code=200).inc()
            
            with self._lock:
                test_run = self.test_runs.get(run_id)
                logs = self.test_logs.get(run_id, [])
            
            if not test_run:
                raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")
            
            return {
                "run_id": run_id,
                "status": test_run.status.value,
                "started_at": test_run.started_at.isoformat(),
                "completed_at": test_run.completed_at.isoformat() if test_run.completed_at else None,
                "exit_code": test_run.exit_code,
                "output": test_run.output,
                "error": test_run.error,
                "logs": logs[-100:],  # Last 100 log lines
                "test_path": test_run.test_path,
                "test_name": test_run.test_name
            }
        
        @self.app.get("/tests/logs/{run_id}")
        async def get_test_logs(run_id: str, lines: int = 100):
            """Get logs for a test run."""
            HTTP_REQUESTS_TOTAL.labels(method="GET", endpoint="/tests/logs", status_code=200).inc()
            
            with self._lock:
                test_run = self.test_runs.get(run_id)
                logs = self.test_logs.get(run_id, [])
            
            if not test_run:
                raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")
            
            return {
                "run_id": run_id,
                "status": test_run.status.value,
                "logs": logs[-lines:] if lines > 0 else logs
            }
        
        @self.app.get("/tests/runs")
        async def list_test_runs(limit: int = 50):
            """List all test runs."""
            HTTP_REQUESTS_TOTAL.labels(method="GET", endpoint="/tests/runs", status_code=200).inc()
            
            with self._lock:
                runs = list(self.test_runs.values())
            
            # Sort by started_at descending
            runs.sort(key=lambda r: r.started_at, reverse=True)
            
            return {
                "runs": [
                    {
                        "run_id": run.run_id,
                        "status": run.status.value,
                        "started_at": run.started_at.isoformat(),
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                        "exit_code": run.exit_code,
                        "test_path": run.test_path,
                        "test_name": run.test_name
                    }
                    for run in runs[:limit]
                ],
                "total": len(runs)
            }
        
        @self.app.delete("/tests/runs/{run_id}")
        async def cancel_test_run(run_id: str):
            """Cancel a running test."""
            HTTP_REQUESTS_TOTAL.labels(method="DELETE", endpoint="/tests/runs", status_code=200).inc()
            
            with self._lock:
                test_run = self.test_runs.get(run_id)
                process = self.test_processes.get(run_id)
            
            if not test_run:
                raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")
            
            if test_run.status != TestRunStatus.RUNNING:
                raise HTTPException(
                    status_code=400,
                    detail=f"Test run {run_id} is not running (status: {test_run.status.value})"
                )
            
            if process:
                try:
                    process.terminate()
                    # Wait a bit for graceful termination
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                except Exception as e:
                    logger.error(f"Error cancelling test run {run_id}: {e}")
            
            with self._lock:
                test_run.status = TestRunStatus.CANCELLED
                test_run.completed_at = datetime.now()
                if run_id in self.test_processes:
                    del self.test_processes[run_id]
            
            return {
                "run_id": run_id,
                "status": test_run.status.value,
                "message": "Test run cancelled"
            }
    
    async def _run_tests(self, run_id: str, test_path: Optional[str], test_name: Optional[str]):
        """Run tests in background."""
        with self._lock:
            test_run = self.test_runs[run_id]
            test_run.status = TestRunStatus.RUNNING
        
        logger.info(f"Starting test run {run_id}: path={test_path}, name={test_name}")
        
        # Build pytest command
        cmd = ["poetry", "run", "pytest", "-v"]
        
        if test_path:
            cmd.append(test_path)
        else:
            # Default to integration tests directory
            cmd.append("tests/integration/")
        
        if test_name:
            cmd.append(f"-k{test_name}")
        
        # Add output options
        cmd.extend(["--tb=short", "-v"])
        
        try:
            # Start subprocess
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            with self._lock:
                self.test_processes[run_id] = process
            
            # Read output line by line
            output_lines = []
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    line = line.rstrip()
                    output_lines.append(line)
                    with self._lock:
                        if run_id in self.test_logs:
                            self.test_logs[run_id].append(line)
                    logger.debug(f"Test {run_id}: {line}")
            
            # Wait for process to complete
            exit_code = process.wait()
            output = "\n".join(output_lines)
            
            # Update test run status
            with self._lock:
                test_run = self.test_runs[run_id]
                test_run.completed_at = datetime.now()
                test_run.exit_code = exit_code
                test_run.output = output
                
                if exit_code == 0:
                    test_run.status = TestRunStatus.COMPLETED
                else:
                    test_run.status = TestRunStatus.FAILED
                    test_run.error = f"Tests failed with exit code {exit_code}"
                
                if run_id in self.test_processes:
                    del self.test_processes[run_id]
            
            logger.info(f"Test run {run_id} completed with exit code {exit_code}")
            
        except Exception as e:
            logger.error(f"Error running tests for {run_id}: {e}", exc_info=True)
            with self._lock:
                test_run = self.test_runs[run_id]
                test_run.completed_at = datetime.now()
                test_run.status = TestRunStatus.FAILED
                test_run.error = str(e)
                if run_id in self.test_processes:
                    del self.test_processes[run_id]
    
    def run(self, host: str = "0.0.0.0"):
        """Run the FastAPI server."""
        logger.info(f"Starting integration test service on {host}:{self.port}")
        uvicorn.run(self.app, host=host, port=self.port, log_level="info")
