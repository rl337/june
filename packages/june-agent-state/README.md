# June Agent State

Agent state management models and data structures for June.

## Overview

This package provides data models for managing agent state, including:

- **AgentState**: Current state of an agent (status, current task, capabilities, metrics)
- **AgentCapabilities**: Agent tools and capabilities
- **AgentMetrics**: Performance metrics (tasks completed, success rate, execution times)
- **AgentExecutionRecord**: Individual action records for audit and history
- **AgentPlan**: Execution plans and strategies

## Models

### AgentState

Main model representing the current state of an agent:

```python
from june_agent_state import AgentState, AgentStatus

state = AgentState(
    agent_id="agent-1",
    status=AgentStatus.ACTIVE,
    current_task_id="task-123",
    capabilities=[...],
    metrics=AgentMetrics(...),
    config={"max_concurrent_tasks": 3}
)
```

### AgentCapabilities

Describes what tools and capabilities an agent has:

```python
from june_agent_state import AgentCapabilities

caps = AgentCapabilities(
    tools=["code_execution", "git_operations"],
    metadata={"version": "1.0"},
    version="1.0"
)
```

### AgentMetrics

Tracks agent performance metrics:

```python
from june_agent_state import AgentMetrics

metrics = AgentMetrics()
metrics.update_from_task(task_duration=10.0, success=True)
# Automatically updates tasks_completed, success_rate, avg_execution_time
```

### AgentExecutionRecord

Records individual agent actions:

```python
from june_agent_state import AgentExecutionRecord, AgentExecutionOutcome

record = AgentExecutionRecord(
    agent_id="agent-1",
    task_id="task-123",
    action_type="task_completed",
    outcome=AgentExecutionOutcome.SUCCESS,
    duration_ms=5000,
    metadata={"tools_used": ["git", "pytest"]}
)
```

### AgentPlan

Stores execution plans and strategies:

```python
from june_agent_state import AgentPlan

plan = AgentPlan(
    agent_id="agent-1",
    task_id="task-123",
    plan_type="execution_plan",
    plan_data={"steps": ["step1", "step2"], "strategy": "sequential"}
)

plan.increment_execution(success=True)
# Updates execution_count and success_rate
```

## Installation

```bash
pip install june-agent-state
```

## Usage

All models use Pydantic for validation and serialization:

```python
from june_agent_state import AgentState, AgentStatus

# Create state
state = AgentState(agent_id="test", status=AgentStatus.ACTIVE)

# Serialize to JSON
json_str = state.model_dump_json()

# Deserialize from JSON
state2 = AgentState.model_validate_json(json_str)
```

## Status Enums

- **AgentStatus**: `INIT`, `ACTIVE`, `IDLE`, `ERROR`
- **AgentExecutionOutcome**: `SUCCESS`, `FAILURE`, `PARTIAL`, `CANCELLED`

## Testing

Run tests with pytest:

```bash
cd packages/june-agent-state
pytest
```

## Requirements

- Python >= 3.10
- Pydantic >= 2.0.0
