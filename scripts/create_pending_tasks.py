#!/usr/bin/env python3
"""
Script to create pending tasks in Todorama.

This script can be run by the looping agent to create tasks that need to be added to Todorama.
Run from within a container that has network access to todo-mcp-service.
"""
import requests
import json
import os
import sys

def create_task(title, description, task_type="feature", agent_id="looping_agent", originator="ide_agent"):
    """Create a task in Todorama."""
    todo_service_url = os.getenv("TODO_SERVICE_URL", "http://todo-mcp-service:8004")
    if not todo_service_url.startswith("http"):
        todo_service_url = f"http://{todo_service_url}"
    
    api_key = os.getenv("TODO_SERVICE_API_KEY") or os.getenv("TODORAMA_API_KEY")
    
    task_payload = {
        "project_id": 1,
        "title": title,
        "description": description,
        "agent_type": "implementation",
        "task_type": task_type,
        "agent_id": agent_id,
        "originator": originator,
    }
    
    create_url = f"{todo_service_url}/tasks"
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
        print(f"Using API key for authentication")
    else:
        print(f"Warning: No API key found - request may fail")
    
    try:
        response = requests.post(create_url, json=task_payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            task_data = response.json()
            task_id = task_data.get("id") or task_data.get("task_id")
            print(f"✅ Created task: {title} (june-{task_id})")
            return task_id
        else:
            print(f"❌ Failed to create task '{title}': HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error creating task '{title}': {e}")
        return None

if __name__ == "__main__":
    # Task 1: Fix Telegram response issue
    task1_desc = """**Problem:** Telegram service is not sending acknowledgment responses when users send messages.

**Current Status:**
- Service successfully creates Todorama tasks for user messages
- Startup notification works correctly
- Task creation acknowledgment is not being sent back to users

**Issues to Investigate:**
1. **API Key Authentication:** Todorama API requires X-API-Key header. Need to find/configure the API key for task creation.
2. **Task Creation Flow:** Verify the create-user-interaction-task command is working correctly and returning task data.
3. **Acknowledgment Message:** Check if the Telegram handler is properly parsing task creation response and sending acknowledgment.
4. **Error Handling:** Review error handling in the message processing flow to ensure errors are logged and handled gracefully.

**Expected Behavior:**
- User sends message to Telegram
- Service creates Todorama task (type: human_interface)
- Service sends formatted acknowledgment message to user with task details (june-<task#>, creation date, originator, assignee, title, description)

**Files to Check:**
- /home/rlee/dev/june/essence/commands/create_user_interaction_task.py
- /home/rlee/dev/june/essence/services/telegram/handlers/text.py
- Todorama API key configuration

**Priority:** High - Users cannot confirm their messages are being processed."""
    
    # Task 2: Versioning system
    task2_desc = """**Description:**
Implement a formal release versioning system with auto-increment for all components that get released and built into containers. Each component should be able to be versioned independently.

**Requirements:**
1. **Version Management:**
   - Each service/component should have its own version number
   - Versions should follow semantic versioning (MAJOR.MINOR.PATCH)
   - Auto-increment mechanism for patch versions on each build
   - Manual control for major/minor version bumps

2. **Components to Version:**
   - Telegram service
   - Discord service
   - STT service
   - TTS service
   - Message API service
   - Any other containerized services

3. **Implementation:**
   - Version should be stored in a version file or environment variable
   - Docker images should be tagged with version numbers
   - Version should be included in container labels/metadata
   - Version should be accessible via health check endpoints
   - Version should be displayed in startup notifications

4. **Version Sources:**
   - Could use git tags/commits
   - Could use a version file (VERSION, version.txt, etc.)
   - Could use pyproject.toml version field
   - Should be consistent across all components

5. **Build Integration:**
   - Docker build process should read version and tag images accordingly
   - CI/CD pipeline should handle version increment
   - Version should be passed to containers at build time

6. **Documentation:**
   - Document versioning strategy
   - Document how to bump versions
   - Document how versions are used in deployment

**Expected Outcome:**
- All containerized services have independent, trackable versions
- Version information is available at runtime
- Build process automatically increments patch versions
- Clear process for major/minor version updates"""
    
    print("Creating tasks in Todorama...\n")
    
    task1_id = create_task(
        "Fix Telegram service not responding to user messages",
        task1_desc,
        task_type="bug_fix",
        agent_id="looping_agent",
        originator="ide_agent"
    )
    
    task2_id = create_task(
        "Formalize release versioning with auto-increment for all components",
        task2_desc,
        task_type="feature",
        agent_id="looping_agent",
        originator="ide_agent"
    )
    
    if task1_id and task2_id:
        print(f"\n✅ Successfully created both tasks!")
        sys.exit(0)
    else:
        print(f"\n⚠️  Some tasks may not have been created. Check output above.")
        sys.exit(1)

