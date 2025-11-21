"""
LLM Client for Agentic Reasoning

Provides a unified interface for LLM interactions used by reasoning components.
Supports both gRPC (TensorRT-LLM, legacy inference-api) and HTTP (NVIDIA NIM) protocols.
"""
import logging
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

import grpc
import httpx
from june_grpc_api import llm_pb2_grpc
from june_grpc_api.llm_pb2 import (
    ChatMessage,
    ChatRequest,
    Context,
    FunctionCall,
    GenerationParameters,
    ToolCall,
)
from opentelemetry import trace

from essence.chat.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class LLMClient:
    """
    LLM client for agentic reasoning components.

    Provides methods for thinking, planning, and reflection phases.
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
        Initialize the LLM client.

        Args:
            llm_url: LLM endpoint URL. Supports:
                    - gRPC: "tensorrt-llm:8000" (default), "inference-api:50051", "grpc://nim-qwen3:8001"
                    - HTTP: "http://nim-qwen3:8000" (NVIDIA NIM OpenAI-compatible API)
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

        # Detect protocol from URL
        if "://" in llm_url:
            # URL has explicit scheme
            parsed = urlparse(llm_url)
            self._protocol = parsed.scheme
            self._host = parsed.hostname or parsed.netloc.split(":")[0]
            self._port = parsed.port or (8000 if self._protocol in ["http", "https"] else 8001)
            # Ensure protocol is valid
            if self._protocol not in ["http", "https", "grpc"]:
                # If unknown scheme, default based on port
                if self._port in [8000, 8003] and "nim" in self._host.lower():
                    self._protocol = "http"
                    logger.warning(f"Unknown scheme '{parsed.scheme}', defaulting to HTTP for NIM service")
                else:
                    self._protocol = "grpc"
                    logger.warning(f"Unknown scheme '{parsed.scheme}', defaulting to gRPC")
        else:
            # No scheme - parse as host:port
            if ":" in llm_url:
                parts = llm_url.split(":")
                self._host = parts[0]
                try:
                    self._port = int(parts[1])
                except (ValueError, IndexError):
                    self._port = 8001  # Default gRPC port
            else:
                self._host = llm_url
                self._port = 8001  # Default gRPC port
            
            # Detect protocol based on hostname and port
            if "nim" in self._host.lower() and self._port in [8000, 8003]:
                self._protocol = "http"
                logger.info(f"Detected NIM service ({self._host}:{self._port}) - using HTTP protocol")
            else:
                self._protocol = "grpc"
        
        # Map model name for NIM (NIM expects "Qwen/Qwen3-32B", not full HuggingFace path)
        if self._protocol == "http" and "nim" in self._host.lower():
            # NIM model name mapping
            if "qwen3" in self.model_name.lower() and "32b" in self.model_name.lower():
                # Map any Qwen3-32B variant to the NIM model name
                self._nim_model_name = "Qwen/Qwen3-32B"
                logger.debug(f"Mapped model name '{self.model_name}' to NIM model '{self._nim_model_name}'")
            else:
                # Use model name as-is (may need adjustment for other models)
                self._nim_model_name = self.model_name
        else:
            self._nim_model_name = None  # Not using NIM
        
        # gRPC connection (for TensorRT-LLM, legacy inference-api)
        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[llm_pb2_grpc.LLMInferenceStub] = None
        
        # HTTP client (for NVIDIA NIM OpenAI-compatible API)
        self._http_client: Optional[httpx.Client] = None
        self._http_base_url: Optional[str] = None

    def _ensure_connection(self) -> None:
        """Ensure connection to LLM inference service is established (gRPC or HTTP)."""
        if self._protocol == "http":
            # HTTP connection (NVIDIA NIM OpenAI-compatible API)
            if self._http_client is None:
                # Build base URL
                if not self._http_base_url:
                    self._http_base_url = f"http://{self._host}:{self._port}"
                self._http_client = httpx.Client(timeout=120.0)  # Longer timeout for LLM inference
                logger.info(f"Initialized HTTP client for LLM service at {self._http_base_url}")
        else:
            # gRPC connection (TensorRT-LLM, legacy inference-api)
            if self._channel is None or self._stub is None:
                # Build gRPC address (host:port format)
                grpc_address = f"{self._host}:{self._port}"
                self._channel = grpc.insecure_channel(grpc_address)
                self._stub = llm_pb2_grpc.LLMInferenceStub(self._channel)
                logger.info(f"Connected to LLM inference service via gRPC at {grpc_address}")

    def _create_chat_message(self, role: str, content: str) -> ChatMessage:
        """Create a ChatMessage protobuf object."""
        return ChatMessage(role=role, content=content)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[str]:
        """
        Generate text from a prompt.

        Args:
            prompt: The input prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (overrides default)
            max_tokens: Maximum tokens to generate (overrides default)
            stream: Whether to stream the response

        Yields:
            Response chunks as they arrive (if stream=True)
        """
        with tracer.start_as_current_span("llm_client.generate") as span:
            try:
                span.set_attribute("prompt_length", len(prompt))
                span.set_attribute("stream", stream)
                span.set_attribute("protocol", self._protocol)

                self._ensure_connection()

                if self._protocol == "http":
                    # HTTP/OpenAI-compatible API (NVIDIA NIM)
                    yield from self._generate_http(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=stream,
                        span=span,
                        tools=tools,
                        messages=None,  # LLMClient.generate() doesn't support messages yet
                    )
                else:
                    # gRPC API (TensorRT-LLM, legacy inference-api)
                    # Build messages
                    messages: List[ChatMessage] = []
                    if system_prompt:
                        messages.append(self._create_chat_message("system", system_prompt))
                    messages.append(self._create_chat_message("user", prompt))

                    # Create request
                    request = ChatRequest(
                        messages=messages,
                        params=GenerationParameters(
                            temperature=temperature or self.temperature,
                            max_tokens=max_tokens or self.max_tokens,
                            top_p=0.9,
                        ),
                        context=Context(
                            enable_tools=False,
                            max_context_tokens=self.max_context_length,
                        ),
                        stream=stream,
                    )

                    # Generate response
                    if stream:
                        for chunk in self._stub.ChatStream(request):
                            if chunk.chunk.role == "assistant":
                                content = chunk.chunk.content
                                if content:
                                    yield content
                    else:
                        # Non-streaming: collect all chunks
                        response = ""
                        for chunk in self._stub.ChatStream(request):
                            if chunk.chunk.role == "assistant":
                                content = chunk.chunk.content
                                if content:
                                    response += content
                        yield response

            except Exception as e:
                logger.error(f"Error generating text: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    def _generate_http(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        span: Optional[trace.Span] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[str]:
        """
        Generate text using HTTP/OpenAI-compatible API (NVIDIA NIM).

        Args:
            prompt: The input prompt (used if messages is None)
            system_prompt: Optional system prompt (used if messages is None)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            span: OpenTelemetry span for tracing
            tools: Optional list of OpenAI-format tool definitions for function calling
            messages: Optional list of OpenAI-format messages (if provided, prompt and system_prompt are ignored)

        Yields:
            Response chunks as they arrive
        """
        # Build messages in OpenAI format
        if messages is not None:
            # Use provided messages directly
            openai_messages = messages
        else:
            # Build messages from prompt/system_prompt (backward compatibility)
            openai_messages: List[Dict[str, Any]] = []
            if system_prompt:
                openai_messages.append({"role": "system", "content": system_prompt})
            openai_messages.append({"role": "user", "content": prompt})

        # Build request payload
        # Use NIM-specific model name if available, otherwise use default
        model_name_for_request = self._nim_model_name if self._nim_model_name else self.model_name
        payload = {
            "model": model_name_for_request,
            "messages": openai_messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": stream,
        }
        
        # Add tools if provided (for function calling)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"  # Let model decide when to call functions

        url = f"{self._http_base_url}/v1/chat/completions"
        
        try:
            if stream:
                # Streaming response
                # Collect function calls incrementally (OpenAI streams them in parts)
                accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}  # Index -> tool call
                
                with self._http_client.stream(
                    "POST", url, json=payload, timeout=120.0
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            if data_str == "[DONE]":
                                # Finalize any accumulated function calls
                                if accumulated_tool_calls:
                                    final_tool_calls = [tc for idx, tc in sorted(accumulated_tool_calls.items())]
                                    yield f"\n[FUNCTION_CALLS:{json.dumps(final_tool_calls)}]"
                                break
                            try:
                                import json
                                data = json.loads(data_str)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                                    
                                    # Handle function calls (streamed incrementally)
                                    if "tool_calls" in delta:
                                        for tool_call_delta in delta["tool_calls"]:
                                            index = tool_call_delta.get("index")
                                            if index is not None:
                                                # Initialize or update accumulated tool call
                                                if index not in accumulated_tool_calls:
                                                    accumulated_tool_calls[index] = {
                                                        "id": tool_call_delta.get("id", ""),
                                                        "type": tool_call_delta.get("type", "function"),
                                                        "function": {"name": "", "arguments": ""}
                                                    }
                                                
                                                # Update function name if present
                                                if "function" in tool_call_delta:
                                                    func_delta = tool_call_delta["function"]
                                                    if "name" in func_delta:
                                                        accumulated_tool_calls[index]["function"]["name"] = func_delta["name"]
                                                    if "arguments" in func_delta:
                                                        # Arguments are streamed incrementally
                                                        accumulated_tool_calls[index]["function"]["arguments"] += func_delta["arguments"]
                                                
                                                # Update ID and type if present
                                                if "id" in tool_call_delta:
                                                    accumulated_tool_calls[index]["id"] = tool_call_delta["id"]
                                                if "type" in tool_call_delta:
                                                    accumulated_tool_calls[index]["type"] = tool_call_delta["type"]
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse streaming chunk: {data_str}")
                                continue
                    
                    # After stream ends, yield accumulated function calls if any
                    if accumulated_tool_calls:
                        final_tool_calls = [tc for idx, tc in sorted(accumulated_tool_calls.items())]
                        yield f"\n[FUNCTION_CALLS:{json.dumps(final_tool_calls)}]"
            else:
                # Non-streaming response
                response = self._http_client.post(url, json=payload, timeout=120.0)
                response.raise_for_status()
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    message = result["choices"][0].get("message", {})
                    content = message.get("content", "")
                    if content:
                        yield content
                    # Check for function calls in non-streaming response
                    if "tool_calls" in message:
                        # Function calls present - yield special marker
                        yield f"\n[FUNCTION_CALLS:{json.dumps(message['tool_calls'])}]"
        except httpx.HTTPError as e:
            logger.error(f"HTTP request to LLM service failed: {e}")
            if span:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise

    def generate_from_messages(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[str]:
        """
        Generate text from OpenAI-format messages.

        Args:
            messages: List of OpenAI-format messages (role, content, etc.)
            temperature: Sampling temperature (overrides default)
            max_tokens: Maximum tokens to generate (overrides default)
            stream: Whether to stream the response
            tools: Optional list of OpenAI-format tool definitions for function calling

        Yields:
            Response chunks as they arrive (if stream=True)
        """
        with tracer.start_as_current_span("llm_client.generate_from_messages") as span:
            try:
                span.set_attribute("messages_count", len(messages))
                span.set_attribute("stream", stream)
                span.set_attribute("protocol", self._protocol)

                self._ensure_connection()

                if self._protocol == "http":
                    # HTTP/OpenAI-compatible API (NVIDIA NIM)
                    yield from self._generate_http(
                        prompt="",  # Not used when messages is provided
                        system_prompt=None,  # Not used when messages is provided
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=stream,
                        span=span,
                        tools=tools,
                        messages=messages,
                    )
                else:
                    # gRPC: Convert messages to ChatMessage protobuf
                    chat_messages: List[ChatMessage] = []
                    for msg in messages:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        chat_msg = self._create_chat_message(role, content)
                        
                        # Handle tool calls if present
                        if "tool_calls" in msg:
                            for tool_call_dict in msg["tool_calls"]:
                                tool_call = ToolCall(
                                    id=tool_call_dict.get("id", ""),
                                    type=tool_call_dict.get("type", "function"),
                                    function=FunctionCall(
                                        name=tool_call_dict.get("function", {}).get("name", ""),
                                        arguments=tool_call_dict.get("function", {}).get("arguments", "{}")
                                    )
                                )
                                chat_msg.tool_calls.append(tool_call)
                        
                        chat_messages.append(chat_msg)
                    
                    # Create request
                    request = ChatRequest(
                        messages=chat_messages,
                        params=GenerationParameters(
                            temperature=temperature or self.temperature,
                            max_tokens=max_tokens or self.max_tokens,
                        ),
                        stream=stream,
                    )

                    # Generate response
                    if stream:
                        for chunk in self._stub.ChatStream(request):
                            if chunk.chunk.role == "assistant":
                                content = chunk.chunk.content
                                if content:
                                    yield content
                    else:
                        # Non-streaming: collect all chunks
                        response = ""
                        for chunk in self._stub.ChatStream(request):
                            if chunk.chunk.role == "assistant":
                                content = chunk.chunk.content
                                if content:
                                    response += content
                        yield response

            except Exception as e:
                logger.error(f"Error generating text from messages: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate text from a prompt (non-streaming).

        Args:
            prompt: The input prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (overrides default)
            max_tokens: Maximum tokens to generate (overrides default)

        Returns:
            Generated text as a string
        """
        response_chunks = list(
            self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
        )
        return "".join(response_chunks) if response_chunks else ""

    def think(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Think phase: Analyze the user's request.

        Args:
            user_message: The user's message/request
            conversation_history: Optional conversation history

        Returns:
            Analysis/thinking result as text
        """
        with tracer.start_as_current_span("llm_client.think") as span:
            try:
                span.set_attribute("user_message_length", len(user_message))

                system_prompt = """You are an AI assistant that analyzes user requests.
Your task is to think deeply about what the user is asking for, identify the key requirements,
and understand the complexity and context of the request.

Provide a clear, concise analysis of the request."""

                prompt = f"""Analyze this user request:

{user_message}

Provide your analysis of what the user is asking for, including:
1. What is the main goal or objective?
2. What are the key requirements?
3. What is the complexity level (simple/moderate/complex)?
4. What context or information might be needed?"""

                if conversation_history:
                    history_text = "\n".join(
                        [
                            f"{msg['role']}: {msg['content']}"
                            for msg in conversation_history[-5:]  # Last 5 messages
                        ]
                    )
                    prompt = f"""Previous conversation:
{history_text}

{prompt}"""

                result = self.generate_text(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.3,  # Lower temperature for more focused thinking
                    max_tokens=512,
                )

                span.set_attribute("result_length", len(result))
                return result

            except Exception as e:
                logger.error(f"Error in think phase: {e}", exc_info=True)
                span.record_exception(e)
                raise

    def plan(
        self,
        user_request: str,
        analysis: str,
        available_tools: List[str],
    ) -> str:
        """
        Plan phase: Create an execution plan.

        Args:
            user_request: The original user request
            analysis: The analysis from the think phase
            available_tools: List of available tool names

        Returns:
            Plan as structured text
        """
        with tracer.start_as_current_span("llm_client.plan") as span:
            try:
                span.set_attribute("user_request_length", len(user_request))
                span.set_attribute("analysis_length", len(analysis))
                span.set_attribute("available_tools_count", len(available_tools))

                system_prompt = """You are an AI assistant that creates execution plans.
Your task is to break down user requests into clear, executable steps.

Create a step-by-step plan that:
1. Identifies the required tools
2. Determines the execution order
3. Sets success criteria
4. Estimates complexity"""

                tools_text = (
                    "\n".join([f"- {tool}" for tool in available_tools])
                    if available_tools
                    else "No specific tools available"
                )

                prompt = f"""Based on this analysis:
{analysis}

Create an execution plan for this request:
{user_request}

Available tools:
{tools_text}

Provide a structured plan with:
1. List of steps (numbered)
2. Tool to use for each step (if applicable)
3. Expected outcome for each step
4. Success criteria"""

                result = self.generate_text(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.5,  # Moderate temperature for balanced planning
                    max_tokens=1024,
                )

                span.set_attribute("result_length", len(result))
                return result

            except Exception as e:
                logger.error(f"Error in plan phase: {e}", exc_info=True)
                span.record_exception(e)
                raise

    def reflect(
        self,
        original_request: str,
        plan: str,
        execution_results: List[Dict[str, Any]],
    ) -> str:
        """
        Reflect phase: Evaluate execution results.

        Args:
            original_request: The original user request
            plan: The plan that was executed
            execution_results: Results from executing the plan

        Returns:
            Reflection/evaluation as text
        """
        with tracer.start_as_current_span("llm_client.reflect") as span:
            try:
                span.set_attribute("original_request_length", len(original_request))
                span.set_attribute("plan_length", len(plan))
                span.set_attribute("execution_results_count", len(execution_results))

                system_prompt = """You are an AI assistant that evaluates execution results.
Your task is to reflect on whether goals were achieved and identify any issues.

Evaluate:
1. Was the goal achieved?
2. Were there any errors or issues?
3. Should the plan be adjusted?
4. Is the response complete?"""

                results_text = "\n".join(
                    [
                        f"Step {i+1}: {'✓ Success' if r.get('success') else '✗ Failed'}\n"
                        f"  Output: {r.get('output', 'N/A')}\n"
                        f"  Error: {r.get('error', 'None')}"
                        for i, r in enumerate(execution_results)
                    ]
                )

                prompt = f"""Original request:
{original_request}

Plan that was executed:
{plan}

Execution results:
{results_text}

Evaluate:
1. Was the goal achieved? Why or why not?
2. What issues were encountered (if any)?
3. Should the plan be adjusted or retried?
4. What is the final response to the user?"""

                result = self.generate_text(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.4,  # Lower temperature for more consistent evaluation
                    max_tokens=1024,
                )

                span.set_attribute("result_length", len(result))
                return result

            except Exception as e:
                logger.error(f"Error in reflect phase: {e}", exc_info=True)
                span.record_exception(e)
                raise

    def cleanup(self) -> None:
        """Clean up connections (close HTTP client and gRPC channel)."""
        if self._http_client is not None:
            try:
                self._http_client.close()
                self._http_client = None
                logger.debug("Closed HTTP client connection")
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")
        
        if self._channel is not None:
            try:
                self._channel.close()
                self._channel = None
                self._stub = None
                logger.debug("Closed gRPC channel connection")
            except Exception as e:
                logger.warning(f"Error closing gRPC channel: {e}")
