"""Text message handler for Telegram bot - handles owner/whitelisted user messages."""
import logging
import re
from typing import Optional

from opentelemetry import trace
from telegram import Update
from telegram.ext import ContextTypes

from essence.chat.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def extract_user_info(message: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract user name and favorite color from a message.

    Looks for patterns like:
    - "My name is X" or "I'm X" or "I am X"
    - "My favorite color is X" or "favorite color is X"
    - Handles combined statements like "My name is Bob and my favorite color is blue"

    Args:
        message: The user's message text

    Returns:
        Tuple of (name, favorite_color) - both can be None
    """
    name = None
    favorite_color = None

    # Normalize message for easier matching
    message_lower = message.lower()

    # Patterns for name extraction - capture word after "name is" or similar
    name_patterns = [
        r"my name is ([a-zA-Z]+)",
        r"i'?m ([a-zA-Z]+)",
        r"i am ([a-zA-Z]+)",
        r"name is ([a-zA-Z]+)",
        r"call me ([a-zA-Z]+)",
    ]

    for pattern in name_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            # Extract name, handling cases where it might be followed by "and"
            name_candidate = match.group(1).strip()
            # Check if there's more text after (like "and my favorite color")
            # The regex should stop at word boundaries, but let's be safe
            name = name_candidate.capitalize()
            break

    # Patterns for favorite color extraction
    color_patterns = [
        r"favorite color is ([a-zA-Z]+)",
        r"favourite color is ([a-zA-Z]+)",
        r"favorite colour is ([a-zA-Z]+)",
        r"favourite colour is ([a-zA-Z]+)",
        r"my favorite color is ([a-zA-Z]+)",
        r"my favourite color is ([a-zA-Z]+)",
    ]

    for pattern in color_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            favorite_color = match.group(1).strip().lower()
            break

    return name, favorite_color


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, config
):
    """
    Handle text messages from Telegram users.

    Flow:
    - Non-whitelisted users: Ignore completely (no response)
    - Owner users: Append to USER_MESSAGES.md with status "NEW" for looping agent to process
    - Whitelisted (non-owner) users: Forward message to owner

    Args:
        update: Telegram update object
        context: Telegram context
        config: Service configuration
    """
    with tracer.start_as_current_span("telegram.text_message.handle") as span:
        try:
            user_message = update.message.text
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id

            # Set span attributes
            span.set_attribute("user_id", str(user_id))
            span.set_attribute("chat_id", str(chat_id))
            span.set_attribute(
                "message_length", len(user_message) if user_message else 0
            )
            span.set_attribute("platform", "telegram")

            # Check if user is whitelisted
            from essence.chat.user_messages_sync import (
                is_user_whitelisted,
                is_user_owner,
            )

            is_whitelisted = is_user_whitelisted(str(user_id), "telegram")
            span.set_attribute("whitelisted", is_whitelisted)

            # Non-whitelisted users: Ignore completely (no response)
            if not is_whitelisted:
                logger.info(f"Ignoring message from non-whitelisted user {user_id}")
                span.set_attribute("action", "ignored")
                span.set_status(trace.Status(trace.StatusCode.OK))
                return  # Silently ignore - don't send any response

            # Get username if available
            username = None
            try:
                if update.effective_user.username:
                    username = f"@{update.effective_user.username}"
            except Exception:
                pass

            # Check if user is owner
            is_owner = is_user_owner(str(user_id), "telegram")
            span.set_attribute("is_owner", is_owner)

            if is_owner:
                # Owner: Create todorama task instead of appending to USER_MESSAGES.md
                logger.info(
                    f"Owner user {user_id} - creating todorama task for user interaction"
                )

                # Call command to create todorama task
                import subprocess
                import sys
                
                try:
                    # Determine user name for originator
                    # Owner users are "richard"
                    user_name = "richard" if is_owner else None
                    
                    # Build command to create user interaction task
                    cmd = [
                        sys.executable,
                        "-m",
                        "essence",
                        "create-user-interaction-task",
                        "--user-id", str(user_id),
                        "--chat-id", str(chat_id),
                        "--platform", "telegram",
                        "--content", user_message,
                        "--message-id", str(update.message.message_id),
                    ]
                    
                    if username:
                        cmd.extend(["--username", username])
                    
                    if user_name:
                        cmd.extend(["--originator", user_name])
                    
                    # Run command and capture output
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    
                    if result.returncode == 0:
                        span.set_attribute("action", "created_todorama_task")
                        logger.info(f"Successfully created todorama task for owner message")
                        
                        # Parse task creation response and send acknowledgment
                        try:
                            import json
                            output_lines = result.stdout.strip().split('\n')
                            # Find the JSON output (should be the last line)
                            task_output = None
                            for line in reversed(output_lines):
                                try:
                                    parsed = json.loads(line)
                                    if isinstance(parsed, dict) and "success" in parsed:
                                        task_output = parsed
                                        break
                                except json.JSONDecodeError:
                                    continue
                            
                            if task_output and task_output.get("success"):
                                task_data = task_output.get("task_data", {})
                                task_id = task_output.get("task_id") or task_data.get("id") or task_data.get("task_id")
                                
                                # Format task acknowledgment message
                                project_id = task_data.get("project_id", 1)
                                task_number = task_id if task_id else "?"
                                task_ref = f"june-{task_number}"
                                
                                created_at = task_data.get("created_at") or task_data.get("created_date")
                                if created_at:
                                    from datetime import datetime
                                    try:
                                        if isinstance(created_at, str):
                                            # Try parsing ISO format
                                            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                            created_date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                                        else:
                                            created_date_str = str(created_at)
                                    except:
                                        created_date_str = str(created_at)
                                else:
                                    from datetime import datetime
                                    created_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                
                                originator = task_data.get("originator") or user_name or "unknown"
                                assignee = task_data.get("agent_id") or task_data.get("assignee") or "looping_agent"
                                task_title = task_data.get("title") or title
                                task_description = task_data.get("description") or instruction
                                
                                # Format acknowledgment message
                                ack_message = (
                                    f"✅ **Task Created**\n\n"
                                    f"**Task:** `{task_ref}`\n"
                                    f"**Created:** {created_date_str}\n"
                                    f"**Created by:** {originator}\n"
                                    f"**Assigned to:** {assignee}\n\n"
                                    f"**{task_title}**\n"
                                    f"{task_description[:200]}{'...' if len(task_description) > 200 else ''}"
                                )
                                
                                # Send acknowledgment message
                                await update.message.reply_text(ack_message, parse_mode="Markdown")
                                logger.info(f"Sent task creation acknowledgment: {task_ref}")
                        except Exception as e:
                            logger.warning(f"Failed to send task acknowledgment: {e}", exc_info=True)
                            # Don't fail the whole operation if acknowledgment fails
                    else:
                        span.set_attribute("action", "task_creation_failed")
                        logger.error(
                            f"Failed to create todorama task: {result.stderr}"
                        )
                except Exception as e:
                    span.set_attribute("action", "task_creation_error")
                    logger.error(
                        f"Error creating todorama task: {e}", exc_info=True
                    )

                span.set_status(trace.Status(trace.StatusCode.OK))
                return

            else:
                # Whitelisted (non-owner): Forward to owner
                logger.info(
                    f"Whitelisted (non-owner) user {user_id} - forwarding message to owner"
                )

                # Get owner user IDs for forwarding
                from essence.chat.user_messages_sync import get_owner_users

                owner_users = get_owner_users("telegram")
                if not owner_users:
                    logger.warning(
                        "No owner users configured, cannot forward whitelisted user message"
                    )
                    span.set_attribute("action", "forward_failed_no_owner")
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    return

                # Forward to first owner (for now - could be enhanced to forward to all)
                owner_user_id = owner_users[0]

                # Create todorama task for forwarded message
                forward_content = f"[Forwarded from whitelisted user {user_id} (@{username or 'unknown'})] {user_message}"

                import subprocess
                import sys
                
                try:
                    # Forwarded messages are from the owner (richard)
                    user_name = "richard"
                    
                    # Build command to create user interaction task
                    cmd = [
                        sys.executable,
                        "-m",
                        "essence",
                        "create-user-interaction-task",
                        "--user-id", str(owner_user_id),
                        "--chat-id", str(chat_id),
                        "--platform", "telegram",
                        "--content", forward_content,
                        "--message-id", str(update.message.message_id),
                        "--originator", user_name,
                    ]
                    
                    if username:
                        cmd.extend(["--username", f"forwarded_from_{user_id}"])
                    
                    # Run command (non-blocking, fire-and-forget)
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    
                    if result.returncode == 0:
                        span.set_attribute("action", "forwarded_to_owner")
                        logger.info(
                            f"Successfully forwarded whitelisted user message to owner {owner_user_id}"
                        )
                    else:
                        span.set_attribute("action", "forward_failed")
                        logger.error(
                            f"Failed to forward whitelisted user message: {result.stderr}"
                        )
                except Exception as e:
                    span.set_attribute("action", "forward_error")
                    logger.error(
                        f"Error forwarding whitelisted user message: {e}", exc_info=True
                    )

                span.set_status(trace.Status(trace.StatusCode.OK))
                return

        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
