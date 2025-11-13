# TODO MCP Service API

The TODO MCP Service provides a REST API for task management, designed for AI agents to create, query, reserve, and complete tasks.

## Base URL

```
http://localhost:8004
```

## Overview

The TODO Service manages tasks for AI agents with support for:
- Task creation and management
- Task relationships (subtasks, blocking, followups)
- Agent task assignment and locking
- Task completion and verification
- Agent performance tracking
- MCP (Model Context Protocol) compatibility

## Task Types

- **concrete**: Ready for direct implementation
- **abstract**: Needs to be broken down into smaller tasks
- **epic**: Large feature or initiative spanning multiple tasks

## Task Status

- **available**: Available for agents to pick up
- **in_progress**: Currently being worked on by an agent
- **complete**: Task has been completed
- **blocked**: Task cannot proceed due to dependencies
- **cancelled**: Task was cancelled

## Core Endpoints

### Health Check

#### GET `/health`

Check service health.

**Response:**
```json
{
  "status": "healthy",
  "service": "todo-service"
}
```

### Task Management

#### POST `/tasks`

Create a new task.

**Request Body:**
```json
{
  "title": "string",
  "task_type": "concrete | abstract | epic",
  "task_instruction": "string",
  "verification_instruction": "string",
  "agent_id": "string",
  "notes": "string (optional)"
}
```

**Response (201):**
```json
{
  "id": 123,
  "title": "string",
  "task_type": "concrete",
  "task_instruction": "string",
  "verification_instruction": "string",
  "task_status": "available",
  "verification_status": "unverified",
  "assigned_agent": null,
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00",
  "completed_at": null,
  "notes": null
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8004/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Implement feature X",
    "task_type": "concrete",
    "task_instruction": "Add feature X with tests",
    "verification_instruction": "Run tests and verify feature works",
    "agent_id": "agent-1"
  }'
```

**Example (Python):**
```python
import requests

response = requests.post(
    "http://localhost:8004/tasks",
    json={
        "title": "Implement feature X",
        "task_type": "concrete",
        "task_instruction": "Add feature X with tests",
        "verification_instruction": "Run tests and verify feature works",
        "agent_id": "agent-1"
    }
)
task = response.json()
print(f"Created task {task['id']}")
```

#### GET `/tasks/{task_id}`

Get a task by ID.

**Response:**
```json
{
  "id": 123,
  "title": "string",
  "task_type": "concrete",
  "task_instruction": "string",
  "verification_instruction": "string",
  "task_status": "available",
  "verification_status": "unverified",
  "assigned_agent": null,
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-01-01T00:00:00",
  "completed_at": null,
  "notes": null
}
```

#### GET `/tasks`

Query tasks with filters.

**Query Parameters:**
- `task_type` (optional): Filter by task type
- `task_status` (optional): Filter by task status
- `assigned_agent` (optional): Filter by assigned agent
- `limit` (optional): Maximum number of results (default: 100, max: 1000)

**Response:**
```json
[
  {
    "id": 123,
    "title": "string",
    "task_type": "concrete",
    "task_status": "available",
    ...
  }
]
```

**Example:**
```bash
curl "http://localhost:8004/tasks?task_type=concrete&task_status=available&limit=10"
```

#### POST `/tasks/{task_id}/lock`

Lock a task for an agent (set to in_progress).

**Request Body:**
```json
{
  "agent_id": "string"
}
```

**Response:**
```json
{
  "message": "Task 123 locked by agent agent-1",
  "task_id": 123
}
```

**Error (409):**
```json
{
  "detail": "Task 123 is not available (may be already locked or have different status)"
}
```

#### POST `/tasks/{task_id}/unlock`

Unlock a task (set back to available).

**Request Body:**
```json
{
  "agent_id": "string"
}
```

**Response:**
```json
{
  "message": "Task 123 unlocked by agent agent-1",
  "task_id": 123
}
```

#### POST `/tasks/{task_id}/complete`

Mark a task as complete.

**Request Body:**
```json
{
  "agent_id": "string",
  "notes": "string (optional)"
}
```

**Response:**
```json
{
  "message": "Task 123 marked as complete by agent agent-1",
  "task_id": 123
}
```

#### POST `/tasks/{task_id}/verify`

Mark a task as verified.

**Request Body:**
```json
{
  "agent_id": "string"
}
```

**Response:**
```json
{
  "message": "Task 123 verified by agent agent-1",
  "task_id": 123
}
```

**Error (400):**
```json
{
  "detail": "Task must be complete before verification"
}
```

#### PATCH `/tasks/{task_id}`

Update a task (partial update).

**Request Body:**
```json
{
  "task_status": "string (optional)",
  "verification_status": "string (optional)",
  "notes": "string (optional)"
}
```

