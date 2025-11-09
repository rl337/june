#!/usr/bin/env python3
"""
June Agent Service - Orchestrates task execution with Qwen3-30B-A3B.

This service continuously picks up tasks from the TODO service and uses
Qwen3-30B-A3B for planning, execution, and verification.

Usage:
    python3 main.py [--max-loops N] [--sleep-interval SECONDS]

Environment Variables:
    JUNE_AGENT_ID: Agent identifier (default: 'june-agent')
    JUNE_PROJECT_ID: Project ID to filter tasks (optional)
    JUNE_AGENT_TYPE: Agent type - 'implementation' or 'breakdown' (default: 'implementation')
    JUNE_SLEEP_INTERVAL: Sleep interval between iterations in seconds (default: 60)
    TODO_SERVICE_URL: TODO MCP Service URL (default: 'http://localhost:8004')
    QWEN3_MODEL_NAME: Qwen3 model name (default: 'Qwen/Qwen2.5-72B-Instruct')
    LOG_LEVEL: Logging level (default: 'INFO')
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import traceback

# Add packages to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "packages" / "june-mcp-client"))
sys.path.insert(0, str(project_root / "packages" / "inference-core"))
sys.path.insert(0, str(project_root / "packages" / "june-agent-state"))

try:
    from june_mcp_client import MCPClient, MCPServiceError, MCPConnectionError
except ImportError:
    print("ERROR: june_mcp_client not found. Install with: pip install -e packages/june-mcp-client/")
    sys.exit(1)

try:
    from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
    from inference_core.strategies import InferenceRequest, InferenceResponse
except ImportError:
    print("ERROR: inference_core not found. Install with: pip install -e packages/inference-core/")
    sys.exit(1)

# Setup logging first (before imports that might log)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

try:
    from june_agent_state import AgentStateStorage
except ImportError:
    logger.warning("june-agent-state not available, plan persistence will be disabled")
    AgentStateStorage = None

# Import planning system
from planning import PlanningSystem

# Configuration
AGENT_ID = os.getenv("JUNE_AGENT_ID", "june-agent")
PROJECT_ID = os.getenv("JUNE_PROJECT_ID")
AGENT_TYPE = os.getenv("JUNE_AGENT_TYPE", "implementation")
SLEEP_INTERVAL = int(os.getenv("JUNE_SLEEP_INTERVAL", "60"))
TODO_SERVICE_URL = os.getenv("TODO_SERVICE_URL", "http://localhost:8004")
QWEN3_MODEL_NAME = os.getenv("QWEN3_MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
QWEN3_DEVICE = os.getenv("QWEN3_DEVICE", "cuda" if os.getenv("CUDA_VISIBLE_DEVICES") else "cpu")

# Global Qwen3 strategy instance
_qwen3_strategy: Optional[Qwen3LlmStrategy] = None


def get_qwen3_strategy() -> Qwen3LlmStrategy:
    """Get or initialize Qwen3 LLM strategy."""
    global _qwen3_strategy
    if _qwen3_strategy is None:
        logger.info(f"Initializing Qwen3 strategy with model: {QWEN3_MODEL_NAME}")
        _qwen3_strategy = Qwen3LlmStrategy(
            model_name=QWEN3_MODEL_NAME,
            device=QWEN3_DEVICE
        )
        logger.info("Warming up Qwen3 model...")
        _qwen3_strategy.warmup()
        logger.info("Qwen3 model ready")
    return _qwen3_strategy


def call_qwen3(prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 4096, temperature: float = 0.7) -> str:
    """
    Call Qwen3 model with a prompt.
    
    Args:
        prompt: User prompt
        system_prompt: Optional system prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        
    Returns:
        Generated text response
    """
    try:
        strategy = get_qwen3_strategy()
        
        # Format full prompt with system message if provided
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt
        
        request = InferenceRequest(
            payload={
                "prompt": full_prompt,
                "params": {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "top_p": 0.9
                }
            }
        )
        
        response = strategy.infer(request)
        
        if isinstance(response.payload, dict):
            return response.payload.get("text", "")
        return str(response.payload)
        
    except Exception as e:
        logger.error(f"Qwen3 inference error: {e}", exc_info=True)
        raise


def plan_task_with_qwen3(task_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use Qwen3 to analyze task and create execution plan.
    
    Args:
        task_context: Task context from MCP service
        
    Returns:
        Execution plan with steps
    """
    task = task_context.get("task", {})
    project = task_context.get("project", {})
    project_path = project.get("local_path", "")
    
    title = task.get("title", "Unknown Task")
    instruction = task.get("task_instruction", "")
    verification = task.get("verification_instruction", "")
    updates = task_context.get("updates", [])
    
    # Build planning prompt
    planning_prompt = f"""You are an autonomous agent working on a software development task.

TASK: {title}

TASK INSTRUCTIONS:
{instruction}

VERIFICATION CRITERIA:
{verification}

PROJECT PATH: {project_path if project_path else 'Not specified'}

PREVIOUS WORK:
{chr(10).join([f"- [{u.get('update_type', 'unknown')}]: {u.get('content', '')[:200]}" for u in updates[-5:]]) if updates else "No previous work found."}

Your job is to create a detailed execution plan for this task. The plan should:
1. Analyze what needs to be done
2. Break it down into concrete steps
3. Identify files that need to be created/modified
4. Specify what commands need to be run
5. Identify what tests need to be written/run

Return your response as a JSON object with this structure:
{{
    "analysis": "Brief analysis of what needs to be done",
    "steps": [
        {{
            "step_number": 1,
            "description": "Description of the step",
            "action": "create|modify|run|test",
            "target": "file path or command",
            "details": "Additional details about what to do"
        }}
    ],
    "estimated_complexity": "low|medium|high",
    "dependencies": ["list", "of", "dependencies"]
}}

Make sure to:
- Check git status first to see existing changes
- Review any existing code in the project
- Create tests before implementation (TDD)
- Run tests after implementation
- Commit changes with meaningful messages
"""

    logger.info("Planning task with Qwen3...")
    response = call_qwen3(
        planning_prompt,
        system_prompt="You are a software development agent that creates detailed, executable plans for coding tasks. Always follow test-driven development (TDD) principles.",
        max_tokens=2048,
        temperature=0.3  # Lower temperature for planning
    )
    
    # Try to parse JSON from response
    try:
        # Extract JSON from response if it's wrapped in markdown or other text
        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            response = response[json_start:json_end].strip()
        elif "```" in response:
            json_start = response.find("```") + 3
            json_end = response.find("```", json_start)
            response = response[json_start:json_end].strip()
        
        plan = json.loads(response)
        logger.info(f"Generated plan with {len(plan.get('steps', []))} steps")
        return plan
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON plan, using raw response")
        return {
            "analysis": response[:500],
            "steps": [{"step_number": 1, "description": "Execute task", "action": "run", "target": "implementation"}],
            "estimated_complexity": "medium",
            "dependencies": []
        }


