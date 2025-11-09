#!/usr/bin/env python3
"""
Comprehensive Agent Planning and Task Decomposition System.

This module provides:
1. Task Analysis: Parse instructions, identify dependencies, assess complexity
2. Task Decomposition: Break tasks into subtasks with relationships
3. Execution Planning: Create step-by-step execution plans
4. Strategy Selection: Choose approaches based on task type
5. Learning from Experience: Store and reuse successful plans
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

# Add packages to path for imports
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "packages" / "june-agent-state"))

try:
    from june_agent_state import AgentPlan, AgentStateStorage
except ImportError:
    logging.warning("june-agent-state not available, plan persistence disabled")

logger = logging.getLogger(__name__)


class TaskAnalyzer:
    """Analyzes tasks to extract requirements, dependencies, and complexity."""
    
    def __init__(self, qwen3_call_fn):
        """
        Initialize task analyzer.
        
        Args:
            qwen3_call_fn: Function to call Qwen3 model
        """
        self.qwen3_call = qwen3_call_fn
    
    def analyze_task(self, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a task to extract requirements, dependencies, and complexity.
        
        Args:
            task_context: Full task context from MCP service
            
        Returns:
            Analysis dictionary with:
            - requirements: List of requirements
            - dependencies: List of dependencies
            - prerequisites: List of prerequisites
            - complexity: Complexity assessment (low/medium/high)
            - estimated_effort: Estimated hours
            - required_tools: List of required tools/capabilities
        """
        task = task_context.get("task", {})
        project = task_context.get("project", {})
        updates = task_context.get("updates", [])
        
        title = task.get("title", "Unknown Task")
        instruction = task.get("task_instruction", "")
        verification = task.get("verification_instruction", "")
        task_type = task.get("task_type", "concrete")
        project_path = project.get("local_path", "")
        
        # Build analysis prompt
        analysis_prompt = f"""You are a task analysis system. Analyze the following task and extract key information.

TASK: {title}
TASK TYPE: {task_type}
INSTRUCTION: {instruction}
VERIFICATION: {verification}
PROJECT PATH: {project_path}

PREVIOUS WORK:
{chr(10).join([f"- [{u.get('update_type', 'unknown')}]: {u.get('content', '')[:200]}" for u in updates[-5:]]) if updates else "No previous work."}

Analyze this task and provide:
1. Requirements: What needs to be done (list of specific requirements)
2. Dependencies: What this task depends on (other tasks, features, infrastructure)
3. Prerequisites: What must be in place before starting (tools, access, knowledge)
4. Complexity: Assessment of complexity (low/medium/high) with reasoning
5. Estimated Effort: Hours estimate (be realistic)
6. Required Tools: Tools, libraries, or capabilities needed

Return JSON:
{{
    "requirements": ["requirement1", "requirement2"],
    "dependencies": ["dependency1", "dependency2"],
    "prerequisites": ["prerequisite1", "prerequisite2"],
    "complexity": "low|medium|high",
    "complexity_reasoning": "Explanation of complexity assessment",
    "estimated_effort_hours": 4.0,
    "required_tools": ["tool1", "tool2"],
    "risk_factors": ["risk1", "risk2"]
}}
"""
        
        logger.info("Analyzing task with Qwen3...")
        response = self.qwen3_call(
            analysis_prompt,
            system_prompt="You are an expert task analyst. Provide detailed, accurate analysis of software development tasks.",
            max_tokens=2048,
            temperature=0.3
        )
        
        # Parse JSON response
        try:
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            
            analysis = json.loads(response)
            logger.info(f"Task analysis complete: complexity={analysis.get('complexity')}, effort={analysis.get('estimated_effort_hours')}h")
            return analysis
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse analysis JSON: {e}")
            # Return default analysis
            return {
                "requirements": [instruction[:100]] if instruction else [],
                "dependencies": [],
                "prerequisites": [],
                "complexity": "medium",
                "complexity_reasoning": "Could not parse analysis",
                "estimated_effort_hours": 4.0,
                "required_tools": [],
                "risk_factors": []
            }