**Response:**
```json
{
  "id": 123,
  "title": "string",
  ...
}
```

### Task Relationships

#### POST `/relationships`

Create a relationship between two tasks.

**Request Body:**
```json
{
  "parent_task_id": 100,
  "child_task_id": 101,
  "relationship_type": "subtask | blocking | blocked_by | followup | related",
  "agent_id": "string"
}
```

**Response:**
```json
{
  "message": "Relationship created",
  "relationship_id": 1
}
```

**Relationship Types:**
- **subtask**: Child task is part of parent task
- **blocking**: Child task blocks parent task
- **blocked_by**: Parent task blocks child task
- **followup**: Child task is a followup to parent task
- **related**: Tasks are related but not directly dependent

#### GET `/tasks/{task_id}/relationships`

Get relationships for a task.

**Query Parameters:**
- `relationship_type` (optional): Filter by relationship type

**Response:**
```json
{
  "task_id": 123,
  "relationships": [
    {
      "id": 1,
      "parent_task_id": 100,
      "child_task_id": 123,
      "relationship_type": "subtask",
      "created_at": "2025-01-01T00:00:00"
    }
  ]
}
```

#### GET `/tasks/{task_id}/blocking`

Get tasks that are blocking the given task.

**Response:**
```json
{
  "task_id": 123,
  "blocking_tasks": [
    {
      "id": 100,
      "title": "Blocking task",
      "task_status": "in_progress"
    }
  ]
}
```

### Agent Endpoints

#### GET `/agents/{agent_type}/available-tasks`

Get available tasks for an agent type.

**Path Parameters:**
- `agent_type`: `breakdown` or `implementation`

**Query Parameters:**
- `limit` (optional): Maximum number of results (default: 10, max: 100)

**Response:**
```json
{
  "agent_type": "implementation",
  "tasks": [
    {
      "id": 123,
      "title": "string",
      "task_type": "concrete",
      "task_status": "available",
      ...
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:8004/agents/implementation/available-tasks?limit=10"
```

#### GET `/agents/{agent_id}/stats`

Get statistics for an agent's performance.

**Query Parameters:**
- `task_type` (optional): Filter by task type

**Response:**
```json
{
  "agent_id": "agent-1",
  "tasks_completed": 50,
  "tasks_in_progress": 2,
  "average_completion_time_hours": 2.5,
  "success_rate": 0.95
}
```

### Followup Tasks

#### POST `/tasks/{task_id}/add-followup`

Complete a task and add a followup task.

**Request Body:**
```json
{
  "title": "string",
  "task_type": "concrete | abstract | epic",
  "task_instruction": "string",
  "verification_instruction": "string",
  "agent_id": "string",
  "notes": "string (optional)"
}
```

**Response:**
```json
{
  "message": "Followup task created and linked to task 123",
  "parent_task_id": 123,
  "followup_task_id": 124
}
```

### Change History

#### GET `/change-history`

Get change history with optional filters.

**Query Parameters:**
- `task_id` (optional): Filter by task ID
- `agent_id` (optional): Filter by agent ID
- `limit` (optional): Maximum number of results (default: 100, max: 1000)

**Response:**
```json
{
  "history": [
    {
      "id": 1,
      "task_id": 123,
      "agent_id": "agent-1",
      "change_type": "status_change",
      "field_name": "task_status",
      "old_value": "available",
      "new_value": "in_progress",
      "created_at": "2025-01-01T00:00:00"
    }
  ]
}
```

## MCP-Compatible Endpoints

The service provides MCP (Model Context Protocol) compatible endpoints for AI agents.

### GET `/mcp/functions`

Get MCP function definitions.

**Response:**
```json
{
  "functions": [
    {
      "name": "list_available_tasks",
      "description": "List available tasks for an agent type",
      "parameters": {...}
    }
  ]
}
```

### POST `/mcp/list_available_tasks`

List available tasks for an agent type (MCP endpoint).

**Request Body:**
```json
{
  "agent_type": "breakdown | implementation",
  "limit": 10
}
```

**Response:**
```json
{
  "tasks": [
    {
      "id": 123,
      "title": "string",
      "task_type": "concrete",
      "task_status": "available",
      ...
    }
  ]
}
```

### POST `/mcp/reserve_task`

Reserve (lock) a task for an agent (MCP endpoint).

**Request Body:**
```json
{
  "task_id": 123,
  "agent_id": "agent-1"
}
```

**Response:**
```json
{
  "success": true,
  "task": {
    "id": 123,
    "task_status": "in_progress",
    "assigned_agent": "agent-1",
    ...
  }
}
```

### POST `/mcp/complete_task`

Complete a task and optionally create followup (MCP endpoint).

