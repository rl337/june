"""Helper module for calling chat response agent and formatting responses."""
import json
import logging
import subprocess
import os
import time
import threading
import queue
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Iterator, Tuple

# Add essence module to path for streaming_popen_generator
essence_path = Path(__file__).parent.parent.parent.parent / "essence"
sys.path.insert(0, str(essence_path))

from essence.chat.utils.streaming_popen import streaming_popen_generator

logger = logging.getLogger(__name__)

# Valid agent modes (matching prompt directory names)
VALID_AGENT_MODES = {
    "normal", "architect", "precommit", "refactor-planner", 
    "project-cleanup", "telegram-response"
}


def parse_agent_mode_from_message(user_message: str) -> Tuple[str, str]:
    """
    Parse agent mode from message prefix like !name.
    
    Args:
        user_message: The user's message
        
    Returns:
        Tuple of (cleaned_message, agent_mode) where:
        - cleaned_message: Message with !name prefix removed (if present)
        - agent_mode: Agent mode name (default: "telegram-response")
    """
    # Strip leading whitespace
    stripped = user_message.lstrip()
    
    # Check if message starts with !
    if not stripped.startswith("!"):
        return user_message, "telegram-response"
    
    # Find the end of the agent name (whitespace or end of string)
    # Look for !name pattern where name is alphanumeric and hyphens
    import re
    match = re.match(r"^!([a-zA-Z0-9-]+)(\s+|$)", stripped)
    if match:
        agent_name = match.group(1)
        # Check if it's a valid agent mode
        if agent_name in VALID_AGENT_MODES:
            # Remove the !name prefix and any following whitespace
            cleaned = user_message[len(stripped[:match.end()]):].lstrip()
            # If the cleaned message is empty, return the original (fallback)
            if not cleaned:
                return user_message, "telegram-response"
            logger.info(f"Parsed agent mode '{agent_name}' from message prefix")
            return cleaned, agent_name
    
    # If !name pattern doesn't match a valid agent, return original message
    return user_message, "telegram-response"


