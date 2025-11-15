"""Popen-based cursor agent implementation."""

import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, Any, Optional
import uuid

from switchboard.agents.base import Agent, AgentRequest, AgentResponse, AgentStatus

logger = logging.getLogger(__name__)


class PopenCursorAgent(Agent):
    """Agent that executes cursor-agent via subprocess popen."""
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """Initialize popen cursor agent.
        
        Config keys:
            - script_path: Path to the agent script (e.g., telegram_response_agent.sh)
            - script_simple_path: Path to simple agent script (optional)
            - working_directory: Working directory for agent execution
            - timeout: Default timeout in seconds
            - use_simple: Whether to use simple script (default: False)
        """
        super().__init__(agent_id, config)
        self.script_path = Path(config.get("script_path"))
        self.script_simple_path = config.get("script_simple_path")
        if self.script_simple_path:
            self.script_simple_path = Path(self.script_simple_path)
        self.working_directory = config.get("working_directory")
        if self.working_directory:
            self.working_directory = Path(self.working_directory)
        self.default_timeout = config.get("timeout", 3600)
        self.use_simple = config.get("use_simple", False)
        self._running_processes: Dict[str, subprocess.Popen] = {}
    
    @property
    def agent_type(self) -> str:
        return "popen_cursor"
    
    async def execute(
        self,
        request: AgentRequest
    ) -> AsyncIterator[AgentResponse]:
        """Execute cursor-agent via subprocess."""
        request_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        
        # Validate request
        is_valid, error = self.validate_request(request)
        if not is_valid:
            yield AgentResponse(
                request_id=request_id,
                agent_id=request.agent_id,
                session_id=request.session_id,
                status=AgentStatus.FAILED,
                message="",
                error=error,
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
            return
        
        # Determine which script to use
        script_to_use = self.script_simple_path if (self.use_simple and self.script_simple_path) else self.script_path
        
        if not script_to_use.exists():
            yield AgentResponse(
                request_id=request_id,
                agent_id=request.agent_id,
                session_id=request.session_id,
                status=AgentStatus.FAILED,
                message="",
                error=f"Script not found: {script_to_use}",
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
            return
        
        # Build command
        # Script expects: [user_id] [chat_id] "<message>" or just "<message>"
        if request.context and "user_id" in request.context and "chat_id" in request.context:
            cmd = [
                str(script_to_use),
                str(request.context["user_id"]),
                str(request.context["chat_id"]),
                request.message
            ]
        else:
            cmd = [str(script_to_use), request.message]
        
        # Set environment variables from context
        env = dict(os.environ)
        if request.context:
            for key, value in request.context.items():
                if key.startswith("ENV_"):
                    env[key[4:]] = str(value)
                elif key.upper() == "TELEGRAM_USER_ID":
                    env["TELEGRAM_USER_ID"] = str(value)
                elif key.upper() == "TELEGRAM_CHAT_ID":
                    env["TELEGRAM_CHAT_ID"] = str(value)
        
        timeout = request.timeout or self.default_timeout
        
        try:
            self.status = AgentStatus.RUNNING
            self._running_processes[request_id] = None  # Will be set below
            
            # Start process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_directory) if self.working_directory else None,
                env=env
            )
            
            self._running_processes[request_id] = process
            
            # Yield initial status
            yield AgentResponse(
                request_id=request_id,
                agent_id=request.agent_id,
                session_id=request.session_id,
                status=AgentStatus.RUNNING,
                message="Agent execution started",
                started_at=started_at
            )
            
            # Stream output
            output_lines = []
            error_lines = []
            
            # Read stdout and stderr concurrently
            async def read_stream(stream, lines_list):
                async for line in stream:
                    line_text = line.decode('utf-8', errors='replace').rstrip()
                    if line_text:
                        lines_list.append(line_text)
            
            stdout_task = asyncio.create_task(read_stream(process.stdout, output_lines))
            stderr_task = asyncio.create_task(read_stream(process.stderr, error_lines))
            
            # Wait for process with timeout
            try:
                return_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                # Process timed out
                process.kill()
                await process.wait()
                yield AgentResponse(
                    request_id=request_id,
                    agent_id=request.agent_id,
                    session_id=request.session_id,
                    status=AgentStatus.FAILED,
                    message="",
                    error=f"Agent execution timed out after {timeout} seconds",
                    output="\n".join(output_lines),
                    started_at=started_at,
                    completed_at=datetime.utcnow()
                )
                return
            
            # Wait for streams to finish
            await stdout_task
            await stderr_task
            
            output = "\n".join(output_lines)
            error_output = "\n".join(error_lines)
            
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            # Parse output (expecting JSON response)
            try:
                import json
                response_data = json.loads(output) if output else {}
                message = response_data.get("message", output)
            except (json.JSONDecodeError, ValueError):
                message = output
            
            if return_code == 0:
                status = AgentStatus.COMPLETED
                error = None
            else:
                status = AgentStatus.FAILED
                error = error_output or f"Process exited with code {return_code}"
            
            yield AgentResponse(
                request_id=request_id,
                agent_id=request.agent_id,
                session_id=request.session_id,
                status=status,
                message=message,
                output=output,
                error=error,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration
            )
            
        except Exception as e:
            logger.exception(f"Error executing agent {self.agent_id}: {e}")
            yield AgentResponse(
                request_id=request_id,
                agent_id=request.agent_id,
                session_id=request.session_id,
                status=AgentStatus.FAILED,
                message="",
                error=str(e),
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
        finally:
            self.status = AgentStatus.IDLE
            self._running_processes.pop(request_id, None)
    
    async def cancel(self, request_id: str) -> bool:
        """Cancel a running execution."""
        process = self._running_processes.get(request_id)
        if process and process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            self._running_processes.pop(request_id, None)
            return True
        return False
    
    async def get_status(self, request_id: str) -> Optional[AgentResponse]:
        """Get status of a request."""
        process = self._running_processes.get(request_id)
        if process is None:
            return None
        
        if process.returncode is None:
            return AgentResponse(
                request_id=request_id,
                agent_id=self.agent_id,
                session_id="",
                status=AgentStatus.RUNNING,
                message="Execution in progress"
            )
        else:
            return AgentResponse(
                request_id=request_id,
                agent_id=self.agent_id,
                session_id="",
                status=AgentStatus.COMPLETED if process.returncode == 0 else AgentStatus.FAILED,
                message=f"Process completed with code {process.returncode}"
            )

