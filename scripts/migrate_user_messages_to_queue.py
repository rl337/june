#!/usr/bin/env python3
"""
Script to migrate messages from USER_MESSAGES.md to the user_interaction_tasks.jsonl queue.
Only migrates messages with ERROR or NEW status.
"""
import json
import re
from pathlib import Path

def parse_user_messages():
    """Parse USER_MESSAGES.md and extract messages with ERROR or NEW status."""
    messages_file = Path('/home/rlee/june_data/var-data/USER_MESSAGES.md')
    if not messages_file.exists():
        print('No USER_MESSAGES.md file found')
        return []
    
    content = messages_file.read_text()
    
    # Split by message sections (## headers)
    sections = re.split(r'^## \[([^\]]+)\] (.+)$', content, flags=re.MULTILINE)
    
    messages = []
    i = 1  # Start at 1 because section[0] is content before first header
    
    while i < len(sections):
        timestamp = sections[i]
        msg_type = sections[i+1] if i+1 < len(sections) else ''
        section_content = sections[i+2] if i+2 < len(sections) else ''
        
        # Parse the section content
        current_message = {'timestamp': timestamp, 'type': msg_type}
        
        # Extract fields from section
        user_match = re.search(r'- \*\*User:\*\*[^\n]*user_id: (\d+)', section_content)
        if user_match:
            current_message['user_id'] = user_match.group(1)
        
        username_match = re.search(r'- \*\*User:\*\*[^\n]*@(\w+)', section_content)
        if username_match:
            current_message['username'] = username_match.group(1)
        
        platform_match = re.search(r'- \*\*Platform:\*\* (.+)', section_content)
        if platform_match:
            current_message['platform'] = platform_match.group(1).strip().lower()
        
        content_match = re.search(r'- \*\*Content:\*\* (.+)', section_content)
        if content_match:
            current_message['content'] = content_match.group(1).strip()
        
        msg_id_match = re.search(r'- \*\*Message ID:\*\* (.+)', section_content)
        if msg_id_match:
            current_message['message_id'] = msg_id_match.group(1).strip()
        
        chat_id_match = re.search(r'- \*\*Chat ID:\*\* (\d+)', section_content)
        if chat_id_match:
            current_message['chat_id'] = chat_id_match.group(1).strip()
        
        status_match = re.search(r'- \*\*Status:\*\* (.+)', section_content)
        if status_match:
            current_message['status'] = status_match.group(1).strip()
        
        # Only include messages with ERROR or NEW status that have required fields
        if (current_message.get('status') in ('ERROR', 'NEW') and 
            current_message.get('user_id') and 
            current_message.get('content')):
            messages.append(current_message)
        
        i += 3  # Move to next section
    
    return messages

def add_to_queue(messages):
    """Add messages to the user_interaction_tasks.jsonl queue file."""
    queue_file = Path('/home/rlee/june_data/var-data/user_interaction_tasks.jsonl')
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    
    added = 0
    for msg in messages:
        # Format task data
        username_str = f"@{msg.get('username')} " if msg.get('username') else ""
        title = f"User Interaction: {msg['platform'].capitalize()} - {username_str}({msg['user_id']})"
        
        instruction = f"""User message from {msg['platform'].capitalize()}:
- User: {username_str}(user_id: {msg['user_id']})
- Chat ID: {msg.get('chat_id', msg['user_id'])}
- Message ID: {msg.get('message_id', 'N/A')}
- Platform: {msg['platform'].capitalize()}
- Content: {msg['content']}

Please process this user interaction and respond appropriately."""
        
        verification = f"""Verify response by:
1. Agent has processed the user message
2. Agent has sent a response via {msg['platform'].capitalize()}
3. Task can be marked as complete"""
        
        task_data = {
            "user_id": msg['user_id'],
            "chat_id": msg.get('chat_id', msg['user_id']),
            "platform": msg['platform'],
            "content": msg['content'],
            "message_id": msg.get('message_id'),
            "username": msg.get('username'),
            "title": title,
            "instruction": instruction,
            "verification": verification,
            "project_id": 1,
        }
        
        # Append to queue file
        with open(queue_file, "a") as f:
            f.write(json.dumps(task_data) + "\n")
        
        added += 1
        print(f"✓ Added: {msg['timestamp']} - {msg['content'][:60]}...")
    
    return added

if __name__ == '__main__':
    print("Parsing USER_MESSAGES.md...")
    messages = parse_user_messages()
    
    if not messages:
        print("No messages with ERROR or NEW status found.")
        exit(0)
    
    print(f"\nFound {len(messages)} messages to migrate:")
    for msg in messages:
        print(f"  - {msg['timestamp']}: {msg['content'][:60]}...")
    
    print(f"\nAdding to queue file...")
    added = add_to_queue(messages)
    print(f"\n✓ Successfully added {added} messages to queue file")
    print(f"Queue file: /home/rlee/june_data/var-data/user_interaction_tasks.jsonl")