def call_chat_response_agent(
    user_message: str, 
    agenticness_dir: Optional[str] = None,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    agent_script_name: str = "telegram_response_agent.sh",
    agent_script_simple_name: str = "telegram_response_agent_simple.sh",
    platform: str = "telegram"
) -> Dict[str, Any]:
    """
    Call the chat response agent with a user message.
    
    Args:
        user_message: The message from the user (may contain !name prefix to select agent)
        agenticness_dir: Path to agenticness directory (defaults to ../agenticness)
        user_id: User ID for session identification (optional, but required for context preservation)
        chat_id: Chat ID for session identification (optional, but required for context preservation)
        agent_script_name: Name of the session-aware agent script
        agent_script_simple_name: Name of the simple agent script (no session)
        platform: Platform name (telegram, discord, etc.) for environment variables
    
    Returns:
        Dictionary with agent response or error information
    """
    # Parse agent mode from message prefix (e.g., !architect, !normal)
    cleaned_message, agent_mode = parse_agent_mode_from_message(user_message)
    
    if agenticness_dir is None:
        # Default to ../agenticness from service directory
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        agenticness_dir = os.path.join(script_dir, "agenticness")
    
    # Use session-aware script if user_id and chat_id are provided, otherwise fall back to simple script
    if user_id is not None and chat_id is not None:
        agent_script = os.path.join(agenticness_dir, "scripts", agent_script_name)
    else:
        logger.warning("user_id and chat_id not provided - using simple script without session support")
        agent_script = os.path.join(agenticness_dir, "scripts", agent_script_simple_name)
    
    if not os.path.exists(agent_script):
        logger.error(f"Agent script not found: {agent_script}")
        return {
            "error": "Agent script not found",
            "message": f"The {platform} response agent is not available."
        }
    
    if not os.access(agent_script, os.X_OK):
        logger.error(f"Agent script is not executable: {agent_script}")
        return {
            "error": "Agent script not executable",
            "message": "The TelegramResponse agent script is not executable."
        }
    
    try:
        # Set environment variables for the agent
        env = os.environ.copy()
        env["CURSOR_AGENT_EXE"] = env.get("CURSOR_AGENT_EXE", "cursor-agent")
        env["AGENT_ID"] = env.get("AGENT_ID", f"{platform}-response-agent")
        env["AGENT_TIMEOUT"] = env.get("AGENT_TIMEOUT", "300")
        env["TODO_SERVICE_URL"] = env.get("TODO_SERVICE_URL", "http://localhost:8000/mcp/todo-mcp-service")
        
        # Set AGENT_MODE from parsed message prefix
        env["AGENT_MODE"] = agent_mode
        
        # Set AGENTICNESS_STATE_DIR so the script uses the correct session directory
        # This must be set before the script sources session_manager.sh
        agenticness_state_dir = os.getenv("AGENTICNESS_STATE_DIR", "/home/rlee/june_data/agenticness-state")
        env["AGENTICNESS_STATE_DIR"] = agenticness_state_dir
        
        # Remove CURSOR_API_KEY from environment - let cursor-agent use auth.json
        # Setting it causes "invalid API key" errors even when logged in
        if "CURSOR_API_KEY" in env:
            del env["CURSOR_API_KEY"]
        
        # Set environment variables for session identification if provided
        if user_id is not None and chat_id is not None:
            env[f"{platform.upper()}_USER_ID"] = str(user_id)
            env[f"{platform.upper()}_CHAT_ID"] = str(chat_id)
            logger.info(f"Using session-aware agent for user {user_id}, chat {chat_id}, mode: {agent_mode}")
        
        # Call the agent script with bash -x for debugging
        # CRITICAL: cursor-agent requires a PTY (isTTY check fails otherwise)
        # Use pty.fork() which creates a PTY pair and forks in one call
        logger.info(f"Calling {platform} response agent (mode: {agent_mode}) with message: {cleaned_message[:50]}...")
        import pty
        import select
        
        # Build command arguments with cleaned message (with !name prefix removed)
        script_args = [cleaned_message]
        if user_id is not None and chat_id is not None:
            script_args = [str(user_id), str(chat_id), cleaned_message]
        
        # pty.fork() creates a PTY pair and forks, returning (pid, master_fd)
        # The child process automatically gets the slave PTY as its controlling terminal
        pid, master_fd = pty.fork()
        
        if pid == 0:
            # Child process - execute the command
            # The slave PTY is already set up as the controlling terminal
            os.execve("/bin/bash", ["bash", "-x", agent_script] + script_args, env)
        else:
            # Parent process - read output from master_fd
            output_chunks = []
            import time
            
            try:
                start_time = time.time()
                timeout = 320  # Match agent timeout
                
                while time.time() - start_time < timeout:
                    ready, _, _ = select.select([master_fd], [], [], 0.1)
                    if ready:
                        try:
                            data = os.read(master_fd, 4096)
                            if data:
                                output_chunks.append(data)
                                logger.debug(f"Read {len(data)} bytes from PTY")
                            # Don't break on empty data - might be temporary
                        except (OSError, EOFError) as e:
                            # I/O error might be normal when process closes PTY
                            logger.debug(f"PTY read error (might be normal): {e}")
                            # Continue to check if process is done
                    
                    # Check if process is done (non-blocking)
                    try:
                        wait_result = os.waitpid(pid, os.WNOHANG)
                        if wait_result[0] == pid:
                            # Process finished, read any remaining output
                            logger.debug("Child process finished, reading remaining output")
                            remaining_attempts = 10
                            while remaining_attempts > 0:
                                ready, _, _ = select.select([master_fd], [], [], 0.1)
                                if not ready:
                                    remaining_attempts -= 1
                                    if remaining_attempts <= 0:
                                        break
                                    continue
                                try:
                                    data = os.read(master_fd, 4096)
                                    if data:
                                        output_chunks.append(data)
                                        logger.debug(f"Read {len(data)} remaining bytes")
                                    remaining_attempts -= 1
                                except (OSError, EOFError):
                                    break
                            # Get the exit status from the wait_result we already have
                            status = wait_result[1]
                            returncode = os.WEXITSTATUS(status)
                            break
                    except OSError:
                        # Process not finished yet
                        pass
                else:
                    # Timeout - kill the process
                    logger.warning("Agent process timed out, killing it")
                    try:
                        os.kill(pid, 15)  # SIGTERM
                        _, status = os.waitpid(pid, 0)
                        returncode = os.WEXITSTATUS(status)
                    except OSError:
                        returncode = 124  # Timeout exit code
                
                # If we didn't get the returncode yet (shouldn't happen, but be safe)
                if 'returncode' not in locals():
                    try:
                        _, status = os.waitpid(pid, 0)
                        returncode = os.WEXITSTATUS(status)
                    except OSError:
                        # Process already reaped or doesn't exist
                        returncode = 1
                
                # Decode output
                stdout = b''.join(output_chunks).decode('utf-8', errors='replace')
                stderr = ""  # Combined in stdout from PTY
                
                logger.debug(f"Agent completed with return code {returncode}, output length: {len(stdout)}")
                
                result = subprocess.CompletedProcess(
                    args=["bash", "-x", agent_script] + script_args,
                    returncode=returncode,
                    stdout=stdout,
                    stderr=stderr
                )
            finally:
                try:
                    os.close(master_fd)
                except:
                    pass
        
        if result.returncode != 0:
            logger.error(f"Agent script failed with exit code {result.returncode}")
            logger.error(f"Agent stderr: {result.stderr}")
            logger.error(f"Agent stdout: {result.stdout[:1000] if result.stdout else '(empty)'}")
            # Include more details in error response for debugging
            error_details = result.stderr[:500] if result.stderr else "No error output"
            stdout_preview = result.stdout[:500] if result.stdout else "No output"
            return {
                "error": f"Agent execution failed (exit code {result.returncode})",
                "message": "I encountered an error processing your request. Please try again.",
                "stderr": error_details,
                "stdout_preview": stdout_preview,
                "exit_code": result.returncode
            }
        
        # Parse stream-json output (multiple JSON objects, one per line)
        # The script now outputs stream-json directly to stdout (no file-based approach)
        try:
            agent_output = result.stdout.strip()
            
            # Parse stream-json format: each line is a separate JSON object
            # Extract human-readable response text from various JSON object types
            final_result_text = None
            
            for line in agent_output.split('\n'):
                line = line.strip()
                # Skip non-JSON lines (log messages, bash debug output, etc.)
                if not line or not line.startswith('{'):
                    continue
                
                try:
                    json_obj = json.loads(line)
                    obj_type = json_obj.get("type", "")
                    subtype = json_obj.get("subtype", "")
                    
                    # Skip intermediate states like "thinking"
                    if obj_type == "thinking":
                        continue
                    
                    # Check for assistant messages (these contain the actual response)
                    if obj_type == "assistant":
                        message = json_obj.get("message", {})
                        if isinstance(message, dict):
                            content = message.get("content", [])
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text = item.get("text", "").strip()
                                        if text and len(text) > 10:
                                            # Filter out descriptions
                                            if not text.startswith(("Writing", "Wrote", "Created", "Updated", "Response written")):
                                                final_result_text = text
                    
                    # Check for result objects (final result)
                    if obj_type == "result" and subtype == "success":
                        result_text = json_obj.get("result", "")
                        if result_text and isinstance(result_text, str) and len(result_text.strip()) > 10:
                            # Filter out descriptions
                            if not result_text.strip().startswith(("Writing", "Wrote", "Created", "Updated", "Response written")):
                                final_result_text = result_text.strip()
                    
                    # Check for tool_call results (in case agent used tools)
                    if obj_type == "tool_call" and subtype == "completed":
                        tool_call = json_obj.get("tool_call", {})
                        if "editToolCall" in tool_call:
                            edit_result = tool_call["editToolCall"].get("result", {})
                            if "success" in edit_result:
                                file_content = edit_result["success"].get("afterFullFileContent", "")
                                if file_content and isinstance(file_content, str) and len(file_content.strip()) > 10:
                                    # Filter out descriptions
                                    if not file_content.strip().startswith(("Writing", "Wrote", "Created", "Updated")):
                                        final_result_text = file_content.strip()
                
                except json.JSONDecodeError:
                    # Skip invalid JSON lines (log messages, etc.)
                    continue
            
            if final_result_text:
                # Clean up the result text
                final_result_text = final_result_text.strip()
                return {
                    "message": final_result_text,
                    "response": final_result_text
                }
            else:
                # No result found in stream-json, return error
                logger.warning("No result found in stream-json output")
                logger.debug(f"Agent stdout (first 1000 chars): {result.stdout[:1000]}")
                return {
                    "error": "No response generated",
                    "message": "I received your message but couldn't generate a response. Please try again."
                }
                
        except Exception as e:
            logger.error(f"Failed to parse agent stream-json output: {e}", exc_info=True)
            logger.error(f"Agent stdout (first 1000 chars): {result.stdout[:1000]}")
            # Return error message
            return {
                "error": "Failed to parse agent response",
                "message": "I encountered an error processing your message. Please try again."
            }
    
    except subprocess.TimeoutExpired:
        logger.error("Agent script timed out")
        return {
            "error": "Agent execution timed out",
            "message": "Your request took too long to process. Please try a simpler request."
        }
    except Exception as e:
        logger.error(f"Error calling agent script: {e}", exc_info=True)
        return {
            "error": str(e),
            "message": "I encountered an error processing your request. Please try again."
        }


