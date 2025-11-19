"""
LLM Client for Agentic Reasoning

Provides a unified interface for LLM interactions used by reasoning components.
Wraps the gRPC LLM inference service (TensorRT-LLM) for use in reasoning phases.
"""
import logging
from typing import Optional, List, Dict, Any, Iterator
import grpc

from june_grpc_api.llm_pb2 import (
    ChatRequest,
    ChatMessage,
    GenerationParameters,
    ChatChunk,
    Context,
)
from june_grpc_api import llm_pb2_grpc
from essence.chat.utils.tracing import get_tracer
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class LLMClient:
    """
    LLM client for agentic reasoning components.
    
    Provides methods for thinking, planning, and reflection phases.
    """
    
    def __init__(
        self,
        inference_api_url: str = "tensorrt-llm:8000",
        model_name: str = "Qwen/Qwen3-30B-A3B-Thinking-2507",
        max_context_length: int = 131072,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """
        Initialize the LLM client.
        
        Args:
            inference_api_url: gRPC endpoint for LLM inference service
            model_name: Name of the model to use
            max_context_length: Maximum context length for the model
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.inference_api_url = inference_api_url
        self.model_name = model_name
        self.max_context_length = max_context_length
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[llm_pb2_grpc.LLMInferenceStub] = None
    
    def _ensure_connection(self) -> None:
        """Ensure gRPC connection to LLM inference service is established."""
        if self._channel is None or self._stub is None:
            self._channel = grpc.insecure_channel(self.inference_api_url)
            self._stub = llm_pb2_grpc.LLMInferenceStub(self._channel)
            logger.info(f"Connected to LLM inference service at {self.inference_api_url}")
    
    def _create_chat_message(self, role: str, content: str) -> ChatMessage:
        """Create a ChatMessage protobuf object."""
        return ChatMessage(
            role=role,
            content=content
        )
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
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
                
                self._ensure_connection()
                
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
        response_chunks = list(self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        ))
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
                    history_text = "\n".join([
                        f"{msg['role']}: {msg['content']}"
                        for msg in conversation_history[-5:]  # Last 5 messages
                    ])
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
                
                tools_text = "\n".join([f"- {tool}" for tool in available_tools]) if available_tools else "No specific tools available"
                
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
                
                results_text = "\n".join([
                    f"Step {i+1}: {'✓ Success' if r.get('success') else '✗ Failed'}\n"
                    f"  Output: {r.get('output', 'N/A')}\n"
                    f"  Error: {r.get('error', 'None')}"
                    for i, r in enumerate(execution_results)
                ])
                
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