class TaskDecomposer:
    """Decomposes large tasks into smaller subtasks."""
    
    def __init__(self, qwen3_call_fn, mcp_client):
        """
        Initialize task decomposer.
        
        Args:
            qwen3_call_fn: Function to call Qwen3 model
            mcp_client: MCP client for creating subtasks
        """
        self.qwen3_call = qwen3_call_fn
        self.mcp_client = mcp_client
    
    def decompose_task(self, task_context: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Decompose a task into smaller subtasks.
        
        Args:
            task_context: Full task context
            analysis: Task analysis result
            
        Returns:
            List of subtask definitions (not yet created in TODO service)
        """
        task = task_context.get("task", {})
        project = task_context.get("project", {})
        
        title = task.get("title", "")
        instruction = task.get("task_instruction", "")
        verification = task.get("verification_instruction", "")
        task_id = task.get("id")
        project_id = project.get("id")
        complexity = analysis.get("complexity", "medium")
        requirements = analysis.get("requirements", [])
        
        # Only decompose if task is complex enough
        if complexity == "low" and len(requirements) <= 3:
            logger.info("Task is simple, skipping decomposition")
            return []
        
        # Build decomposition prompt
        decomposition_prompt = f"""You are a task decomposition system. Break down this task into smaller, manageable subtasks.

PARENT TASK: {title}
INSTRUCTION: {instruction}
VERIFICATION: {verification}
COMPLEXITY: {complexity}
REQUIREMENTS: {json.dumps(requirements, indent=2)}

Break this task into 3-8 subtasks. Each subtask should be:
- Independently completable
- Have clear, specific instructions
- Have clear verification criteria
- Be ordered logically (dependencies considered)

Return JSON:
{{
    "subtasks": [
        {{
            "title": "Subtask title",
            "task_instruction": "Detailed instruction for this subtask",
            "verification_instruction": "How to verify this subtask is complete",
            "estimated_hours": 2.0,
            "dependencies": ["subtask_index_1", "subtask_index_2"],
            "order": 1
        }}
    ],
    "reasoning": "Why this decomposition makes sense"
}}
"""
        
        logger.info("Decomposing task with Qwen3...")
        response = self.qwen3_call(
            decomposition_prompt,
            system_prompt="You are an expert at breaking down complex software tasks into manageable pieces. Create clear, actionable subtasks.",
            max_tokens=4096,
            temperature=0.4
        )
        
        # Parse JSON response
        try:
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            
            decomposition = json.loads(response)
            subtasks = decomposition.get("subtasks", [])
            logger.info(f"Decomposed task into {len(subtasks)} subtasks")
            return subtasks
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse decomposition JSON: {e}")
            return []
    
    def create_subtasks(self, parent_task_id: int, agent_id: str, subtask_definitions: List[Dict[str, Any]], project_id: Optional[int] = None) -> List[int]:
        """
        Create subtasks in the TODO service.
        
        Args:
            parent_task_id: Parent task ID
            agent_id: Agent ID creating subtasks
            subtask_definitions: List of subtask definitions from decomposition
            project_id: Project ID (optional)
            
        Returns:
            List of created subtask IDs
        """
        created_ids = []
        
        # Sort subtasks by order
        sorted_subtasks = sorted(subtask_definitions, key=lambda x: x.get("order", 0))
        
        for subtask_def in sorted_subtasks:
            try:
                # Create subtask via MCP (synchronous call)
                result = self.mcp_client.create_task(
                    title=subtask_def.get("title", "Untitled Subtask"),
                    task_type="concrete",
                    task_instruction=subtask_def.get("task_instruction", ""),
                    verification_instruction=subtask_def.get("verification_instruction", ""),
                    agent_id=agent_id,
                    project_id=project_id,
                    parent_task_id=parent_task_id,
                    relationship_type="subtask",
                    estimated_hours=subtask_def.get("estimated_hours"),
                    notes=f"Created via task decomposition. Order: {subtask_def.get('order', 0)}"
                )
                
                subtask_id = result.get("task_id")
                if subtask_id:
                    created_ids.append(subtask_id)
                    logger.info(f"Created subtask {subtask_id}: {subtask_def.get('title')}")
            except Exception as e:
                logger.error(f"Failed to create subtask '{subtask_def.get('title')}': {e}", exc_info=True)
        
        return created_ids


class StrategySelector:
    """Selects execution strategies based on task type and context."""
    
    STRATEGIES = {
        "concrete": {
            "approach": "direct_implementation",
            "steps": ["analyze", "plan", "implement", "test", "verify"],
            "error_recovery": {
                "rollback_plan": "Revert changes on failure",
                "retry_strategy": "Fix errors and retry"
            }
        },
        "abstract": {
            "approach": "decomposition_first",
            "steps": ["analyze", "decompose", "plan_subtasks", "execute_subtasks", "verify"],
            "error_recovery": {
                "rollback_plan": "Unlock subtasks on failure",
                "retry_strategy": "Re-decompose if needed"
            }
        },
        "epic": {
            "approach": "phased_implementation",
            "steps": ["analyze", "decompose", "prioritize", "phase_1", "phase_2", "verify"],
            "error_recovery": {
                "rollback_plan": "Rollback phase on failure",
                "retry_strategy": "Continue with next phase"
            }
        }
    }
    
    def select_strategy(self, task_context: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Select execution strategy based on task type and analysis.
        
        Args:
            task_context: Full task context
            analysis: Task analysis result
            
        Returns:
            Strategy dictionary with approach, steps, and error recovery
        """
        task = task_context.get("task", {})
        task_type = task.get("task_type", "concrete")
        complexity = analysis.get("complexity", "medium")
        
        # Get base strategy for task type
        base_strategy = self.STRATEGIES.get(task_type, self.STRATEGIES["concrete"]).copy()
        
        # Adapt based on complexity
        if complexity == "high":
            base_strategy["approach"] = "careful_planning_first"
            base_strategy["steps"].insert(1, "deep_analysis")
            base_strategy["error_recovery"]["rollback_plan"] = "Incremental rollback with checkpoints"
        elif complexity == "low":
            base_strategy["approach"] = "rapid_prototyping"
            base_strategy["steps"] = ["quick_plan", "implement", "test", "verify"]
        
        # Add risk mitigation if risks identified
        risk_factors = analysis.get("risk_factors", [])
        if risk_factors:
            base_strategy["risk_mitigation"] = {
                "risks": risk_factors,
                "mitigation": "Address risks early, add extra verification steps"
            }
        
        logger.info(f"Selected strategy: {base_strategy['approach']} for {task_type} task")
        return base_strategy


class PlanManager:
    """Manages plan persistence and learning from experience."""
    
    def __init__(self, storage: Optional[AgentStateStorage] = None):
        """
        Initialize plan manager.
        
        Args:
            storage: AgentStateStorage instance (optional, for persistence)
        """
        self.storage = storage
        self._plans_cache: Dict[str, AgentPlan] = {}
    
    async def save_plan(self, plan: AgentPlan) -> Optional[str]:
        """
        Save plan to database.
        
        Args:
            plan: AgentPlan instance
            
        Returns:
            Plan ID if saved, None otherwise
        """
        if not self.storage:
            logger.debug("Storage not available, skipping plan save")
            return None
        
        try:
            plan_id = await self.storage.save_plan(plan)
            self._plans_cache[plan_id] = plan
            logger.info(f"Saved plan {plan_id} (type: {plan.plan_type})")
            return plan_id
        except Exception as e:
            logger.error(f"Failed to save plan: {e}", exc_info=True)
            return None
    
    async def find_similar_plan(self, agent_id: str, task_type: str, plan_type: str, min_success_rate: float = 0.7) -> Optional[AgentPlan]:
        """
        Find similar successful plan to reuse.
        
        Args:
            agent_id: Agent ID
            task_type: Task type (concrete/abstract/epic)
            plan_type: Plan type (execution_plan/task_decomposition/strategy)
            min_success_rate: Minimum success rate to consider
            
        Returns:
            Similar AgentPlan if found, None otherwise
        """
        if not self.storage:
            return None
        
        try:
            plans = await self.storage.query_plans(
                agent_id=agent_id,
                plan_type=plan_type,
                min_success_rate=min_success_rate,
                limit=10
            )
            
            # Filter by task type if available in plan_data
            for plan in plans:
                plan_task_type = plan.plan_data.get("task_type")
                if plan_task_type == task_type:
                    logger.info(f"Found similar plan {plan.plan_data.get('id', 'unknown')} with success rate {plan.success_rate}")
                    return plan
            
            return None
        except Exception as e:
            logger.error(f"Failed to query similar plans: {e}", exc_info=True)
            return None
    
    async def update_plan_success(self, plan_id: str, success: bool):
        """
        Update plan success rate after execution.
        
        Args:
            plan_id: Plan ID
            success: Whether execution was successful
        """
        if not self.storage:
            return
        
        try:
            plan = await self.storage.load_plan(plan_id)
            if plan:
                plan.increment_execution(success)
                await self.storage.update_plan(plan_id, {
                    "success_rate": plan.success_rate,
                    "execution_count": plan.execution_count,
                    "plan_data": plan.plan_data
                })
                logger.info(f"Updated plan {plan_id}: success_rate={plan.success_rate}, count={plan.execution_count}")
        except Exception as e:
            logger.error(f"Failed to update plan success: {e}", exc_info=True)


class PlanningSystem:
    """Comprehensive planning system integrating all components."""
    
    def __init__(self, qwen3_call_fn, mcp_client, storage: Optional[AgentStateStorage] = None):
        """
        Initialize planning system.
        
        Args:
            qwen3_call_fn: Function to call Qwen3 model
            mcp_client: MCP client for TODO operations
            storage: AgentStateStorage for plan persistence (optional)
        """
        self.analyzer = TaskAnalyzer(qwen3_call_fn)
        self.decomposer = TaskDecomposer(qwen3_call_fn, mcp_client)
        self.strategy_selector = StrategySelector()
        self.plan_manager = PlanManager(storage)
    
    async def create_plan(self, task_context: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """
        Create comprehensive execution plan for a task.
        
        Args:
            task_context: Full task context from MCP service
            agent_id: Agent ID creating the plan
            
        Returns:
            Plan dictionary with:
            - analysis: Task analysis
            - decomposition: Subtask definitions (if applicable)
            - strategy: Execution strategy
            - execution_plan: Step-by-step execution plan
            - plan_id: Saved plan ID (if persisted)
        """
        task = task_context.get("task", {})
        task_id = task.get("id")
        task_type = task.get("task_type", "concrete")
        
        logger.info(f"Creating plan for task {task_id} (type: {task_type})")
        
        # Step 1: Analyze task
        analysis = self.analyzer.analyze_task(task_context)
        
        # Step 2: Check for similar successful plans
        similar_plan = await self.plan_manager.find_similar_plan(
            agent_id=agent_id,
            task_type=task_type,
            plan_type="execution_plan"
        )
        
        # Step 3: Decompose if needed
        decomposition = []
        subtask_ids = []
        if task_type in ["abstract", "epic"] or analysis.get("complexity") == "high":
            subtask_definitions = self.decomposer.decompose_task(task_context, analysis)
            if subtask_definitions:
                decomposition = subtask_definitions
                # Create subtasks in TODO service (synchronous call)
                subtask_ids = self.decomposer.create_subtasks(
                    parent_task_id=task_id,
                    agent_id=agent_id,
                    subtask_definitions=subtask_definitions,
                    project_id=task_context.get("project", {}).get("id")
                )
        
        # Step 4: Select strategy
        strategy = self.strategy_selector.select_strategy(task_context, analysis)
        
        # Step 5: Create execution plan (reuse similar plan if found)
        if similar_plan and similar_plan.plan_data.get("execution_plan"):
            logger.info("Reusing similar successful plan")
            execution_plan = similar_plan.plan_data.get("execution_plan")
        else:
            # Create new execution plan
            execution_plan = self._create_execution_plan(task_context, analysis, strategy)
        
        # Step 6: Save plan for future reuse
        plan = AgentPlan(
            agent_id=agent_id,
            task_id=str(task_id) if task_id else None,
            plan_type="execution_plan",
            plan_data={
                "task_type": task_type,
                "analysis": analysis,
                "decomposition": decomposition,
                "strategy": strategy,
                "execution_plan": execution_plan,
                "subtask_ids": subtask_ids
            },
            success_rate=0.0,
            execution_count=0
        )
        
        plan_id = await self.plan_manager.save_plan(plan)
        
        return {
            "analysis": analysis,
            "decomposition": decomposition,
            "subtask_ids": subtask_ids,
            "strategy": strategy,
            "execution_plan": execution_plan,
            "plan_id": plan_id,
            "similar_plan_reused": similar_plan is not None
        }
    
    def _create_execution_plan(self, task_context: Dict[str, Any], analysis: Dict[str, Any], strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create step-by-step execution plan.
        
        Args:
            task_context: Full task context
            analysis: Task analysis
            strategy: Selected strategy
            
        Returns:
            List of execution steps
        """
        task = task_context.get("task", {})
        requirements = analysis.get("requirements", [])
        steps = strategy.get("steps", [])
        
        execution_plan = []
        step_number = 1
        
        for step_name in steps:
            if step_name == "analyze":
                execution_plan.append({
                    "step_number": step_number,
                    "name": "analyze",
                    "description": "Analyze task requirements and context",
                    "action": "analyze",
                    "details": f"Review: {', '.join(requirements[:3])}"
                })
                step_number += 1
            elif step_name == "decompose":
                execution_plan.append({
                    "step_number": step_number,
                    "name": "decompose",
                    "description": "Break task into subtasks",
                    "action": "decompose",
                    "details": "Create subtasks via MCP"
                })
                step_number += 1
            elif step_name == "plan":
                execution_plan.append({
                    "step_number": step_number,
                    "name": "plan",
                    "description": "Create detailed execution plan",
                    "action": "plan",
                    "details": "Generate step-by-step plan"
                })
                step_number += 1
            elif step_name == "implement":
                execution_plan.append({
                    "step_number": step_number,
                    "name": "implement",
                    "description": "Implement the solution",
                    "action": "implement",
                    "details": f"Implement: {task.get('title', 'task')}"
                })
                step_number += 1
            elif step_name == "test":
                execution_plan.append({
                    "step_number": step_number,
                    "name": "test",
                    "description": "Run tests",
                    "action": "test",
                    "details": "Run test suite"
                })
                step_number += 1
            elif step_name == "verify":
                execution_plan.append({
                    "step_number": step_number,
                    "name": "verify",
                    "description": "Verify completion",
                    "action": "verify",
                    "details": task.get("verification_instruction", "Verify task completion")
                })
                step_number += 1
        
        return execution_plan
    
    async def record_plan_execution(self, plan_id: Optional[str], success: bool):
        """
        Record plan execution result for learning.
        
        Args:
            plan_id: Plan ID (if saved)
            success: Whether execution was successful
        """
        if plan_id:
            await self.plan_manager.update_plan_success(plan_id, success)