def stream_chat_response_agent(
    user_message: str,
    agenticness_dir: Optional[str] = None,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    line_timeout: float = 30.0,  # Timeout if no JSON line received for this many seconds
    max_total_time: float = 300.0,  # Maximum total time for the entire operation
    agent_script_name: str = "telegram_response_agent.sh",
    agent_script_simple_name: str = "telegram_response_agent_simple.sh",
    platform: str = "telegram"
) -> Iterator[Tuple[str, bool]]:
    """
    Stream responses from the chat response agent as they arrive.
    
    Uses subprocess.Popen to stream output line-by-line, parsing JSON as it arrives
    and extracting human-readable text. Only yields actual response text, filtering
    out intermediate states like "thinking".
    
    Args:
        user_message: The message from the user (may contain !name prefix to select agent)
        agenticness_dir: Path to agenticness directory (defaults to ../agenticness)
        user_id: User ID for session identification
        chat_id: Chat ID for session identification
        line_timeout: Seconds to wait for a new JSON line before timing out
        max_total_time: Maximum total seconds for the entire operation
        agent_script_name: Name of the session-aware agent script
        agent_script_simple_name: Name of the simple agent script (no session)
        platform: Platform name (telegram, discord, etc.) for environment variables
    
    Yields:
        Tuples of (message_text, is_final) where:
        - message_text: Human-readable text to send to the chat platform
        - is_final: True if this is the final message, False for intermediate messages
    """
    # Parse agent mode from message prefix (e.g., !architect, !normal)
    cleaned_message, agent_mode = parse_agent_mode_from_message(user_message)
    
    if agenticness_dir is None:
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        agenticness_dir = os.path.join(script_dir, "agenticness")
    
    # Use session-aware script if user_id and chat_id are provided
    if user_id is not None and chat_id is not None:
        agent_script = os.path.join(agenticness_dir, "scripts", agent_script_name)
    else:
        logger.warning("user_id and chat_id not provided - using simple script without session support")
        agent_script = os.path.join(agenticness_dir, "scripts", agent_script_simple_name)
    
    if not os.path.exists(agent_script):
        logger.error(f"Agent script not found: {agent_script}")
        yield (f"⚠️ The {platform} response agent is not available.", True)
        return
    
    if not os.access(agent_script, os.X_OK):
        logger.error(f"Agent script is not executable: {agent_script}")
        yield (f"⚠️ The {platform} response agent script is not executable.", True)
        return
    
    # Set environment variables for the agent
    env = os.environ.copy()
    env["CURSOR_AGENT_EXE"] = env.get("CURSOR_AGENT_EXE", "cursor-agent")
    env["AGENT_ID"] = env.get("AGENT_ID", f"{platform}-response-agent")
    env["AGENT_TIMEOUT"] = env.get("AGENT_TIMEOUT", "300")
    env["TODO_SERVICE_URL"] = env.get("TODO_SERVICE_URL", "http://localhost:8004")
    
    # Set AGENT_MODE from parsed message prefix
    env["AGENT_MODE"] = agent_mode
    
    agenticness_state_dir = os.getenv("AGENTICNESS_STATE_DIR", "/home/rlee/june_data/agenticness-state")
    env["AGENTICNESS_STATE_DIR"] = agenticness_state_dir
    
    if "CURSOR_API_KEY" in env:
        del env["CURSOR_API_KEY"]
    
    if user_id is not None and chat_id is not None:
        env[f"{platform.upper()}_USER_ID"] = str(user_id)
        env[f"{platform.upper()}_CHAT_ID"] = str(chat_id)
        logger.info(f"Streaming agent response for user {user_id}, chat {chat_id}, mode: {agent_mode}")
    
    # Build command arguments with cleaned message (with !name prefix removed)
    script_args = [cleaned_message]
    if user_id is not None and chat_id is not None:
        script_args = [str(user_id), str(chat_id), cleaned_message]
    
    # Use streaming_popen_generator utility for proper PTY-based streaming
    command = ["/bin/bash", "-x", agent_script] + script_args
    
    start_time = time.time()
    last_json_line_time = start_time
    last_message_yield_time = start_time
    seen_messages = set()  # Track messages we've already yielded to avoid duplicates
    pending_messages = []  # Queue of messages waiting to be yielded (for pacing)
    accumulated_message = ""  # Track the longest/fullest message we've seen
    
    try:
        # Minimum time between yielding messages (pacing) - 0.5 seconds
        min_message_interval = 0.5
        # Maximum time to wait before showing partial response - 2 seconds
        max_wait_for_first_message = 2.0
        
        first_message_sent = False
        
        # Use the streaming_popen_generator utility
        for line, is_final_line in streaming_popen_generator(command, env=env, chunk_size=1024, read_timeout=0.05):
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Check total timeout
            if elapsed > max_total_time:
                logger.warning(f"Agent stream exceeded max total time ({max_total_time}s)")
                yield ("⏱️ The request took too long to process. Please try a simpler request.", True)
                break
            
            # Process JSON lines - only process complete, valid JSON
            if line and line.startswith('{'):
                last_json_line_time = current_time
                # Try to parse JSON first to ensure it's complete
                try:
                    json_obj = json.loads(line)  # Validate JSON is complete
                except json.JSONDecodeError:
                    # Incomplete JSON line, skip it
                    continue
                
                # Check if this is a result message (full accumulated text)
                obj_type = json_obj.get("type", "")
                is_result = obj_type == "result" and json_obj.get("subtype") == "success"
                
                message = _extract_human_readable_from_json_line(line)
                if message:
                    message_updated = False
                    
                    if is_result:
                        # Result message contains the full accumulated text - replace accumulated with it
                        # Also validate that our chunk appending worked correctly
                        if accumulated_message:
                            # Validate: check if appended chunks match result (allowing for newlines)
                            appended_normalized = accumulated_message.replace('\n\n', '\n')
                            result_normalized = message.replace('\n\n', '\n')
                            
                            if appended_normalized == result_normalized:
                                logger.info(f"✅ Chunk appending validated: appended chunks match result ({len(accumulated_message)} chars)")
                            else:
                                # Log the difference for debugging
                                logger.warning(
                                f"⚠️ Chunk appending mismatch: "
                                f"appended={len(accumulated_message)} chars, result={len(message)} chars. "
                                f"Using result as authoritative."
                            )
                        
                        accumulated_message = message
                        message_updated = True
                        logger.info(f"Replaced with result message (full accumulated): {len(message)} chars")
                    else:
                        # Assistant message: check if it's a delta chunk or full accumulated
                        logger.info(f"Extracted assistant chunk: length={len(message)}, preview={message[:100]}...")
                        if accumulated_message:
                            # If this chunk contains the accumulated message, it's the full accumulated - replace
                            if accumulated_message in message:
                                logger.info(f"Assistant chunk contains accumulated - replacing: {len(accumulated_message)} -> {len(message)} chars")
                                accumulated_message = message
                                message_updated = True
                            elif message in accumulated_message:
                                # This chunk is a prefix/substring of what we already have - skip it (duplicate/restart)
                                logger.debug(f"Skipping duplicate/restart chunk: {len(message)} chars (already have {len(accumulated_message)} chars)")
                                message_updated = False
                            elif len(message) > len(accumulated_message) * 0.8 and message.startswith(accumulated_message[:20] if len(accumulated_message) >= 20 else accumulated_message):
                                # Chunk is significantly long and starts with the same pattern - likely full accumulated
                                # This handles cases where cursor-agent sends the full message after sending partial chunks
                                logger.info(f"Detected full accumulated message (long restart pattern): {len(accumulated_message)} -> {len(message)} chars")
                                accumulated_message = message
                                message_updated = True
                            else:
                                # Delta chunk - append directly (no separators, chunks should fit together)
                                old_accumulated = accumulated_message
                                accumulated_message = accumulated_message + message
                                message_updated = True
                                logger.info(
                                    f"Appending assistant delta chunk. "
                                    f"Old: {old_accumulated[:50]}... ({len(old_accumulated)} chars), "
                                    f"New chunk: {message[:50]}... ({len(message)} chars), "
                                    f"Combined: {len(accumulated_message)} chars"
                                )
                        else:
                            # First message - always accept it
                            accumulated_message = message
                            message_updated = True
                            logger.info(f"First assistant chunk: {len(accumulated_message)} chars")
                    
                    # Always yield the accumulated message when it updates, so Telegram can update in place
                    if message_updated:
                        # Update seen_messages with the accumulated message
                        seen_messages.discard(accumulated_message)  # Remove old if exists
                        seen_messages.add(accumulated_message)
                        
                        # Clear pending and add the new accumulated message
                        pending_messages = [(accumulated_message, current_time)]
                        
                        # If this is the first message and we've waited long enough, send it immediately
                        if not first_message_sent and elapsed >= max_wait_for_first_message:
                            first_message_sent = True
                            logger.info(f"Yielding first message after {elapsed:.2f}s: length={len(accumulated_message)}")
                            yield (accumulated_message, False)
                            last_message_yield_time = current_time
                            # Remove from pending since we just sent it
                            pending_messages = []
                        elif first_message_sent:
                            # We've already sent a message, yield the updated one immediately
                            # This allows Telegram to update the message in place
                            logger.info(f"Yielding updated accumulated message: length={len(accumulated_message)}")
                            yield (accumulated_message, False)
                            last_message_yield_time = current_time
                            pending_messages = []
            
            # Yield pending messages if enough time has passed (pacing)
            if pending_messages:
                time_since_last_yield = current_time - last_message_yield_time
                if time_since_last_yield >= min_message_interval:
                    # Send the accumulated message (should be the longest/fullest version)
                    message, _ = pending_messages.pop(0)
                    first_message_sent = True
                    logger.info(f"Yielding pending message after {time_since_last_yield:.2f}s: length={len(message)}")
                    yield (message, False)
                    last_message_yield_time = current_time
            
            # If this is the final line from the generator, process remaining messages
            if is_final_line:
                logger.info(f"Received final line from generator. pending_messages={len(pending_messages)}, seen_messages={len(seen_messages)}")
                # Process any remaining pending messages quickly
                for message, _ in pending_messages:
                    if message not in seen_messages or not first_message_sent:
                        logger.info(f"Yielding remaining pending message: length={len(message)}")
                        yield (message, False)
                        first_message_sent = True
                
                # Check for timeout on final line
                time_since_last_json = current_time - last_json_line_time
                if time_since_last_json > line_timeout and last_json_line_time > start_time:
                    logger.warning(f"No JSON line received for {time_since_last_json}s before final line")
                
                # Final message indicating completion
                if first_message_sent:
                    # We've already sent messages, just mark as final
                    logger.info(f"Yielding final signal. Total messages sent: {len(seen_messages)}")
                    yield ("", True)  # Empty message with is_final=True to signal completion
                else:
                    # No messages were extracted, send error
                    logger.warning("No messages were extracted from stream")
                    yield ("⚠️ I received your message but couldn't generate a response. Please try again.", True)
                break
    
    except Exception as e:
        logger.error(f"Error streaming agent response: {e}", exc_info=True)
        yield ("❌ I encountered an error processing your message. Please try again.", True)