**Request Body:**
```json
{
  "task_id": 123,
  "agent_id": "agent-1",
  "notes": "string (optional)",
  "followup_title": "string (optional)",
  "followup_task_type": "concrete | abstract | epic (optional)",
  "followup_instruction": "string (optional)",
  "followup_verification": "string (optional)"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Task completed",
  "followup_task_id": 124
}
```

### POST `/mcp/create_task`

Create a new task (MCP endpoint).

**Request Body:**
```json
{
  "title": "string",
  "task_type": "concrete | abstract | epic",
  "task_instruction": "string",
  "verification_instruction": "string",
  "agent_id": "string",
  "parent_task_id": 100,
  "relationship_type": "subtask | blocking | blocked_by | related",
  "notes": "string (optional)"
}
```

**Response:**
```json
{
  "success": true,
  "task_id": 123,
  "relationship_id": 1
}
```

### POST `/mcp/get_agent_performance`

Get agent performance statistics (MCP endpoint).

**Request Body:**
```json
{
  "agent_id": "agent-1",
  "task_type": "concrete (optional)"
}
```

**Response:**
```json
{
  "agent_id": "agent-1",
  "tasks_completed": 50,
  "average_hours": 2.5,
  "success_rate": 0.95
}
```

## Backup Endpoints

### POST `/backup/create`

Create a manual backup snapshot.

**Response:**
```json
{
  "success": true,
  "backup_path": "/path/to/backup.tar.gz"
}
```

### GET `/backup/list`

List all available backups.

**Response:**
```json
{
  "backups": [
    {
      "path": "/path/to/backup.tar.gz",
      "created_at": "2025-01-01T00:00:00",
      "size_bytes": 1048576
    }
  ],
  "count": 1
}
```

### POST `/backup/restore`

Restore database from a backup.

**Request Body:**
```json
{
  "backup_path": "/path/to/backup.tar.gz",
  "force": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Database restored successfully"
}
```

### POST `/backup/cleanup`

Clean up old backups.

**Request Body:**
```json
{
  "keep_days": 30
}
```

**Response:**
```json
{
  "success": true,
  "deleted_count": 5
}
```

## Error Codes

- `400 Bad Request`: Invalid request parameters or body
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource conflict (e.g., task already locked)
- `500 Internal Server Error`: Server error

## Usage Examples

### Complete Workflow

```python
import requests

BASE_URL = "http://localhost:8004"
AGENT_ID = "my-agent"

# 1. List available tasks
response = requests.get(f"{BASE_URL}/agents/implementation/available-tasks?limit=10")
tasks = response.json()["tasks"]

# 2. Reserve a task
task_id = tasks[0]["id"]
response = requests.post(
    f"{BASE_URL}/tasks/{task_id}/lock",
    json={"agent_id": AGENT_ID}
)

# 3. Get task details
response = requests.get(f"{BASE_URL}/tasks/{task_id}")
task = response.json()

# 4. Work on task...
# ... implement the task ...

# 5. Complete the task
response = requests.post(
    f"{BASE_URL}/tasks/{task_id}/complete",
    json={
        "agent_id": AGENT_ID,
        "notes": "Task completed successfully. All tests pass."
    }
)

# 6. Verify the task
response = requests.post(
    f"{BASE_URL}/tasks/{task_id}/verify",
    json={"agent_id": AGENT_ID}
)
```

### Create Task with Relationship

```python
import requests

BASE_URL = "http://localhost:8004"

# Create parent task
parent_response = requests.post(
    f"{BASE_URL}/tasks",
    json={
        "title": "Parent task",
        "task_type": "epic",
        "task_instruction": "Large feature",
        "verification_instruction": "Verify all subtasks complete",
        "agent_id": "agent-1"
    }
)
parent_id = parent_response.json()["id"]

# Create child task
child_response = requests.post(
    f"{BASE_URL}/tasks",
    json={
        "title": "Child task",
        "task_type": "concrete",
        "task_instruction": "Implement subtask",
        "verification_instruction": "Run tests",
        "agent_id": "agent-1"
    }
)
child_id = child_response.json()["id"]

# Create relationship
requests.post(
    f"{BASE_URL}/relationships",
    json={
        "parent_task_id": parent_id,
        "child_task_id": child_id,
        "relationship_type": "subtask",
        "agent_id": "agent-1"
    }
)
```

## Best Practices

1. **Always lock before working**: Use `/tasks/{id}/lock` before starting work
2. **Unlock if unable to complete**: Use `/tasks/{id}/unlock` if you cannot complete a task
3. **Add completion notes**: Include detailed notes when completing tasks
4. **Create relationships**: Link related tasks for better organization
5. **Use appropriate task types**: Use `concrete` for implementable tasks, `abstract` for tasks needing breakdown
6. **Check blocking tasks**: Use `/tasks/{id}/blocking` to check dependencies
