"""
Inference API Service - LLM orchestration with RAG and tool invocation.
"""
import asyncio
import logging
import os
import re
import sys
import json
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
import numpy as np
from pathlib import Path

import grpc
from grpc import aio
import nats
import torch
from transformers import (
    AutoTokenizer, AutoModelForCausalLM
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import asyncpg
# MinIO removed - not needed for MVP
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
from prometheus_client.exposition import start_http_server

# Import gRPC authentication and protobuf classes
# grpc_auth.py is copied to /app/grpc_auth.py in the Dockerfile
try:
    from grpc_auth import create_auth_interceptor, get_user_from_metadata, is_service_request
except ImportError:
    # Fallback: disable auth if grpc_auth not available
    def create_auth_interceptor(*args, **kwargs):
        return None
    def get_user_from_metadata(*args, **kwargs):
        return None
    def is_service_request(*args, **kwargs):
        return True

from june_grpc_api.llm_pb2 import (
    GenerationRequest, GenerationResponse, GenerationChunk,
    ChatRequest, ChatResponse, ChatChunk, ChatMessage,
    EmbeddingRequest, EmbeddingResponse,
    HealthRequest, HealthResponse,
    GenerationParameters, Context, ToolDefinition,
    FinishReason, UsageStats
)
from june_grpc_api import llm_pb2_grpc

from inference_core import config, setup_logging, Timer, HealthChecker, CircularBuffer
from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
from inference_core.strategies import InferenceRequest, InferenceResponse

# Initialize tracing early
tracer = None
try:
    # Add essence package to path for tracing import
    essence_path = Path(__file__).parent.parent.parent / "essence"
    if str(essence_path) not in sys.path:
        sys.path.insert(0, str(essence_path))
    from essence.chat.utils.tracing import setup_tracing, get_tracer
    from opentelemetry import trace
    setup_tracing(service_name="june-inference-api")
    tracer = get_tracer(__name__)
except ImportError:
    pass

# Setup logging first
setup_logging(config.monitoring.log_level, "inference-api")
logger = logging.getLogger(__name__)

# Import rate limiting (after logger is initialized)
try:
    from june_rate_limit import RateLimitInterceptor, RateLimitConfig
    RATE_LIMIT_AVAILABLE = True
except ImportError:
    logger.warning("june-rate-limit package not available, rate limiting disabled for gRPC")
    RATE_LIMIT_AVAILABLE = False
    RateLimitInterceptor = None
    RateLimitConfig = None

# Import input validation
try:
    from june_security import get_input_validator, InputValidationError
    input_validator = get_input_validator()
    VALIDATION_AVAILABLE = True
except ImportError:
    logger.warning("june-security input validation not available")
    input_validator = None
    VALIDATION_AVAILABLE = False

# Prometheus metrics
REGISTRY = CollectorRegistry()
REQUEST_COUNT = Counter('inference_requests_total', 'Total requests', ['method', 'status'], registry=REGISTRY)
REQUEST_DURATION = Histogram('inference_request_duration_seconds', 'Request duration', registry=REGISTRY)
TOKEN_COUNT = Counter('inference_tokens_total', 'Total tokens generated', ['model'], registry=REGISTRY)
TOKEN_GENERATION_RATE = Histogram('inference_token_generation_rate', 'Token generation rate (tokens/second)', registry=REGISTRY)
MODEL_LOAD_TIME = Histogram('inference_model_load_seconds', 'Model loading time', registry=REGISTRY)
RAG_RETRIEVAL_TIME = Histogram('inference_rag_retrieval_seconds', 'RAG retrieval time', registry=REGISTRY)
CONTEXT_USAGE = Gauge('inference_context_usage_tokens', 'Context usage in tokens', registry=REGISTRY)
ACTIVE_CONNECTIONS = Gauge('inference_active_connections', 'Active gRPC connections', registry=REGISTRY)
ERROR_COUNT = Counter('inference_errors_total', 'Total errors', ['error_type'], registry=REGISTRY)

class InferenceAPIService(llm_pb2_grpc.LLMInferenceServicer):
    """Main inference API service class."""
    
    def __init__(self):
        self.llm_strategy = None  # Qwen3LlmStrategy instance
        self.embedding_model = None
        self.embedding_tokenizer = None
        self.db_engine = None
        # MinIO removed - not needed for MVP
        self.nats_client = None
        self.health_checker = HealthChecker()
        self.conversation_buffer = CircularBuffer(1000)
        self.device = config.model.device
        
        # Add health checks
        self.health_checker.add_check("model", self._check_model_health)
        self.health_checker.add_check("gpu", self._check_gpu_health)
        self.health_checker.add_check("database", self._check_database_health)
        # MinIO health check removed - not needed for MVP
        self.health_checker.add_check("nats", self._check_nats_health)
    
    async def GenerateStream(self, request: GenerationRequest, context: grpc.aio.ServicerContext) -> AsyncGenerator[GenerationChunk, None]:
        """Streaming text generation."""
        span = None
        if tracer is not None:
            span = tracer.start_span("llm.generate_stream")
            span.set_attribute("llm.method", "stream")
            span.set_attribute("llm.prompt_length", len(request.prompt))
            if request.params:
                span.set_attribute("llm.max_tokens", request.params.max_tokens)
                span.set_attribute("llm.temperature", request.params.temperature)
        
        try:
            with Timer("generation_stream"):
                # Validate input
                if VALIDATION_AVAILABLE and input_validator:
                    try:
                        validated_prompt = input_validator.validate_string(
                            request.prompt,
                            field_name="prompt",
                            max_length=100000,
                            sanitize=True
                        )
                        request.prompt = validated_prompt
                    except InputValidationError as e:
                        if span:
                            span.set_status(trace.Status(trace.StatusCode.ERROR, f"Invalid prompt: {str(e)}"))
                            span.record_exception(e)
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Invalid prompt: {str(e)}")
                        error_chunk = GenerationChunk(
                            token="",
                            is_final=True,
                            finish_reason=FinishReason.ERROR
                        )
                        yield error_chunk
                        return
                
                # Prepare context
                context_data = await self._prepare_context(request.context)
                
                # Generate tokens
                chunk_count = 0
                async for chunk in self._generate_tokens_stream(
                    request.prompt, 
                    request.params, 
                    context_data
                ):
                    chunk_count += 1
                    yield chunk
                
                # Update span with results
                if span:
                    span.set_attribute("llm.chunk_count", chunk_count)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    
        except Exception as e:
            logger.error(f"Generation stream error: {e}")
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            error_chunk = GenerationChunk(
                token="",
                is_final=True,
                finish_reason=FinishReason.ERROR
            )
            yield error_chunk
        finally:
            if span:
                span.end()
    
    async def Generate(self, request: GenerationRequest, context: grpc.aio.ServicerContext) -> GenerationResponse:
        """One-shot text generation."""
        span = None
        if tracer is not None:
            span = tracer.start_span("llm.generate")
            span.set_attribute("llm.method", "oneshot")
            span.set_attribute("llm.prompt_length", len(request.prompt))
            if request.params:
                span.set_attribute("llm.max_tokens", request.params.max_tokens)
                span.set_attribute("llm.temperature", request.params.temperature)
        
        try:
            with Timer("generation"):
                # Validate input
                if VALIDATION_AVAILABLE and input_validator:
                    try:
                        validated_prompt = input_validator.validate_string(
                            request.prompt,
                            field_name="prompt",
                            max_length=100000,
                            sanitize=True
                        )
                        request.prompt = validated_prompt
                    except InputValidationError as e:
                        if span:
                            span.set_status(trace.Status(trace.StatusCode.ERROR, f"Invalid prompt: {str(e)}"))
                            span.record_exception(e)
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Invalid prompt: {str(e)}")
                        return GenerationResponse()
                
                # Prepare context
                context_data = await self._prepare_context(request.context)
                
                # Generate text
                response_text, usage_stats, tokens_per_second = await self._generate_text(
                    request.prompt,
                    request.params,
                    context_data
                )
                
                # Update span with results
                if span:
                    span.set_attribute("llm.response_length", len(response_text))
                    span.set_attribute("llm.completion_tokens", usage_stats.completion_tokens)
                    span.set_attribute("llm.total_tokens", usage_stats.total_tokens)
                    span.set_attribute("llm.tokens_per_second", tokens_per_second)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                
                return GenerationResponse(
                    text=response_text,
                    tokens_generated=usage_stats.completion_tokens,
                    tokens_per_second=tokens_per_second,
                    finish_reason=FinishReason.STOP,
                    usage=usage_stats
                )
        except RuntimeError as e:
            error_msg = str(e).lower()
            error_type = "unknown"
            if "out of memory" in error_msg or "oom" in error_msg:
                error_type = "out_of_memory"
            elif "timeout" in error_msg or "timed out" in error_msg:
                error_type = "timeout"
            
            # Update span for error
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
                span.record_exception(e)
            
            # Attempt recovery
            await self.recover_from_error(error_type)
            
            logger.error(f"Generation error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return GenerationResponse()
        except Exception as e:
            # Update span for error
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            
            # Attempt recovery for unknown errors
            await self.recover_from_error("unknown")
            
            logger.error(f"Generation error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return GenerationResponse()
        finally:
            if span:
                span.end()
    
    async def ChatStream(self, request: ChatRequest, context: grpc.aio.ServicerContext) -> AsyncGenerator[ChatChunk, None]:
        """Streaming chat with conversation history."""
        span = None
        if tracer is not None:
            span = tracer.start_span("llm.chat_stream")
            span.set_attribute("llm.method", "chat_stream")
            span.set_attribute("llm.message_count", len(request.messages))
            if request.params:
                span.set_attribute("llm.max_tokens", request.params.max_tokens)
                span.set_attribute("llm.temperature", request.params.temperature)
        
        try:
            with Timer("chat_stream"):
                # Validate input messages
                if VALIDATION_AVAILABLE and input_validator:
                    try:
                        for message in request.messages:
                            if message.content:
                                validated_content = input_validator.validate_string(
                                    message.content,
                                    field_name="message.content",
                                    max_length=100000,
                                    sanitize=True
                                )
                                message.content = validated_content
                    except InputValidationError as e:
                        if span:
                            span.set_status(trace.Status(trace.StatusCode.ERROR, f"Invalid message content: {str(e)}"))
                            span.record_exception(e)
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Invalid message content: {str(e)}")
                        error_chunk = ChatChunk(
                            content_delta="",
                            role="assistant",
                            is_final=True,
                            finish_reason=FinishReason.ERROR
                        )
                        yield error_chunk
                        return
                
                # Prepare context
                context_data = await self._prepare_context(request.context)
                
                # Format conversation
                formatted_prompt = await self._format_conversation(request.messages, context_data)
                
                if span:
                    span.set_attribute("llm.formatted_prompt_length", len(formatted_prompt))
                
                # Generate response
                chunk_count = 0
                async for chunk in self._generate_tokens_stream(
                    formatted_prompt,
                    request.params,
                    context_data
                ):
                    chunk_count += 1
                    chat_chunk = ChatChunk(
                        content_delta=chunk.token,
                        role="assistant",
                        is_final=chunk.is_final,
                        finish_reason=chunk.finish_reason
                    )
                    yield chat_chunk
                
                # Update span with results
                if span:
                    span.set_attribute("llm.chunk_count", chunk_count)
                    span.set_status(trace.Status(trace.StatusCode.OK))
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                error_chunk = ChatChunk(
                    content_delta="",
                    role="assistant",
                    is_final=True,
                    finish_reason=FinishReason.ERROR
                )
                yield error_chunk
        finally:
            if span:
                span.end()
    
    async def Chat(self, request: ChatRequest, context: grpc.aio.ServicerContext) -> ChatResponse:
        """One-shot chat with conversation history."""
        span = None
        if tracer is not None:
            span = tracer.start_span("llm.chat")
            span.set_attribute("llm.method", "chat")
            span.set_attribute("llm.message_count", len(request.messages))
            if request.params:
                span.set_attribute("llm.max_tokens", request.params.max_tokens)
                span.set_attribute("llm.temperature", request.params.temperature)
        
        try:
            with Timer("chat"):
                # Validate input messages
                if VALIDATION_AVAILABLE and input_validator:
                    try:
                        for message in request.messages:
                            if message.content:
                                validated_content = input_validator.validate_string(
                                    message.content,
                                    field_name="message.content",
                                    max_length=100000,
                                    sanitize=True
                                )
                                message.content = validated_content
                    except InputValidationError as e:
                        if span:
                            span.set_status(trace.Status(trace.StatusCode.ERROR, f"Invalid message content: {str(e)}"))
                            span.record_exception(e)
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Invalid message content: {str(e)}")
                        return ChatResponse()
                
                # Prepare context
                context_data = await self._prepare_context(request.context)
                
                # Format conversation
                formatted_prompt = await self._format_conversation(request.messages, context_data)
                
                if span:
                    span.set_attribute("llm.formatted_prompt_length", len(formatted_prompt))
                
                # Generate response
                response_text, usage_stats, tokens_per_second = await self._generate_text(
                    formatted_prompt,
                    request.params,
                    context_data
                )
                
                # Update span with results
                if span:
                    span.set_attribute("llm.response_length", len(response_text))
                    span.set_attribute("llm.completion_tokens", usage_stats.completion_tokens)
                    span.set_attribute("llm.total_tokens", usage_stats.total_tokens)
                    span.set_attribute("llm.tokens_per_second", tokens_per_second)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                
                # Create assistant message
                assistant_message = ChatMessage(
                    role="assistant",
                    content=response_text
                )
                
                return ChatResponse(
                    message=assistant_message,
                    tokens_generated=usage_stats.completion_tokens,
                    tokens_per_second=tokens_per_second,
                    usage=usage_stats
                )
        except Exception as e:
            logger.error(f"Chat error: {e}")
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ChatResponse()
        finally:
            if span:
                span.end()
    
    async def Embed(self, request: EmbeddingRequest, context: grpc.aio.ServicerContext) -> EmbeddingResponse:
        """Generate embeddings for text."""
        with Timer("embedding"):
            try:
                # Validate input texts
                if VALIDATION_AVAILABLE and input_validator:
                    try:
                        validated_texts = []
                        for text in request.texts:
                            validated_text = input_validator.validate_string(
                                text,
                                field_name="text",
                                max_length=100000,
                                sanitize=True
                            )
                            validated_texts.append(validated_text)
                        request.texts[:] = validated_texts
                    except InputValidationError as e:
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Invalid text input: {str(e)}")
                        return EmbeddingResponse()
                
                embeddings = await self._generate_embeddings(request.texts)
                
                return EmbeddingResponse(
                    embeddings=embeddings.flatten().tolist(),
                    dimension=embeddings.shape[1]
                )
                
            except Exception as e:
                logger.error(f"Embedding error: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return EmbeddingResponse()
    
    async def HealthCheck(self, request: HealthRequest, context: grpc.aio.ServicerContext) -> HealthResponse:
        """Health check endpoint."""
        health_status = await self.health_checker.check_all()
        is_healthy = all(health_status.values())
        
        return HealthResponse(
            healthy=is_healthy,
            version="0.2.0",
            model_name=config.model.name,
            max_context_length=config.model.max_context_length,
            supports_streaming=True,
            available_tools=["search", "calculator", "weather"]  # TODO: Dynamic tool list
        )
    
    async def _prepare_context(self, context: Context) -> Dict[str, Any]:
        """Prepare context for generation including RAG retrieval."""
        context_data = {
            "user_id": context.user_id,
            "session_id": context.session_id,
            "rag_documents": [],
            "tools": context.available_tools if context.enable_tools else []
        }
        
        # Retrieve RAG documents if specified
        if context.rag_document_ids:
            with Timer("rag_retrieval"):
                rag_docs = await self._retrieve_rag_documents(context.rag_document_ids)
                context_data["rag_documents"] = rag_docs
        
        return context_data
    
    async def _retrieve_rag_documents(self, document_ids: List[str]) -> List[Dict[str, Any]]:
        """Retrieve documents for RAG."""
        try:
            # Validate document IDs to prevent SQL injection
            if VALIDATION_AVAILABLE and input_validator:
                validated_ids = []
                for doc_id in document_ids:
                    try:
                        validated_id = input_validator.validate_string(
                            doc_id,
                            field_name="document_id",
                            max_length=255,
                            sanitize=True
                        )
                        validated_ids.append(validated_id)
                    except InputValidationError:
                        logger.warning(f"Invalid document ID skipped: {doc_id}")
                        continue
                document_ids = validated_ids
            
            async with self.db_engine.begin() as conn:
                # Use parameterized query to prevent SQL injection
                query = text("""
                    SELECT d.id, d.title, d.content, d.source_url, d.metadata
                    FROM documents d
                    WHERE d.id = ANY(:document_ids)
                """)
                result = await conn.execute(query, {"document_ids": document_ids})
                documents = result.fetchall()
                
                return [
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "content": doc.content,
                        "source_url": doc.source_url,
                        "metadata": doc.metadata
                    }
                    for doc in documents
                ]
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            return []
    
    async def _format_conversation(self, messages: List[ChatMessage], context_data: Dict[str, Any]) -> str:
        """Format conversation history into prompt."""
        formatted_parts = []
        
        # Add system message with RAG context
        if context_data["rag_documents"]:
            rag_context = "\n".join([
                f"Document: {doc['title']}\n{doc['content']}\n"
                for doc in context_data["rag_documents"]
            ])
            formatted_parts.append(f"Context:\n{rag_context}")
        
        # Add conversation history
        for message in messages:
            role = message.role
            content = message.content
            
            if role == "system":
                formatted_parts.append(f"System: {content}")
            elif role == "user":
                formatted_parts.append(f"Human: {content}")
            elif role == "assistant":
                formatted_parts.append(f"Assistant: {content}")
            elif role == "tool":
                formatted_parts.append(f"Tool: {content}")
        
        return "\n\n".join(formatted_parts) + "\n\nAssistant:"
    
    async def _generate_tokens_stream(self, prompt: str, params: GenerationParameters, context_data: Dict[str, Any]) -> AsyncGenerator[GenerationChunk, None]:
        """Generate tokens with streaming."""
        try:
            # Use strategy to generate text
            request = InferenceRequest(
                payload={
                    "prompt": prompt,
                    "params": {
                        "temperature": params.temperature,
                        "max_tokens": params.max_tokens,
                        "top_p": params.top_p,
                        "top_k": params.top_k if params.top_k > 0 else None,
                        "repetition_penalty": params.repetition_penalty,
                    }
                },
                metadata={}
            )
            
            response = self.llm_strategy.infer(request)
            
            # Extract generated text from response
            if isinstance(response.payload, dict):
                response_text = response.payload.get("text", "")
            else:
                response_text = str(response.payload)
            
            # Yield tokens (simplified - in real implementation, use proper streaming)
            tokens = response_text.split()
            for i, token in enumerate(tokens):
                chunk = GenerationChunk(
                    token=token + " ",
                    is_final=(i == len(tokens) - 1),
                    index=i,
                    finish_reason=FinishReason.STOP if i == len(tokens) - 1 else FinishReason.STOP
                )
                yield chunk
                
                # Small delay to simulate streaming
                await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f"Token generation error: {e}")
            error_chunk = GenerationChunk(
                token="",
                is_final=True,
                finish_reason=FinishReason.ERROR
            )
            yield error_chunk
    
    async def _generate_text(self, prompt: str, params: GenerationParameters, context_data: Dict[str, Any]) -> tuple[str, UsageStats, float]:
        """Generate text without streaming.
        
        Returns:
            tuple: (response_text, usage_stats, tokens_per_second)
        """
        try:
            # Use strategy to generate text
            request = InferenceRequest(
                payload={
                    "prompt": prompt,
                    "params": {
                        "temperature": params.temperature,
                        "max_tokens": params.max_tokens,
                        "top_p": params.top_p,
                        "top_k": params.top_k if params.top_k > 0 else None,
                        "repetition_penalty": params.repetition_penalty,
                    }
                },
                metadata={}
            )
            
            response = self.llm_strategy.infer(request)
            
            # Extract generated text and token counts from response
            if isinstance(response.payload, dict):
                response_text = response.payload.get("text", "")
                completion_tokens = response.payload.get("tokens", 0)
            else:
                response_text = str(response.payload)
                completion_tokens = 0
            
            # Get input token count from metadata if available
            input_tokens = response.metadata.get("input_tokens", 0)
            if input_tokens == 0:
                # Fallback: estimate input tokens (rough approximation)
                input_tokens = len(prompt.split())
            
            # Extract performance metrics from response metadata
            tokens_per_second = response.metadata.get("tokens_per_second", 0.0)
            total_duration = response.metadata.get("total_duration_seconds", 0.0)
            kv_cache_enabled = response.metadata.get("kv_cache_enabled", False)
            
            # Record Prometheus metrics
            TOKEN_COUNT.labels(model=config.model.name).inc(completion_tokens)
            if tokens_per_second > 0:
                TOKEN_GENERATION_RATE.observe(tokens_per_second)
            if total_duration > 0:
                REQUEST_DURATION.observe(total_duration)
            
            # Log performance metrics
            logger.info(
                "Inference API generation: %.2f tokens/s, %.2fs duration, KV cache: %s",
                tokens_per_second,
                total_duration,
                "enabled" if kv_cache_enabled else "disabled"
            )
            
            usage_stats = UsageStats(
                prompt_tokens=input_tokens,
                completion_tokens=completion_tokens,
                total_tokens=input_tokens + completion_tokens,
                prompt_cache_hits=0
            )
            
            return response_text, usage_stats, tokens_per_second
            
        except RuntimeError as e:
            error_msg = str(e).lower()
            # Handle specific error types
            if "out of memory" in error_msg or "oom" in error_msg:
                ERROR_COUNT.labels(error_type="out_of_memory").inc()
                logger.error(f"Out of memory error: {e}")
                # Try to recover by clearing CUDA cache
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        logger.info("Cleared CUDA cache after OOM error")
                except Exception:
                    pass
                # Re-raise with user-friendly message
                raise RuntimeError(f"Out of memory error. Try reducing max_tokens or input length.") from e
            elif "timeout" in error_msg or "timed out" in error_msg:
                ERROR_COUNT.labels(error_type="timeout").inc()
                logger.error(f"Inference timeout: {e}")
                raise RuntimeError(f"Inference timed out. Try reducing max_tokens or increasing timeout.") from e
            else:
                ERROR_COUNT.labels(error_type="runtime_error").inc()
                logger.error(f"Runtime error during generation: {e}")
                raise
        except Exception as e:
            ERROR_COUNT.labels(error_type="unknown_error").inc()
            logger.error(f"Text generation error: {e}", exc_info=True)
            raise
    
    async def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for texts."""
        try:
            # Tokenize texts
            inputs = self.embedding_tokenizer(
                texts,
                padding=True,
                truncation=True,
                return_tensors="pt"
            ).to(self.device)
            
            # Generate embeddings
            with torch.no_grad():
                outputs = self.embedding_model(**inputs)
                embeddings = outputs.last_hidden_state.mean(dim=1)
            
            return embeddings.cpu().numpy()
            
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            raise
    
    async def _load_models(self):
        """Load the main LLM and embedding models."""
        with Timer("model_loading"):
            # Check if models are already loaded
            if (self.llm_strategy is not None and 
                hasattr(self.llm_strategy, '_model') and 
                self.llm_strategy._model is not None and
                hasattr(self.llm_strategy, '_tokenizer') and
                self.llm_strategy._tokenizer is not None):
                logger.info("LLM model already loaded. Skipping reload.")
            else:
                logger.info(f"Loading LLM model using Qwen3LlmStrategy: {config.model.name}")
                
                # Initialize and warmup Qwen3LlmStrategy
                self.llm_strategy = Qwen3LlmStrategy(
                    model_name=config.model.name,
                    device=config.model.device,
                    max_context_length=config.model.max_context_length,
                    use_yarn=config.model.use_yarn if hasattr(config.model, 'use_yarn') else None,
                    huggingface_token=config.model.huggingface_token if hasattr(config.model, 'huggingface_token') else None,
                    model_cache_dir=config.model.model_cache_dir if hasattr(config.model, 'model_cache_dir') else None,
                    local_files_only=config.model.local_files_only if hasattr(config.model, 'local_files_only') else None,
                    use_quantization=config.model.use_quantization if hasattr(config.model, 'use_quantization') else None,
                    quantization_bits=config.model.quantization_bits if hasattr(config.model, 'quantization_bits') else None,
                )
                
                # Warmup the strategy (loads model and tokenizer)
                self.llm_strategy.warmup()
                
                logger.info("LLM model loaded successfully via Qwen3LlmStrategy")
            
            # Check if embedding model is already loaded
            if self.embedding_model is not None and self.embedding_tokenizer is not None:
                logger.info("Embedding model already loaded. Skipping reload.")
            else:
                # Load embedding model (smaller model for efficiency)
                # Note: Embedding model is still loaded directly as it's separate from LLM strategy
                embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
                logger.info(f"Loading embedding model: {embedding_model_name}")
                self.embedding_model = AutoModelForCausalLM.from_pretrained(embedding_model_name)
                self.embedding_tokenizer = AutoTokenizer.from_pretrained(embedding_model_name)
                logger.info("Embedding model loaded successfully")
            
            logger.info("All models loaded successfully")
    
    async def _connect_services(self):
        """Connect to external services."""
        try:
            # Connect to database (optional - not required for MVP)
            # PostgreSQL was removed from MVP, but connection code remains for optional use
            db_url = getattr(config.database, 'url', '') if hasattr(config, 'database') else ''
            if db_url and db_url.strip() and db_url.strip() != '':
                try:
                    import os
                    pool_size = int(os.getenv("POSTGRES_POOL_SIZE", "20"))
                    max_overflow = int(os.getenv("POSTGRES_MAX_OVERFLOW", "10"))
                    pool_timeout = int(os.getenv("POSTGRES_POOL_TIMEOUT", "30"))
                    
                    self.db_engine = create_async_engine(
                        config.database.url,
                        pool_size=pool_size,
                        max_overflow=max_overflow,
                        pool_timeout=pool_timeout,
                        pool_pre_ping=True,  # Verify connections before using
                        pool_recycle=3600,  # Recycle connections after 1 hour
                        echo=False
                    )
                    logger.info(
                        f"Connected to database with connection pool "
                        f"(size={pool_size}, max_overflow={max_overflow})"
                    )
                except Exception as e:
                    logger.warning(f"Database connection failed (optional): {e}. Continuing without database.")
                    self.db_engine = None
            else:
                logger.debug("POSTGRES_URL not configured, skipping database connection (not required for MVP)")
                self.db_engine = None
            
            # MinIO connection removed - not needed for MVP
            
            # Connect to NATS (optional - not required for MVP)
            if config.nats.url:
                try:
                    self.nats_client = await nats.connect(config.nats.url)
                    logger.info("Connected to NATS")
                except Exception as e:
                    logger.warning(f"NATS connection failed (optional): {e}. Continuing without NATS.")
                    self.nats_client = None
            else:
                logger.debug("NATS_URL not configured, skipping NATS connection (not required for MVP)")
                self.nats_client = None
            
        except Exception as e:
            logger.error(f"Failed to connect to services: {e}")
            raise
    
    async def _check_model_health(self) -> bool:
        """Check if model is loaded and ready."""
        try:
            if self.llm_strategy is None:
                return False
            # Check if model and tokenizer are loaded
            if not hasattr(self.llm_strategy, '_model') or self.llm_strategy._model is None:
                return False
            if not hasattr(self.llm_strategy, '_tokenizer') or self.llm_strategy._tokenizer is None:
                return False
            # Optionally test model with a simple operation
            # For now, just check if objects exist
            return True
        except Exception as e:
            logger.warning(f"Model health check failed: {e}")
            return False
    
    async def _check_database_health(self) -> bool:
        """Check database connection health."""
        if self.db_engine is None:
            # Database not configured (optional for MVP)
            return True
        try:
            async with self.db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    # MinIO health check removed - not needed for MVP
    
    async def _check_nats_health(self) -> bool:
        """Check NATS connection health."""
        return self.nats_client is not None and self.nats_client.is_connected
    
    async def _check_gpu_health(self) -> bool:
        """Check GPU availability for large models (30B+).
        
        For large models, GPU is required. This check verifies GPU is available
        and compatible before accepting requests.
        """
        try:
            import torch
            
            # Only check GPU for large models (30B+)
            if self.llm_strategy is None:
                # Model not loaded yet, can't determine if it's large
                return True  # Don't fail health check if model isn't loaded yet
            
            # Check if this is a large model
            if not hasattr(self.llm_strategy, '_is_large_model'):
                # Fallback: check model name directly
                model_name = getattr(self.llm_strategy, 'model_name', '') or config.model.name
                is_large = self._is_large_model_from_name(model_name)
            else:
                is_large = self.llm_strategy._is_large_model()
            
            if not is_large:
                # Small models can run on CPU, GPU check not required
                return True
            
            # For large models, GPU is mandatory
            if not torch.cuda.is_available():
                logger.error("GPU required for large models (30B+), but CUDA is not available")
                return False
            
            # Check if device is set to CUDA
            device = getattr(self.llm_strategy, 'device', self.device) or config.model.device
            if not device.startswith("cuda"):
                logger.error(f"GPU required for large models (30B+), but device is set to '{device}'")
                return False
            
            # Verify GPU is actually usable
            try:
                device_capability = torch.cuda.get_device_capability(0)
                # PyTorch 2.5.1 supports up to sm_90a (compute capability 9.0)
                # If GPU has compute capability >= 12, it's not supported
                if device_capability[0] >= 12:
                    logger.error(
                        f"GPU compute capability {device_capability} is not supported by PyTorch 2.5.1. "
                        "PyTorch supports up to sm_90a. GPU required for large models."
                    )
                    return False
                
                # Test GPU with a simple operation
                test_tensor = torch.zeros(10, device=device)
                test_result = test_tensor.sum().item()
                del test_tensor
                torch.cuda.empty_cache()
                if test_result != 0:
                    logger.error("GPU tensor test failed. GPU required for large models.")
                    return False
                
                logger.debug("GPU health check passed")
                return True
            except RuntimeError as e:
                error_msg = str(e).lower()
                if "no kernel image" in error_msg or "cuda" in error_msg or "kernel" in error_msg:
                    logger.error(f"GPU not compatible: {e}. GPU required for large models.")
                    return False
                raise
        except Exception as e:
            logger.error(f"GPU health check failed: {e}")
            return False
    
    def _is_large_model_from_name(self, model_name: str) -> bool:
        """Check if model name indicates a large model (30B+ parameters)."""
        if not model_name:
            return False
        
        model_name_lower = model_name.lower()
        # Match patterns like "30B", "30-B", "30b", "70B", etc.
        large_model_pattern = r'(\d+)[-_\s]?b\b'
        match = re.search(large_model_pattern, model_name_lower)
        if match:
            param_count = int(match.group(1))
            return param_count >= 30
        
        # Also check for explicit indicators
        if "30b" in model_name_lower or "30-b" in model_name_lower:
            return True
        if "70b" in model_name_lower or "70-b" in model_name_lower:
            return True
        
        return False
    
    async def disconnect_services(self):
        """Disconnect from external services."""
        if self.nats_client:
            await self.nats_client.close()
        if self.db_engine:
            await self.db_engine.dispose()
    
    async def recover_from_error(self, error_type: str = "unknown"):
        """Attempt to recover from errors by clearing caches and resetting state.
        
        Args:
            error_type: Type of error ("out_of_memory", "timeout", "unknown")
        """
        logger.info(f"Attempting recovery from {error_type} error...")
        
        try:
            # Clear CUDA cache if available
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Cleared CUDA cache during recovery")
        except Exception as e:
            logger.warning(f"Failed to clear CUDA cache during recovery: {e}")
        
        # For OOM errors, we might want to reload the model with lower memory settings
        # For now, just clear caches and let the next request try again
        if error_type == "out_of_memory":
            logger.info("OOM recovery: Cleared caches. Next request should use lower max_tokens.")
        
        logger.info("Recovery completed")

# Global service instance
inference_service = InferenceAPIService()

async def serve():
    """Start the gRPC server and HTTP metrics server."""
    # Start HTTP server for Prometheus metrics
    metrics_port = int(os.getenv("INFERENCE_METRICS_PORT", "8001"))
    try:
        start_http_server(metrics_port, registry=REGISTRY)
        logger.info(f"Started Prometheus metrics server on port {metrics_port}")
    except Exception as e:
        logger.warning(f"Failed to start metrics server on port {metrics_port}: {e}")
    
    # Add authentication interceptor
    # Allow service-to-service auth from telegram, discord, stt, tts services
    # For MVP/testing, allow disabling auth via environment variable
    require_auth = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
    auth_interceptor = create_auth_interceptor(
        require_auth=require_auth,
        allowed_services=["telegram", "discord", "stt", "tts"]
    )
    if not require_auth:
        logger.info("Authentication disabled (REQUIRE_AUTH=false) - for testing only")
    
    interceptors = [auth_interceptor]
    
    # Add rate limiting interceptor if available
    if RATE_LIMIT_AVAILABLE:
        rate_limit_config = RateLimitConfig(
            default_per_minute=int(os.getenv("RATE_LIMIT_INFERENCE_PER_MINUTE", "60")),
            default_per_hour=int(os.getenv("RATE_LIMIT_INFERENCE_PER_HOUR", "1000")),
            use_redis=False,  # Use in-memory rate limiting for MVP (Redis not required)
            fallback_to_memory=True,
        )
        rate_limit_interceptor = RateLimitInterceptor(config=rate_limit_config)
        interceptors.append(rate_limit_interceptor)
        logger.info("Rate limiting enabled for Inference API (in-memory, Redis not required)")
    
    server = aio.server(interceptors=interceptors)
    
    # Add the service to the server
    llm_pb2_grpc.add_LLMInferenceServicer_to_server(inference_service, server)
    
    # Start server
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting Inference API server on {listen_addr} with authentication")
    
    # Load models and connect to services
    await inference_service._load_models()
    await inference_service._connect_services()
    
    # Start serving
    await server.start()
    logger.info("Inference API server started")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Inference API server...")
        await inference_service.disconnect_services()
        await server.stop(grace=5.0)

if __name__ == "__main__":
    asyncio.run(serve())