def _extract_human_readable_from_json_line(line: str) -> Optional[str]:
    """
    Extract human-readable text from a JSON line in stream-json format.
    
    Filters out intermediate states like "thinking" and only returns
    actual response text that should be sent to the chat platform.
    
    Args:
        line: A single line that should be a JSON object
    
    Returns:
        Human-readable text to send to the chat platform, or None if no valid text found
    """
    try:
        json_obj = json.loads(line)
        
        # Skip intermediate states
        obj_type = json_obj.get("type", "")
        subtype = json_obj.get("subtype", "")
        
        # Filter out "thinking" and other intermediate states
        if obj_type == "thinking" or subtype == "thinking":
            return None
        
        # Look for actual response text in various places
        # 1. Check for tool_call results with file content
        if obj_type == "tool_call" and subtype == "completed":
            tool_call = json_obj.get("tool_call", {})
            for tool_key in tool_call:
                tool_result = tool_call.get(tool_key, {})
                if isinstance(tool_result, dict):
                    result_obj = tool_result.get("result", {})
                    if isinstance(result_obj, dict):
                        # Check for success with content
                        if "success" in result_obj:
                            success_obj = result_obj["success"]
                            for content_key in ["afterFullFileContent", "content", "text", "message", "output"]:
                                content = success_obj.get(content_key, "")
                                if content and isinstance(content, str) and len(content.strip()) > 10:
                                    # Filter out descriptions
                                    if not content.strip().startswith(("Writing", "Wrote", "Created", "Updated")):
                                        return content.strip()
        
        # 2. Check for assistant messages (these contain the actual response text)
        if obj_type == "assistant":
            message = json_obj.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "").strip()
                            if text and len(text) > 5:  # Lower threshold for earlier messages
                                # Filter out descriptions but allow partial responses
                                if not text.strip().startswith(("Writing", "Wrote", "Created", "Updated", "Response written")):
                                    # Return the full text, not just the first chunk
                                    # The streaming function will handle chunking if needed
                                    return text.strip()
        
        # 3. Check for result objects (but be careful - these might be descriptions)
        if obj_type == "result" and subtype == "success":
            result_text = json_obj.get("result", "")
            if result_text and isinstance(result_text, str) and len(result_text.strip()) > 5:  # Lower threshold
                # Filter out descriptions
                if not result_text.strip().startswith(("Writing", "Wrote", "Created", "Updated", "Response written")):
                    return result_text.strip()
        
        # 4. Check for message/content fields directly
        for field in ["message", "content", "text", "response"]:
            value = json_obj.get(field, "")
            if value and isinstance(value, str) and len(value.strip()) > 5:  # Lower threshold
                if not value.strip().startswith(("Writing", "Wrote", "Created", "Updated", "Response written")):
                    return value.strip()
        
        return None
    
    except json.JSONDecodeError:
        # Not a JSON line, skip it
        return None
    except Exception as e:
        logger.debug(f"Error extracting text from JSON line: {e}")
        return None


