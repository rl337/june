#!/usr/bin/env python3
"""
June Agent Loop - Continuously picks up tasks from TODO service and executes them.

This script continuously works through the TODO task queue by:
1. Querying available tasks (or continuing in-progress tasks)
2. Reserving tasks via MCP client
3. Executing tasks using June's Gateway API and Qwen3-30B-A3B
4. Completing or unlocking tasks based on outcome

Based on cursor-agent-loop.sh pattern but adapted for June's architecture.

Usage:
    python3 june-agent-loop.py [--max-loops N] [--sleep-interval SECONDS]

Environment Variables:
    JUNE_AGENT_ID: Agent identifier (default: 'june-agent')
    JUNE_PROJECT_ID: Project ID to filter tasks (optional)
    JUNE_AGENT_TYPE: Agent type - 'implementation' or 'breakdown' (default: 'implementation')
    JUNE_SLEEP_INTERVAL: Sleep interval between iterations in seconds (default: 60)
    TODO_SERVICE_URL: TODO MCP Service URL (default: 'http://localhost:8004')
    GATEWAY_URL: June Gateway service URL (default: 'http://localhost:8000')
    JUNE_USER_ID: User ID for Gateway authentication (default: 'june-agent')
    LOG_LEVEL: Logging level (default: 'INFO')
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import subprocess
from threading import Lock
from datetime import datetime, timedelta

# Add packages to path for imports
sys.path.insert(0, str(Path(__file__).parent / "packages" / "june-mcp-client"))

try:
    from june_mcp_client import MCPClient, MCPServiceError, MCPConnectionError
except ImportError:
    print("ERROR: june_mcp_client not found. Install with: pip install -e packages/june-mcp-client/")
    sys.exit(1)

import httpx

# Setup logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
AGENT_ID = os.getenv("JUNE_AGENT_ID", "june-agent")
PROJECT_ID = os.getenv("JUNE_PROJECT_ID")
AGENT_TYPE = os.getenv("JUNE_AGENT_TYPE", "implementation")
SLEEP_INTERVAL = int(os.getenv("JUNE_SLEEP_INTERVAL", "60"))
TODO_SERVICE_URL = os.getenv("TODO_SERVICE_URL", "http://localhost:8004")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000").rstrip("/")
JUNE_USER_ID = os.getenv("JUNE_USER_ID", "june-agent")

# Performance optimizations: Shared HTTP client with connection pooling
_http_client: Optional[httpx.Client] = None
_http_client_lock = Lock()

# Auth token caching (refresh 5 minutes before expiry)
_cached_token: Optional[str] = None
_token_expiry: Optional[datetime] = None
_token_lock = Lock()


def get_http_client() -> httpx.Client:
    """Get shared HTTP client with connection pooling for performance."""
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            if _http_client is None:
                # Create client with connection pooling and keep-alive
                _http_client = httpx.Client(
                    timeout=httpx.Timeout(300.0, connect=10.0),
                    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                    http2=True  # Enable HTTP/2 for better performance
                )
                logger.debug("Created shared HTTP client with connection pooling")
    return _http_client


def get_auth_token() -> str:
    """
    Get authentication token from Gateway with caching for performance.
    
    Token is cached and refreshed 5 minutes before expiry to reduce API calls.
    
    Returns:
        JWT token for Gateway API
    """
    global _cached_token, _token_expiry
    
    with _token_lock:
        # Check if cached token is still valid (refresh 5 minutes before expiry)
        now = datetime.now()
        if _cached_token and _token_expiry and now < (_token_expiry - timedelta(minutes=5)):
            logger.debug("Using cached auth token")
            return _cached_token
        
        # Fetch new token
        try:
            client = get_http_client()
            response = client.post(
                f"{GATEWAY_URL}/auth/token",
                params={"user_id": JUNE_USER_ID}
            )
            response.raise_for_status()
            token = response.json()["access_token"]
            
            # Cache token (assume 24 hour expiry, refresh after 23 hours)
            _cached_token = token
            _token_expiry = now + timedelta(hours=23)
            
            logger.debug("Fetched and cached new auth token")
            return token
        except Exception as e:
            logger.error(f"Failed to get auth token: {e}")
            # Clear cache on error
            _cached_token = None
            _token_expiry = None
            raise


def execute_task_with_june(task_context: Dict[str, Any], gateway_token: str) -> Dict[str, Any]:
    """
    Execute a task using June's Gateway API and Qwen3-30B-A3B.
    
    Args:
        task_context: Task context from MCP service
        gateway_token: JWT token for Gateway API
        
    Returns:
        Execution result with success status and output
    """
    task = task_context.get("task", {})
    project = task_context.get("project", {})
    project_path = project.get("local_path", "")
    
    # Build prompt for June agent
    title = task.get("title", "Unknown Task")
    instruction = task.get("task_instruction", "")
    verification = task.get("verification_instruction", "")
    
    prompt = f"""Work on task: {title}