def generate_code_with_qwen3(task_context: Dict[str, Any], file_path: str, details: str) -> str:
    """
    Use Qwen3 to generate code for a file.
    
    Args:
        task_context: Task context
        file_path: Target file path
        details: Details about what code to generate
        
    Returns:
        Generated code content
    """
    task = task_context.get("task", {})
    project = task_context.get("project", {})
    project_path = project.get("local_path", "")
    
    code_generation_prompt = f"""You are a software developer. Generate code for the following file.

TASK: {task.get('title', '')}
INSTRUCTION: {task.get('task_instruction', '')}

FILE PATH: {file_path}
DETAILS: {details}

PROJECT PATH: {project_path}

Generate complete, working code for this file. Follow best practices:
- Include proper imports
- Add docstrings and comments
- Handle errors appropriately
- Follow the project's coding style
- Write testable code

Return ONLY the code content, no explanations or markdown formatting.
"""

    logger.info(f"Generating code for {file_path} with Qwen3...")
    code = call_qwen3(
        code_generation_prompt,
        system_prompt="You are an expert Python developer. Generate clean, production-ready code.",
        max_tokens=4096,
        temperature=0.2  # Lower temperature for code generation
    )
    
    # Clean up response (remove markdown code blocks if present)
    if "```python" in code:
        code_start = code.find("```python") + 9
        code_end = code.find("```", code_start)
        code = code[code_start:code_end].strip()
    elif "```" in code:
        code_start = code.find("```") + 3
        code_end = code.find("```", code_start)
        code = code[code_start:code_end].strip()
    
    return code


