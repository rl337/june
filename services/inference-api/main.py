"""
Inference API Service - LLM orchestration with RAG and tool invocation.
"""
import asyncio
import logging
import os
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
try:
    # Add essence package to path for tracing import
    essence_path = Path(__file__).parent.parent.parent / "essence"
    if str(essence_path) not in sys.path:
        sys.path.insert(0, str(essence_path))
    from essence.chat.utils.tracing import setup_tracing
    setup_tracing(service_name="june-inference-api")
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
        self.health_checker.add_check("database", self._check_database_health)
        # MinIO health check removed - not needed for MVP
        self.health_checker.add_check("nats", self._check_nats_health)
    
    async def GenerateStream(self, request: GenerationRequest, context: grpc.aio.ServicerContext) -> AsyncGenerator[GenerationChunk, None]:
        """Streaming text generation."""
        with Timer("generation_stream"):
            try:
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
                async for chunk in self._generate_tokens_stream(
                    request.prompt, 
                    request.params, 
                    context_data
                ):
                    yield chunk
                    
            except Exception as e:
                logger.error(f"Generation stream error: {e}")
                error_chunk = GenerationChunk(
                    token="",
                    is_final=True,
                    finish_reason=FinishReason.ERROR
                )
                yield error_chunk
    
    async def Generate(self, request: GenerationRequest, context: grpc.aio.ServicerContext) -> GenerationResponse:
        """One-shot text generation."""
        with Timer("generation"):
            try:
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
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Invalid prompt: {str(e)}")
                        return GenerationResponse()
                
                # Prepare context
                context_data = await self._prepare_context(request.context)
                
                # Generate text
                response_text, usage_stats = await self._generate_text(
                    request.prompt,
                    request.params,
                    context_data
                )
                
                return GenerationResponse(
                    text=response_text,
                    tokens_generated=usage_stats.completion_tokens,
                    tokens_per_second=usage_stats.completion_tokens / max(usage_stats.total_tokens, 1),
                    finish_reason=FinishReason.STOP,
                    usage=usage_stats
                )
                
            except Exception as e:
                logger.error(f"Generation error: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return GenerationResponse()
    
    async def ChatStream(self, request: ChatRequest, context: grpc.aio.ServicerContext) -> AsyncGenerator[ChatChunk, None]:
        """Streaming chat with conversation history."""
        with Timer("chat_stream"):
            try:
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
                
                # Generate response
                async for chunk in self._generate_tokens_stream(
                    formatted_prompt,
                    request.params,
                    context_data
                ):
                    chat_chunk = ChatChunk(
                        content_delta=chunk.token,
                        role="assistant",
                        is_final=chunk.is_final,
                        finish_reason=chunk.finish_reason
                    )
                    yield chat_chunk
                    
            except Exception as e:
                logger.error(f"Chat stream error: {e}")
                error_chunk = ChatChunk(
                    content_delta="",
                    role="assistant",
                    is_final=True,
                    finish_reason=FinishReason.ERROR
                )
                yield error_chunk
    
    async def Chat(self, request: ChatRequest, context: grpc.aio.ServicerContext) -> ChatResponse:
        """One-shot chat with conversation history."""
        with Timer("chat"):
            try:
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
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details(f"Invalid message content: {str(e)}")
                        return ChatResponse()
                
                # Prepare context
                context_data = await self._prepare_context(request.context)
                
                # Format conversation
                formatted_prompt = await self._format_conversation(request.messages, context_data)
                
                # Generate response
                response_text, usage_stats = await self._generate_text(
                    formatted_prompt,
                    request.params,
                    context_data
                )
                
                # Create assistant message
                assistant_message = ChatMessage(
                    role="assistant",
                    content=response_text
                )
                
                return ChatResponse(
                    message=assistant_message,
                    tokens_generated=usage_stats.completion_tokens,
                    tokens_per_second=usage_stats.completion_tokens / max(usage_stats.total_tokens, 1),
                    usage=usage_stats
                )
                
            except Exception as e:
                logger.error(f"Chat error: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return ChatResponse()
    
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
    
    async def _generate_text(self, prompt: str, params: GenerationParameters, context_data: Dict[str, Any]) -> tuple[str, UsageStats]:
        """Generate text without streaming."""
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
            
            usage_stats = UsageStats(
                prompt_tokens=input_tokens,
                completion_tokens=completion_tokens,
                total_tokens=input_tokens + completion_tokens,
                prompt_cache_hits=0
            )
            
            TOKEN_COUNT.labels(model=config.model.name).inc(completion_tokens)
            
            return response_text, usage_stats
            
        except Exception as e:
            logger.error(f"Text generation error: {e}")
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
            )
            
            # Warmup the strategy (loads model and tokenizer)
            self.llm_strategy.warmup()
            
            logger.info("LLM model loaded successfully via Qwen3LlmStrategy")
            
            # Load embedding model (smaller model for efficiency)
            # Note: Embedding model is still loaded directly as it's separate from LLM strategy
            embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
            logger.info(f"Loading embedding model: {embedding_model_name}")
            self.embedding_model = AutoModelForCausalLM.from_pretrained(embedding_model_name)
            self.embedding_tokenizer = AutoTokenizer.from_pretrained(embedding_model_name)
            
            logger.info("All models loaded successfully")
    
    async def _connect_services(self):
        """Connect to external services."""
        try:
            # Connect to database with connection pooling
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
        return self.llm_strategy is not None and self.llm_strategy._model is not None and self.llm_strategy._tokenizer is not None
    
    async def _check_database_health(self) -> bool:
        """Check database connection health."""
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
    
    async def disconnect_services(self):
        """Disconnect from external services."""
        if self.nats_client:
            await self.nats_client.close()
        if self.db_engine:
            await self.db_engine.dispose()

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
    # Allow service-to-service auth from gateway, stt, tts services
    auth_interceptor = create_auth_interceptor(
        require_auth=True,
        allowed_services=["gateway", "stt", "tts", "telegram", "webapp"]
    )
    
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