def format_agent_response(response_data: Dict[str, Any], max_length: int = 4096) -> str:
    """
    Format agent response data into human-readable message.
    
    Args:
        response_data: Dictionary from agent response
        max_length: Maximum message length (default 4096 for Telegram)
    
    Returns:
        Formatted message string
    """
    # If there's an error, return error message
    if "error" in response_data:
        error_msg = response_data.get("message", "An error occurred.")
        if "exit_code" in response_data:
            return f"❌ {error_msg}"
        return f"⚠️ {error_msg}"
    
    # Extract the message text
    message = response_data.get("message") or \
              response_data.get("response") or \
              response_data.get("text") or \
              response_data.get("content")
    
    if message:
        message_str = str(message)
        # Truncate if exceeds max length
        if len(message_str) > max_length:
            # Truncate and add indicator
            message_str = message_str[:max_length-10] + "\n\n... (message truncated)"
        return message_str
    
    # If we have structured data, format it nicely
    if "tasks" in response_data:
        tasks = response_data["tasks"]
        if isinstance(tasks, list) and len(tasks) > 0:
            lines = ["📋 **Tasks:**\n"]
            for task in tasks[:10]:  # Limit to 10 tasks
                task_id = task.get("id", "?")
                title = task.get("title", "Untitled")
                status = task.get("task_status", "unknown")
                lines.append(f"• Task {task_id}: {title} ({status})")
            return "\n".join(lines)
    
    if "projects" in response_data:
        projects = response_data["projects"]
        if isinstance(projects, list) and len(projects) > 0:
            lines = ["📁 **Projects:**\n"]
            for project in projects[:10]:
                project_id = project.get("id", "?")
                name = project.get("name", "Unnamed")
                lines.append(f"• {name} (ID: {project_id})")
            return "\n".join(lines)
    
    # Fallback: return JSON representation (formatted)
    try:
        return json.dumps(response_data, indent=2)
    except:
        return str(response_data)