TASK INSTRUCTIONS:
{instruction}

VERIFICATION CRITERIA:
{verification}

IMPORTANT:
- Use MCP TODO service tools directly (mcp_todo_* functions via MCP client)
- Check git status in: {project_path if project_path else 'current directory'}
- Add progress updates using mcp_todo_add_task_update() as you work
- When complete, call mcp_todo_complete_task(task_id={task.get('id')}, agent_id='{AGENT_ID}', notes='...')
- If you cannot complete, call mcp_todo_unlock_task(task_id={task.get('id')}, agent_id='{AGENT_ID}') - THIS IS MANDATORY

CRITICAL: DO NOT create scripts or make HTTP requests - use MCP tools directly!

Execute this task using your code execution capabilities, file operations, and git commands.
"""
    
    try:
        # Use shared HTTP client with connection pooling for better performance
        client = get_http_client()
        response = client.post(
            f"{GATEWAY_URL}/chat",
            json={
                "type": "text",
                "text": prompt
            },
            headers={
                "Authorization": f"Bearer {gateway_token}"
            }
        )
        response.raise_for_status()
        result = response.json()
        
        return {
            "success": True,
            "output": result.get("text", ""),
            "response": result
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Gateway API error: {e.response.status_code} - {e.response.text}")
        return {
            "success": False,
            "error": f"HTTP {e.response.status_code}: {e.response.text}",
            "output": ""
        }
    except httpx.RequestError as e:
        logger.error(f"Gateway connection error: {e}")
        return {
            "success": False,
            "error": f"Connection error: {e}",
            "output": ""
        }
    except Exception as e:
        logger.error(f"Unexpected error executing task: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "output": ""
        }


def check_git_status(project_path: str) -> Optional[str]:
    """
    Check git status in project directory.
    
    Args:
        project_path: Path to project directory
        
    Returns:
        Git status output or None if not a git repo
    """
    if not project_path or not os.path.exists(project_path):
        return None
    
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    return None


async def run_agent_loop(max_loops: Optional[int] = None, sleep_interval: Optional[int] = None):
    """
    Main agent loop that continuously processes tasks.
    
    Args:
        max_loops: Maximum number of iterations (None for infinite loop)
        sleep_interval: Sleep interval between iterations (None uses global SLEEP_INTERVAL)
    """
    # Use provided sleep interval or fall back to global
    actual_sleep_interval = sleep_interval if sleep_interval is not None else SLEEP_INTERVAL
    logger.info("Starting June agent loop")
    logger.info(f"Agent ID: {AGENT_ID}")
    logger.info(f"Project ID: {PROJECT_ID or 'all projects'}")
    logger.info(f"Agent Type: {AGENT_TYPE}")
    logger.info(f"Sleep interval: {actual_sleep_interval}s")
    logger.info(f"TODO Service URL: {TODO_SERVICE_URL}")
    logger.info(f"Gateway URL: {GATEWAY_URL}")
    
    if max_loops:
        logger.info(f"Maximum loops: {max_loops}")
    else:
        logger.info("Running indefinitely (no loop limit)")
    
    # Initialize MCP client
    try:
        mcp_client = MCPClient(base_url=TODO_SERVICE_URL)
        logger.info("MCP client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MCP client: {e}", exc_info=True)
        sys.exit(1)
    
    # Get Gateway auth token
    try:
        gateway_token = get_auth_token()
        logger.info("Gateway authentication successful")
    except Exception as e:
        logger.error(f"Failed to authenticate with Gateway: {e}", exc_info=True)
        sys.exit(1)
    
    loop_count = 0
    task_id = None
    
    try:
        while True:
            loop_count += 1
            task_id = None
            
            # Check if we've reached the maximum loop count
            if max_loops and loop_count > max_loops:
                logger.info(f"Reached maximum loop count of {max_loops}. Exiting.")
                break
            
            logger.info(f"Starting task iteration #{loop_count}{f' / {max_loops}' if max_loops else ''}...")
            
            # STEP 1: Check for existing in-progress tasks FIRST
            logger.info("Checking for in-progress tasks...")
            try:
                in_progress_tasks = mcp_client.query_tasks(
                    task_status="in_progress",
                    agent_id=AGENT_ID,
                    limit=10
                )
                
                if in_progress_tasks and len(in_progress_tasks) > 0:
                    task_id = in_progress_tasks[0].id
                    logger.info(f"Found in-progress task: {task_id}")
                else:
                    # STEP 2: No in-progress tasks, find available task
                    logger.info("No in-progress tasks, searching for available tasks...")
                    
                    available_tasks = mcp_client.list_available_tasks(
                        agent_type=AGENT_TYPE,
                        project_id=int(PROJECT_ID) if PROJECT_ID else None,
                        limit=1
                    )
                    
                    if not available_tasks or len(available_tasks) == 0:
                        logger.warning(f"No available tasks found. Sleeping {actual_sleep_interval}s before retry...")
                        await asyncio.sleep(actual_sleep_interval)
                        continue
                    
                    task_id = available_tasks[0].id
                    logger.info(f"Found available task: {task_id}")
                    
                    # Reserve the task
                    try:
                        task_context = mcp_client.reserve_task(
                            task_id=task_id,
                            agent_id=AGENT_ID
                        )
                        logger.info(f"Successfully reserved task {task_id}")
                    except MCPServiceError as e:
                        logger.warning(f"Failed to reserve task {task_id} (may have been taken by another agent): {e}")
                        await asyncio.sleep(actual_sleep_interval)
                        continue
                
            except (MCPConnectionError, Exception) as e:
                logger.error(f"Error querying tasks: {e}", exc_info=True)
                await asyncio.sleep(actual_sleep_interval)
                continue
            
            # STEP 3: Get task context
            logger.info(f"Getting context for task {task_id}...")
            try:
                task_context = mcp_client.get_task_context(task_id=task_id)
                
                # Check for stale warning
                stale_warning = task_context.get("stale_warning")
                if stale_warning:
                    logger.warning(f"?? Picking up stale task: {stale_warning.get('message', 'Unknown')}")
                    mcp_client.add_task_update(
                        task_id=task_id,
                        agent_id=AGENT_ID,
                        content=f"Resuming stale task. Verifying previous work.",
                        update_type="progress"
                    )
                
                # Check git status
                project_path = task_context.get("project", {}).get("local_path", "")
                git_status = check_git_status(project_path)
                if git_status:
                    logger.info(f"Found uncommitted changes:\n{git_status}")
                    mcp_client.add_task_update(
                        task_id=task_id,
                        agent_id=AGENT_ID,
                        content=f"Found uncommitted changes from previous work. Reviewing and continuing.",
                        update_type="progress"
                    )
                
                # Review previous updates
                updates = task_context.get("updates", [])
                if updates:
                    logger.info(f"Found {len(updates)} previous update(s)")
                    for update in updates[-5:]:  # Last 5 updates
                        logger.info(f"  - [{update.get('update_type', 'unknown')}] {update.get('content', '')[:100]}")
                
            except (MCPServiceError, MCPConnectionError) as e:
                logger.error(f"Failed to get task context for task {task_id}: {e}")
                try:
                    mcp_client.unlock_task(task_id=task_id, agent_id=AGENT_ID)
                except Exception:
                    pass
                await asyncio.sleep(actual_sleep_interval)
                continue
            
            # STEP 4: Execute task using June Gateway
            logger.info(f"Executing task {task_id} with June Gateway API...")
            
            try:
                # Add progress update
                mcp_client.add_task_update(
                    task_id=task_id,
                    agent_id=AGENT_ID,
                    content="Starting task execution with June Gateway API and Qwen3-30B-A3B",
                    update_type="progress"
                )
                
                # Execute task
                execution_result = execute_task_with_june(task_context, gateway_token)
                
                if execution_result["success"]:
                    logger.info(f"Task {task_id} executed successfully")
                    
                    # Try to complete the task (June agent should have done this via MCP, but we do it here as backup)
                    try:
                        mcp_client.complete_task(
                            task_id=task_id,
                            agent_id=AGENT_ID,
                            notes="Completed via june-agent-loop.py"
                        )
                        logger.info(f"Task {task_id} marked as complete")
                    except MCPServiceError as e:
                        # Task may have already been completed by June agent
                        logger.warning(f"Task {task_id} may have already been completed: {e}")
                    
                    # Check if we've reached the maximum loop count before sleeping
                    if max_loops and loop_count >= max_loops:
                        logger.info(f"Completed {loop_count} iteration(s). Exiting.")
                        break
                    
                    logger.info(f"Sleeping {actual_sleep_interval}s before next iteration...")
                    await asyncio.sleep(actual_sleep_interval)
                else:
                    # Execution failed
                    error_msg = execution_result.get("error", "Unknown error")
                    logger.error(f"Task execution failed: {error_msg}")
                    
                    # MANDATORY: Unlock task on error
                    try:
                        mcp_client.add_task_update(
                            task_id=task_id,
                            agent_id=AGENT_ID,
                            content=f"Task execution failed: {error_msg}. Unlocking task.",
                            update_type="blocker"
                        )
                        mcp_client.unlock_task(task_id=task_id, agent_id=AGENT_ID)
                        logger.info(f"Task {task_id} unlocked due to execution failure")
                    except Exception as e:
                        logger.error(f"Failed to unlock task {task_id}: {e}", exc_info=True)
                    
                    # Determine if we should exit or continue
                    # Continue on recoverable errors, exit on unrecoverable errors
                    if "Connection error" in error_msg or "timeout" in error_msg.lower():
                        logger.warning("Recoverable error detected, continuing to next iteration...")
                        await asyncio.sleep(actual_sleep_interval)
                        continue
                    else:
                        logger.error("Unrecoverable error detected, exiting loop")
                        sys.exit(1)
                        
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                if task_id:
                    try:
                        mcp_client.unlock_task(task_id=task_id, agent_id=AGENT_ID)
                    except Exception:
                        pass
                raise
            except Exception as e:
                logger.error(f"Unexpected error executing task {task_id}: {e}", exc_info=True)
                
                # MANDATORY: Unlock task on error
                if task_id:
                    try:
                        mcp_client.unlock_task(task_id=task_id, agent_id=AGENT_ID)
                    except Exception as e2:
                        logger.error(f"Failed to unlock task {task_id}: {e2}", exc_info=True)
                
                # Continue on recoverable errors, exit on unrecoverable
                if isinstance(e, (MCPConnectionError, httpx.RequestError)):
                    logger.warning("Recoverable error detected, continuing to next iteration...")
                    await asyncio.sleep(actual_sleep_interval)
                    continue
                else:
                    logger.error("Unrecoverable error detected, exiting loop")
                    sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Agent loop interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in agent loop: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Final cleanup
        if task_id:
            try:
                mcp_client.unlock_task(task_id=task_id, agent_id=AGENT_ID)
            except Exception:
                pass
        
        # Close HTTP client to free resources
        global _http_client
        if _http_client is not None:
            try:
                _http_client.close()
                logger.debug("Closed shared HTTP client")
            except Exception:
                pass
        
        logger.info(f"Agent loop finished. Completed {loop_count} iteration(s).")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="June Agent Loop - Continuously process tasks from TODO service"
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=None,
        help="Maximum number of iterations (default: infinite)"
    )
    parser.add_argument(
        "--sleep-interval",
        type=int,
        default=None,
        help=f"Sleep interval between iterations in seconds (default: {SLEEP_INTERVAL} or JUNE_SLEEP_INTERVAL env var)"
    )
    
    args = parser.parse_args()
    
    # Override sleep interval if provided
    sleep_interval = args.sleep_interval if args.sleep_interval else None
    
    # Run the loop
    try:
        asyncio.run(run_agent_loop(max_loops=args.max_loops, sleep_interval=sleep_interval))
    except KeyboardInterrupt:
        logger.info("Exiting...")
        sys.exit(0)


if __name__ == "__main__":
    main()
