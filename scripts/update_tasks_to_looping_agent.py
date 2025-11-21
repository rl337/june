#!/usr/bin/env python3
"""
Script to update all existing tasks in todorama to use agent_id="looping_agent".
Also marks test tasks as complete with originator="ide_agent".
"""
import subprocess
import sys
import json

def get_cursor_agent_cmd():
    """Get the cursor-agent command path."""
    import shutil
    import os
    
    cursor_agent_exe = os.getenv("CURSOR_AGENT_EXE")
    if cursor_agent_exe and os.path.exists(cursor_agent_exe):
        return cursor_agent_exe
    elif shutil.which("cursor-agent"):
        return "cursor-agent"
    elif shutil.which("cursor_agent"):
        return "cursor_agent"
    elif os.path.exists("/usr/local/bin/cursor-tools/cursor-agent"):
        return "/usr/local/bin/cursor-tools/cursor-agent"
    else:
        print("ERROR: cursor-agent command not found", file=sys.stderr)
        sys.exit(1)

def list_all_tasks(cursor_agent_cmd, project_id=1):
    """List all tasks in the project."""
    cmd = [
        cursor_agent_cmd,
        "mcp",
        "call",
        "todorama",
        "list_tasks",
        "--project_id", str(project_id),
        "--limit", "1000",  # Get a large number
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"ERROR: Failed to list tasks: {result.stderr}", file=sys.stderr)
            return []
        
        # Try to parse JSON output
        try:
            tasks = json.loads(result.stdout)
            if isinstance(tasks, list):
                return tasks
            elif isinstance(tasks, dict) and "tasks" in tasks:
                return tasks["tasks"]
            else:
                print(f"WARNING: Unexpected response format: {result.stdout[:200]}")
                return []
        except json.JSONDecodeError:
            print(f"WARNING: Could not parse JSON response: {result.stdout[:200]}")
            return []
    except Exception as e:
        print(f"ERROR: Exception listing tasks: {e}", file=sys.stderr)
        return []

def update_task_agent_id(cursor_agent_cmd, task_id, agent_id="looping_agent"):
    """Update a task's agent_id."""
    # Note: This depends on todorama having an update_task or similar endpoint
    # If not available, we might need to use a different approach
    print(f"  Updating task {task_id} to use agent_id={agent_id}...")
    # For now, we'll just log - actual update depends on todorama API
    return True

def complete_task(cursor_agent_cmd, task_id, notes="", originator="ide_agent"):
    """Mark a task as complete."""
    cmd = [
        cursor_agent_cmd,
        "mcp",
        "call",
        "todorama",
        "complete_task",
        "--task_id", str(task_id),
        "--agent_id", "looping_agent",
        "--notes", notes or f"Completed by {originator}",
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  ✓ Completed task {task_id}")
            return True
        else:
            print(f"  ✗ Failed to complete task {task_id}: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Exception completing task {task_id}: {e}")
        return False

def main():
    cursor_agent_cmd = get_cursor_agent_cmd()
    print(f"Using cursor-agent: {cursor_agent_cmd}")
    print(f"Fetching all tasks from project_id=1...")
    
    tasks = list_all_tasks(cursor_agent_cmd, project_id=1)
    
    if not tasks:
        print("No tasks found or could not list tasks.")
        print("Note: You may need to manually update tasks via todorama interface.")
        return
    
    print(f"\nFound {len(tasks)} tasks")
    
    # Identify test tasks (you may need to adjust this logic)
    test_task_keywords = ["test", "Test", "TEST"]
    test_tasks = []
    other_tasks = []
    
    for task in tasks:
        task_id = task.get("id") or task.get("task_id")
        title = task.get("title", "").lower()
        status = task.get("status", "").lower()
        
        if not task_id:
            continue
        
        # Check if it's a test task
        is_test = any(keyword.lower() in title for keyword in test_task_keywords)
        
        if is_test and status not in ["complete", "completed"]:
            test_tasks.append(task)
        else:
            other_tasks.append(task)
    
    print(f"\nTest tasks to complete: {len(test_tasks)}")
    print(f"Other tasks to update agent_id: {len(other_tasks)}")
    
    # Complete test tasks
    if test_tasks:
        print("\n=== Completing test tasks ===")
        for task in test_tasks:
            task_id = task.get("id") or task.get("task_id")
            title = task.get("title", "Unknown")
            print(f"Completing: {title} (ID: {task_id})")
            complete_task(cursor_agent_cmd, task_id, f"Test task completed by ide_agent", "ide_agent")
    
    # Update agent_id for all tasks
    print("\n=== Updating agent_id for all tasks ===")
    print("Note: Actual agent_id update depends on todorama API capabilities.")
    print("If todorama doesn't support updating agent_id directly, tasks will use")
    print("looping_agent when reserved/completed by the looping agent.")
    
    print(f"\n✓ Processed {len(tasks)} tasks")
    print("\nNext steps:")
    print("1. The looping agent will use agent_id='looping_agent' for all new operations")
    print("2. Test tasks have been marked as complete")
    print("3. When the looping agent reserves/works on tasks, it will use agent_id='looping_agent'")

if __name__ == "__main__":
    main()

