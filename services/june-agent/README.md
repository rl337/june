# June Agent Service

Orchestrates task execution with Qwen3-30B-A3B for planning, code generation, and verification.

## Overview

This service continuously picks up tasks from the TODO MCP service and uses Qwen3-30B-A3B for:
- **Task Analysis**: Deep analysis of requirements, dependencies, prerequisites, and complexity
- **Task Decomposition**: Breaking large tasks into smaller subtasks with relationships
- **Planning**: Creating comprehensive execution plans with strategy selection
- **Learning from Experience**: Storing and reusing successful plans
- **Code Generation**: Generating code, scripts, and implementation files
- **Execution**: Running commands, tests, and verification
- **Verification**: Reviewing completed work against verification criteria

## Features

1. **Continuous Task Processing**: Runs in a loop, automatically picking up and processing tasks
2. **Comprehensive Planning System**: Task analysis, decomposition, strategy selection, and plan persistence
3. **Qwen3 Integration**: Direct integration with Qwen3-30B-A3B via `Qwen3LlmStrategy`
4. **MCP TODO Integration**: Uses MCP client for all TODO service operations
5. **Task Decomposition**: Automatically breaks complex tasks into subtasks with relationships
6. **Plan Learning**: Stores successful plans and reuses them for similar tasks
7. **Code Execution**: Executes generated code and commands in project directories
8. **Test Integration**: Runs tests and verification as part of task execution
9. **Error Handling**: Gracefully handles errors and unlocks tasks on failure

## Architecture

```
???????????????????
?  Agent Loop     ?
???????????????????
         ?
         ??> Query/Reserve Tasks (MCP)
         ?
         ??> Plan with Qwen3
         ?
         ??> Execute Steps
         ?   ?? Generate Code (Qwen3)
         ?   ?? Run Commands
         ?   ?? Run Tests
         ?
         ??> Verify with Qwen3
         ?
         ??> Complete/Unlock Task (MCP)
```

## Usage

```bash
python3 main.py [--max-loops N] [--sleep-interval SECONDS]
```

## Environment Variables

- `JUNE_AGENT_ID`: Agent identifier (default: 'june-agent')
- `JUNE_PROJECT_ID`: Project ID to filter tasks (optional)
- `JUNE_AGENT_TYPE`: Agent type - 'implementation' or 'breakdown' (default: 'implementation')
- `JUNE_SLEEP_INTERVAL`: Sleep interval between iterations in seconds (default: 60)
- `TODO_SERVICE_URL`: TODO MCP Service URL (default: 'http://localhost:8004')
- `QWEN3_MODEL_NAME`: Qwen3 model name (default: 'Qwen/Qwen2.5-72B-Instruct')
- `QWEN3_DEVICE`: Device for Qwen3 ('cuda' or 'cpu', default: auto-detect)
- `LOG_LEVEL`: Logging level (default: 'INFO')

## Execution Flow

1. **Check for In-Progress Tasks**: First checks for tasks already assigned to the agent
2. **Pick Up New Task**: If none, queries for available tasks and reserves one
3. **Get Task Context**: Retrieves full context including project info, updates, and ancestry
4. **Comprehensive Planning**:
   - **Task Analysis**: Analyzes requirements, dependencies, prerequisites, complexity
   - **Find Similar Plans**: Searches for successful similar plans to reuse
   - **Task Decomposition**: Breaks complex tasks into subtasks (if needed)
   - **Strategy Selection**: Chooses execution strategy based on task type and complexity
   - **Execution Plan**: Creates step-by-step execution plan
   - **Plan Persistence**: Saves plan for future reuse and learning
5. **Execute Steps**: Executes each step in the plan (code generation, commands, tests)
6. **Verify with Qwen3**: Uses Qwen3 to verify task completion against criteria
7. **Record Learning**: Updates plan success rate for future reuse
8. **Complete/Unlock**: Completes task on success or unlocks on failure

## Integration Points

- **TODO MCP Service**: Task management via `june-mcp-client`
- **Qwen3-30B-A3B**: Planning and code generation via `inference-core` package
- **Agent State Storage**: Plan persistence and learning via `june-agent-state` package
- **Code Execution**: Subprocess for running commands and tests
- **Git Operations**: Direct git commands for checking status and committing

## Requirements

- Python 3.8+
- `june-mcp-client` package (from `packages/june-mcp-client/`)
- `inference-core` package (from `packages/inference-core/`)
- `june-agent-state` package (from `packages/june-agent-state/`) - for plan persistence
- Access to Qwen3 model (via HuggingFace or local)
- TODO MCP Service running
- PostgreSQL database (optional, for plan persistence via `DATABASE_URL` env var)
- CUDA support (optional, for GPU acceleration)

## Development

```bash
# Install dependencies
pip install -e ../packages/june-mcp-client
pip install -e ../packages/inference-core
pip install -e ../packages/june-agent-state

# Set up database (optional, for plan persistence)
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/june"

# Run service
python3 main.py --max-loops 1 --sleep-interval 10
```

## Monitoring

The service logs all operations:
- Task reservations and completions
- Qwen3 planning and generation
- Command execution results
- Errors and failures

## Error Handling

- **Task Lock Errors**: Automatically unlocks and retries
- **Execution Errors**: Unlocks task and continues to next iteration
- **Connection Errors**: Retries after sleep interval
- **Fatal Errors**: Exits with error code

## Planning System

The service includes a comprehensive planning system (`planning.py`) with:

1. **TaskAnalyzer**: Deep task analysis extracting requirements, dependencies, prerequisites, complexity, and required tools
2. **TaskDecomposer**: Breaks large tasks into smaller subtasks with proper relationships
3. **StrategySelector**: Chooses execution strategies based on task type (concrete/abstract/epic) and complexity
4. **PlanManager**: Persists plans to database and learns from experience by tracking success rates
5. **PlanningSystem**: Integrates all components for comprehensive planning

### Plan Persistence

Plans are saved to the database and reused for similar tasks:
- Plans are queried by task type and plan type
- Successful plans (high success rate) are prioritized for reuse
- Plan execution results update success rates for continuous learning

### Task Decomposition

Complex tasks are automatically decomposed:
- Abstract and epic tasks are always decomposed
- High complexity tasks are decomposed into subtasks
- Subtasks are created in the TODO service with proper parent-child relationships
- Each subtask has clear instructions and verification criteria

## Best Practices

1. **Test-First Development**: Qwen3 plans should include test creation before implementation
2. **Incremental Execution**: Plans break tasks into small, executable steps
3. **Task Decomposition**: Large tasks should be decomposed into manageable subtasks
4. **Plan Reuse**: The system learns from successful plans and reuses them
5. **Verification**: Always verify work against verification criteria
6. **Error Recovery**: Always unlock tasks on errors
7. **Progress Updates**: Add updates throughout execution for visibility
