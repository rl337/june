"""
Coding Agent Interface

Provides an interface for sending coding tasks to the Qwen3 model via inference API.
Handles tool calling, code execution, file operations, and multi-turn conversations.
All operations run in containers - no host system pollution.
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import grpc
from june_grpc_api import llm_pb2_grpc
from june_grpc_api.llm_pb2 import (
    ChatMessage,
    ChatRequest,
    Context,
    GenerationParameters,
    ToolCall,
    ToolDefinition,
)
from opentelemetry import trace

from essence.chat.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class CodingAgent:
    """
    Coding agent that interfaces with the inference API for coding tasks.

    All operations happen in containers - no host system pollution.
    """

    def __init__(
        self,
        llm_url: str = "tensorrt-llm:8000",
        model_name: str = "Qwen/Qwen3-30B-A3B-Thinking-2507",
        max_context_length: int = 131072,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """
        Initialize the coding agent.

        Args:
            llm_url: gRPC endpoint for LLM inference service (default: "tensorrt-llm:8000" for TensorRT-LLM).
                    Can use "localhost:50051" for local testing, "inference-api:50051" for legacy service,
                    or "nim-qwen3:8001" for NVIDIA NIM.
            model_name: Name of the model to use
            max_context_length: Maximum context length for the model
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.llm_url = llm_url
        self.model_name = model_name
        self.max_context_length = max_context_length
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[llm_pb2_grpc.LLMInferenceStub] = None
        self._conversation_history: List[ChatMessage] = []
        self._workspace_dir: Optional[Path] = None
        self._available_tools: List[ToolDefinition] = []

        # Initialize available tools
        self._initialize_tools()

    def _ensure_connection(self) -> None:
        """Ensure gRPC connection to LLM inference service is established."""
        if self._channel is None or self._stub is None:
            self._channel = grpc.insecure_channel(self.llm_url)
            self._stub = llm_pb2_grpc.LLMInferenceStub(self._channel)
            logger.info(f"Connected to LLM inference service at {self.llm_url}")

    def _create_chat_message(self, role: str, content: str) -> ChatMessage:
        """Create a ChatMessage protobuf object."""
        return ChatMessage(role=role, content=content)

    def send_coding_task(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        reset_conversation: bool = False,
    ) -> Iterator[str]:
        """
        Send a coding task to the model and stream the response.

        Args:
            task_description: Description of the coding task
            context: Optional context (files, requirements, etc.)
            reset_conversation: If True, clear conversation history before sending

        Yields:
            Response chunks as they arrive from the model
        """
        with tracer.start_as_current_span("coding_agent.send_task") as span:
            try:
                span.set_attribute("task_length", len(task_description))
                span.set_attribute("has_context", context is not None)
                span.set_attribute("reset_conversation", reset_conversation)

                self._ensure_connection()

                # Reset conversation if requested
                if reset_conversation:
                    self._conversation_history = []
                    span.set_attribute("conversation_reset", True)

                # Build system message with coding context
                system_message = self._build_system_message(context)
                if system_message:
                    # Add system message if conversation is empty
                    if not self._conversation_history:
                        self._conversation_history.append(
                            self._create_chat_message("system", system_message)
                        )

                # Add user message
                user_message = self._create_chat_message("user", task_description)
                self._conversation_history.append(user_message)

                span.set_attribute(
                    "conversation_length", len(self._conversation_history)
                )

                # Create chat request with tools enabled
                chat_context = Context(
                    enable_tools=True,
                    available_tools=self._available_tools,
                    max_context_tokens=self.max_context_length,
                )

                request = ChatRequest(
                    messages=self._conversation_history,
                    params=GenerationParameters(
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        top_p=0.9,
                    ),
                    context=chat_context,
                    stream=True,
                )

                # Stream response from model and handle tool calls
                chunk_count = 0
                full_response = ""
                tool_calls: List[ToolCall] = []

                with tracer.start_as_current_span(
                    "coding_agent.stream_response"
                ) as stream_span:
                    for chunk in self._stub.ChatStream(request):
                        if chunk.chunk.role == "assistant":
                            content = chunk.chunk.content
                            if content:
                                chunk_count += 1
                                full_response += content
                                stream_span.set_attribute("chunk_count", chunk_count)
                                yield content

                            # Collect tool calls
                            if chunk.chunk.tool_calls:
                                tool_calls.extend(chunk.chunk.tool_calls)
                                stream_span.set_attribute(
                                    "tool_calls_count", len(tool_calls)
                                )

                        if chunk.is_final:
                            stream_span.set_attribute("is_final", True)
                            stream_span.set_attribute("total_chunks", chunk_count)
                            stream_span.set_attribute(
                                "response_length", len(full_response)
                            )
                            break

                # Handle tool calls if any
                if tool_calls:
                    span.set_attribute("has_tool_calls", True)
                    span.set_attribute("tool_calls_count", len(tool_calls))
                    tool_results = self._execute_tool_calls(tool_calls, span)

                    # Add tool results as a new message and continue conversation
                    if tool_results:
                        tool_message = self._create_tool_results_message(tool_results)
                        self._conversation_history.append(tool_message)

                        # Continue conversation with tool results
                        # (This would require another request - for now, we'll include results in the response)
                        yield f"\n\n[Tool execution completed. Results: {tool_results}]\n"

                # Add assistant response to conversation history
                if full_response:
                    assistant_message = self._create_chat_message(
                        "assistant", full_response
                    )
                    if tool_calls:
                        assistant_message.tool_calls.extend(tool_calls)
                    self._conversation_history.append(assistant_message)
                    span.set_attribute("response_length", len(full_response))
                    span.set_attribute("final_chunk_count", chunk_count)

            except grpc.RpcError as e:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"gRPC error in coding agent: {e}")
                raise RuntimeError(
                    f"Failed to communicate with inference API: {e}"
                ) from e
            except Exception as e:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"Error in coding agent: {e}", exc_info=True)
                raise

    def _initialize_tools(self) -> None:
        """Initialize available tools for the coding agent."""
        self._available_tools = [
            ToolDefinition(
                name="read_file",
                description=(
                    "Read the contents of a file. Use this to examine code files, "
                    "configuration files, or any text files."
                ),
                parameters_schema=json.dumps(
                    {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to read (relative to workspace root)",
                            }
                        },
                        "required": ["file_path"],
                    }
                ),
            ),
            ToolDefinition(
                name="write_file",
                description="Write content to a file. Use this to create or modify files.",
                parameters_schema=json.dumps(
                    {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to write (relative to workspace root)",
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write to the file",
                            },
                        },
                        "required": ["file_path", "content"],
                    }
                ),
            ),
            ToolDefinition(
                name="list_files",
                description="List files and directories in a directory.",
                parameters_schema=json.dumps(
                    {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": (
                                    "Directory path to list "
                                    "(relative to workspace root, defaults to workspace root)"
                                ),
                            }
                        },
                        "required": [],
                    }
                ),
            ),
            ToolDefinition(
                name="execute_command",
                description=(
                    "Execute a shell command in the workspace. Use this to run scripts, "
                    "tests, or any shell commands. Commands run in the workspace directory."
                ),
                parameters_schema=json.dumps(
                    {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to execute",
                            },
                            "working_directory": {
                                "type": "string",
                                "description": (
                                    "Working directory for the command "
                                    "(relative to workspace root, defaults to workspace root)"
                                ),
                            },
                        },
                        "required": ["command"],
                    }
                ),
            ),
            ToolDefinition(
                name="read_directory",
                description=(
                    "Get detailed information about files and subdirectories in a directory."
                ),
                parameters_schema=json.dumps(
                    {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": (
                                    "Directory path "
                                    "(relative to workspace root, defaults to workspace root)"
                                ),
                            }
                        },
                        "required": [],
                    }
                ),
            ),
        ]
        logger.info(f"Initialized {len(self._available_tools)} tools for coding agent")

    def set_workspace(self, workspace_dir: str) -> None:
        """
        Set the workspace directory for file operations.

        Args:
            workspace_dir: Path to workspace directory (all file operations are relative to this)
        """
        self._workspace_dir = Path(workspace_dir)
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace directory set to: {self._workspace_dir}")

    def _build_system_message(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        """
        Build system message with coding context.

        Args:
            context: Optional context dictionary with files, requirements, etc.

        Returns:
            System message string or None
        """
        if not context:
            return (
                "You are a helpful coding assistant. Write clean, well-documented code."
            )

        parts = [
            "You are a helpful coding assistant. Write clean, well-documented code."
        ]

        if "files" in context:
            parts.append("\nRelevant files:")
            for file_path, content in context["files"].items():
                parts.append(f"\n{file_path}:\n```\n{content}\n```")

        if "requirements" in context:
            parts.append(f"\nRequirements: {context['requirements']}")

        if "instructions" in context:
            parts.append(f"\nInstructions: {context['instructions']}")

        return "\n".join(parts)

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self._conversation_history = []
        logger.info("Conversation history reset")

    def _execute_tool_calls(
        self, tool_calls: List[ToolCall], parent_span: trace.Span
    ) -> Dict[str, Any]:
        """
        Execute tool calls and return results.

        Args:
            tool_calls: List of tool calls from the model
            parent_span: Parent tracing span

        Returns:
            Dictionary mapping tool call IDs to results
        """
        results = {}

        for tool_call in tool_calls:
            with tracer.start_as_current_span("coding_agent.execute_tool") as tool_span:
                try:
                    tool_span.set_attribute("tool_call_id", tool_call.id)
                    tool_span.set_attribute("tool_name", tool_call.function.name)

                    function_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_span.set_attribute("tool_arguments", json.dumps(arguments))

                    # Execute the tool
                    if function_name == "read_file":
                        result = self._tool_read_file(arguments)
                    elif function_name == "write_file":
                        result = self._tool_write_file(arguments)
                    elif function_name == "list_files":
                        result = self._tool_list_files(arguments)
                    elif function_name == "execute_command":
                        result = self._tool_execute_command(arguments)
                    elif function_name == "read_directory":
                        result = self._tool_read_directory(arguments)
                    else:
                        result = {"error": f"Unknown tool: {function_name}"}

                    results[tool_call.id] = result
                    tool_span.set_attribute("tool_success", "error" not in result)

                except Exception as e:
                    tool_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    tool_span.record_exception(e)
                    results[tool_call.id] = {"error": str(e)}
                    logger.error(
                        f"Error executing tool {tool_call.function.name}: {e}",
                        exc_info=True,
                    )

        return results

    def _create_tool_results_message(self, tool_results: Dict[str, Any]) -> ChatMessage:
        """Create a ChatMessage with tool execution results."""
        results_text = json.dumps(tool_results, indent=2)
        return self._create_chat_message("tool", results_text)

    def _tool_read_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: Read a file."""
        if not self._workspace_dir:
            return {"error": "Workspace directory not set"}

        file_path = arguments.get("file_path", "")
        if not file_path:
            return {"error": "file_path is required"}

        full_path = self._workspace_dir / file_path

        # Security: Ensure path is within workspace
        try:
            full_path.resolve().relative_to(self._workspace_dir.resolve())
        except ValueError:
            return {"error": f"Path {file_path} is outside workspace"}

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"content": content, "file_path": file_path}
        except FileNotFoundError:
            return {"error": f"File not found: {file_path}"}
        except Exception as e:
            return {"error": f"Error reading file: {str(e)}"}

    def _tool_write_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: Write to a file."""
        if not self._workspace_dir:
            return {"error": "Workspace directory not set"}

        file_path = arguments.get("file_path", "")
        content = arguments.get("content", "")

        if not file_path:
            return {"error": "file_path is required"}

        full_path = self._workspace_dir / file_path

        # Security: Ensure path is within workspace
        try:
            full_path.resolve().relative_to(self._workspace_dir.resolve())
        except ValueError:
            return {"error": f"Path {file_path} is outside workspace"}

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "file_path": file_path,
                "bytes_written": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"error": f"Error writing file: {str(e)}"}

    def _tool_list_files(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: List files in a directory."""
        if not self._workspace_dir:
            return {"error": "Workspace directory not set"}

        directory = arguments.get("directory", "")
        target_dir = (
            self._workspace_dir / directory if directory else self._workspace_dir
        )

        # Security: Ensure path is within workspace
        try:
            target_dir.resolve().relative_to(self._workspace_dir.resolve())
        except ValueError:
            return {"error": f"Directory {directory} is outside workspace"}

        try:
            items = []
            for item in target_dir.iterdir():
                items.append(
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "path": str(item.relative_to(self._workspace_dir)),
                    }
                )
            return {"items": items, "directory": directory or "."}
        except Exception as e:
            return {"error": f"Error listing directory: {str(e)}"}

    def _tool_read_directory(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: Get detailed directory information."""
        # For now, same as list_files
        return self._tool_list_files(arguments)

    def _tool_execute_command(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tool: Execute a shell command.

        All commands run in the workspace directory in a sandboxed environment.
        """
        if not self._workspace_dir:
            return {"error": "Workspace directory not set"}

        command = arguments.get("command", "")
        working_dir = arguments.get("working_directory", "")

        if not command:
            return {"error": "command is required"}

        # Determine working directory
        if working_dir:
            cmd_dir = self._workspace_dir / working_dir
            # Security: Ensure path is within workspace
            try:
                cmd_dir.resolve().relative_to(self._workspace_dir.resolve())
            except ValueError:
                return {
                    "error": f"Working directory {working_dir} is outside workspace"
                }
        else:
            cmd_dir = self._workspace_dir

        try:
            # Execute command in workspace directory
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cmd_dir),
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout for commands
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": command,
                "working_directory": str(cmd_dir.relative_to(self._workspace_dir)),
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out after 30 seconds", "command": command}
        except Exception as e:
            return {"error": f"Error executing command: {str(e)}", "command": command}

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history as a list of dicts."""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self._conversation_history
        ]

    def close(self) -> None:
        """Close the gRPC connection."""
        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("Closed connection to inference API")

    def __enter__(self):
        """Context manager entry."""
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