def execute_plan_step(step: Dict[str, Any], project_path: str, mcp_client: MCPClient, task_id: int, task_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a single step from the plan.
    
    Args:
        step: Step definition from plan
        project_path: Path to project directory
        mcp_client: MCP client for updates
        task_id: Task ID
        task_context: Full task context
        
    Returns:
        Execution result
    """
    action = step.get("action", "run")
    target = step.get("target", "")
    description = step.get("description", "")
    details = step.get("details", "")
    
    logger.info(f"Executing step: {action} -> {target}")
    
    try:
        if action == "run":
            # Execute command
            if not project_path:
                return {"success": False, "error": "Project path not specified"}
            
            # Run command in project directory
            result = subprocess.run(
                target.split(),
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        
        elif action == "test":
            # Run tests
            if not project_path:
                return {"success": False, "error": "Project path not specified"}
            
            # Determine test command based on target
            if target.endswith(".py"):
                test_cmd = ["python3", "-m", "pytest", target, "-v"]
            elif target.startswith("test_"):
                test_cmd = ["./run_checks.sh"] if os.path.exists(os.path.join(project_path, "run_checks.sh")) else ["python3", "-m", "pytest", target]
            else:
                test_cmd = ["./run_checks.sh"] if os.path.exists(os.path.join(project_path, "run_checks.sh")) else ["python3", "-m", "pytest", "-v"]
            
            result = subprocess.run(
                test_cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for tests
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        
        elif action in ["create", "modify"]:
            # File operations - generate code with Qwen3
            if not project_path:
                return {"success": False, "error": "Project path not specified"}
            
            file_path = os.path.join(project_path, target) if not os.path.isabs(target) else target
            file_dir = os.path.dirname(file_path)
            
            # Create directory if needed
            if file_dir and not os.path.exists(file_dir):
                os.makedirs(file_dir, exist_ok=True)
            
            # Generate code with Qwen3
            try:
                code_content = generate_code_with_qwen3(task_context, target, details)
                
                # Write file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code_content)
                
                mcp_client.add_task_update(
                    task_id=task_id,
                    agent_id=AGENT_ID,
                    content=f"Generated and wrote code to {target} ({len(code_content)} chars)",
                    update_type="progress"
                )
                
                return {
                    "success": True,
                    "message": f"File {target} created/modified",
                    "file_path": file_path,
                    "code_length": len(code_content)
                }
            except Exception as e:
                logger.error(f"Error generating code: {e}", exc_info=True)
                return {"success": False, "error": f"Code generation failed: {str(e)}"}
        
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
            
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except Exception as e:
        logger.error(f"Error executing step: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def execute_task_with_qwen3(task_context: Dict[str, Any], mcp_client: MCPClient, task_id: int, planning_system: Optional[PlanningSystem] = None) -> Dict[str, Any]:
    """
    Execute a task using Qwen3 for planning and execution.
    
    Args:
        task_context: Task context from MCP service
        mcp_client: MCP client for TODO operations
        task_id: Task ID
        planning_system: PlanningSystem instance (optional)
        
    Returns:
        Execution result
    """
    task = task_context.get("task", {})
    project = task_context.get("project", {})
    project_path = project.get("local_path", "")
    plan_id = None
    
    try:
        # Step 1: Create comprehensive plan using PlanningSystem
        if planning_system:
            logger.info("Step 1: Creating comprehensive execution plan...")
            plan_result = await planning_system.create_plan(task_context, AGENT_ID)
            plan_id = plan_result.get("plan_id")
            
            analysis = plan_result.get("analysis", {})
            strategy = plan_result.get("strategy", {})
            execution_plan = plan_result.get("execution_plan", [])
            subtask_ids = plan_result.get("subtask_ids", [])
            
            # Use execution plan from planning system
            plan = {
                "analysis": analysis.get("complexity_reasoning", ""),
                "steps": execution_plan,
                "estimated_complexity": analysis.get("complexity", "medium"),
                "dependencies": analysis.get("dependencies", []),
                "strategy": strategy.get("approach", "direct_implementation")
            }
            
            update_msg = f"Created comprehensive plan: {len(execution_plan)} steps, complexity={analysis.get('complexity')}, strategy={strategy.get('approach')}"
            if subtask_ids:
                update_msg += f", created {len(subtask_ids)} subtasks"
            if plan_result.get("similar_plan_reused"):
                update_msg += " (reused similar successful plan)"
            
            mcp_client.add_task_update(
                task_id=task_id,
                agent_id=AGENT_ID,
                content=update_msg,
                update_type="progress"
            )
        else:
            # Fallback to basic planning
            logger.info("Step 1: Creating execution plan with Qwen3 (basic)...")
            plan = plan_task_with_qwen3(task_context)
            
            mcp_client.add_task_update(
                task_id=task_id,
                agent_id=AGENT_ID,
                content=f"Created execution plan with {len(plan.get('steps', []))} steps. Analysis: {plan.get('analysis', '')[:200]}",
                update_type="progress"
            )
        
        # Step 2: Execute plan steps
        logger.info("Step 2: Executing plan steps...")
        execution_results = []
        
        # Get steps from execution plan if available, otherwise use legacy format
        steps = plan.get("steps", [])
        if steps and isinstance(steps[0], dict) and "step_number" in steps[0]:
            # New format from PlanningSystem
            for step in steps[:20]:  # Limit to 20 steps per task
                # Convert to legacy format for execute_plan_step
                legacy_step = {
                    "action": step.get("action", "run"),
                    "target": step.get("target", ""),
                    "description": step.get("description", step.get("name", "")),
                    "details": step.get("details", "")
                }
                result = execute_plan_step(legacy_step, project_path, mcp_client, task_id, task_context)
                execution_results.append({
                    "step": step.get("description", step.get("name", "")),
                    "result": result
                })
                
                # Add update for significant steps
                if not result.get("success") and result.get("error"):
                    mcp_client.add_task_update(
                        task_id=task_id,
                        agent_id=AGENT_ID,
                        content=f"Step '{step.get('description', step.get('name', ''))}' failed: {result.get('error', 'Unknown error')}",
                        update_type="blocker"
                    )
        else:
            # Legacy format
            for step in steps[:20]:  # Limit to 20 steps per task
                result = execute_plan_step(step, project_path, mcp_client, task_id, task_context)
                execution_results.append({
                    "step": step.get("description", ""),
                    "result": result
                })
                
                # Add update for significant steps
                if not result.get("success") and result.get("error"):
                    mcp_client.add_task_update(
                        task_id=task_id,
                        agent_id=AGENT_ID,
                        content=f"Step '{step.get('description', '')}' failed: {result.get('error', 'Unknown error')}",
                        update_type="blocker"
                    )
        
        # Step 3: Verify with Qwen3
        logger.info("Step 3: Verifying task completion with Qwen3...")
        verification_prompt = f"""Review the task execution and verify if it's complete:

TASK: {task.get('title', '')}
INSTRUCTION: {task.get('task_instruction', '')}
VERIFICATION: {task.get('verification_instruction', '')}

EXECUTION RESULTS:
{json.dumps(execution_results, indent=2)}

Has the task been completed successfully? Review all steps and verify that:
1. The implementation matches the task instructions
2. All verification criteria are met
3. Tests pass (if applicable)
4. Code is properly committed (if applicable)

Respond with JSON:
{{
    "verified": true/false,
    "reason": "Brief explanation",
    "missing_steps": ["list of any missing steps"],
    "next_actions": ["any remaining actions needed"]
}}
"""

        verification_response = call_qwen3(
            verification_prompt,
            system_prompt="You are a code reviewer verifying task completion.",
            max_tokens=1024,
            temperature=0.2
        )
        
        # Parse verification response
        try:
            if "```json" in verification_response:
                json_start = verification_response.find("```json") + 7
                json_end = verification_response.find("```", json_start)
                verification_response = verification_response[json_start:json_end].strip()
            
            verification = json.loads(verification_response)
        except:
            verification = {"verified": False, "reason": "Could not parse verification response"}
        
        success = verification.get("verified", False)
        
        # Record plan execution for learning
        if planning_system and plan_id:
            await planning_system.record_plan_execution(plan_id, success)
        
        return {
            "success": success,
            "plan": plan,
            "execution_results": execution_results,
            "verification": verification,
            "plan_id": plan_id
        }
        
    except Exception as e:
        logger.error(f"Error executing task with Qwen3: {e}", exc_info=True)
        
        # Record plan failure for learning
        if planning_system and plan_id:
            await planning_system.record_plan_execution(plan_id, False)
        
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


async def run_agent_loop(max_loops: Optional[int] = None, sleep_interval: Optional[int] = None):
    """
    Main agent loop that continuously processes tasks.
    
    Args:
        max_loops: Maximum number of iterations (None for infinite loop)
        sleep_interval: Sleep interval between iterations
    """
    actual_sleep_interval = sleep_interval if sleep_interval is not None else SLEEP_INTERVAL
    
    logger.info("Starting June Agent Service")
    logger.info(f"Agent ID: {AGENT_ID}")
    logger.info(f"Project ID: {PROJECT_ID or 'all projects'}")
    logger.info(f"Agent Type: {AGENT_TYPE}")
    logger.info(f"Sleep interval: {actual_sleep_interval}s")
    logger.info(f"TODO Service URL: {TODO_SERVICE_URL}")
    logger.info(f"Qwen3 Model: {QWEN3_MODEL_NAME}")
    logger.info(f"Qwen3 Device: {QWEN3_DEVICE}")
    
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
    
    # Initialize Qwen3 (warmup happens on first use)
    logger.info("Initializing Qwen3 strategy...")
    get_qwen3_strategy()
    logger.info("Qwen3 strategy ready")
    
    # Initialize planning system
    planning_system = None
    storage = None
    if AgentStateStorage:
        try:
            # Initialize storage
            db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/june")
            storage = AgentStateStorage(db_url=db_url)
            await storage.connect()
            logger.info("Agent state storage connected")
            
            # Create planning system
            planning_system = PlanningSystem(
                qwen3_call_fn=call_qwen3,
                mcp_client=mcp_client,
                storage=storage
            )
            logger.info("Planning system initialized with persistence")
        except Exception as e:
            logger.warning(f"Failed to initialize planning system with storage: {e}. Continuing without persistence.")
            planning_system = PlanningSystem(
                qwen3_call_fn=call_qwen3,
                mcp_client=mcp_client,
                storage=None
            )
    else:
        # Create planning system without persistence
        planning_system = PlanningSystem(
            qwen3_call_fn=call_qwen3,
            mcp_client=mcp_client,
            storage=None
        )
        logger.info("Planning system initialized without persistence")
    
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
                if project_path and os.path.exists(project_path):
                    git_status = subprocess.run(
                        ["git", "status", "--short"],
                        cwd=project_path,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if git_status.returncode == 0 and git_status.stdout.strip():
                        logger.info(f"Found uncommitted changes:\n{git_status.stdout}")
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
            
            # STEP 4: Execute task using Qwen3
            logger.info(f"Executing task {task_id} with Qwen3-30B-A3B...")
            
            try:
                # Add progress update
                mcp_client.add_task_update(
                    task_id=task_id,
                    agent_id=AGENT_ID,
                    content="Starting task execution with Qwen3-30B-A3B for planning and execution",
                    update_type="progress"
                )
                
                # Execute task
                execution_result = await execute_task_with_qwen3(task_context, mcp_client, task_id, planning_system)
                
                if execution_result.get("success"):
                    logger.info(f"Task {task_id} executed successfully")
                    
                    # Try to complete the task
                    try:
                        mcp_client.complete_task(
                            task_id=task_id,
                            agent_id=AGENT_ID,
                            notes=f"Completed via June Agent Service with Qwen3-30B-A3B. {execution_result.get('verification', {}).get('reason', '')}"
                        )
                        logger.info(f"Task {task_id} marked as complete")
                    except MCPServiceError as e:
                        # Task may have already been completed
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
                    
                    # Continue on recoverable errors
                    logger.warning("Continuing to next iteration...")
                    await asyncio.sleep(actual_sleep_interval)
                    continue
                        
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
                
                # Continue on recoverable errors
                if isinstance(e, (MCPConnectionError, ConnectionError)):
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
        
        # Close storage connection
        if storage:
            try:
                await storage.disconnect()
                logger.info("Agent state storage disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting storage: {e}")
        
        logger.info(f"Agent loop finished. Completed {loop_count} iteration(s).")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="June Agent Service - Orchestrates task execution with Qwen3-30B-A3B"
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
