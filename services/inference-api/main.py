"""
Inference API Service - LLM orchestration with RAG and tool invocation.
"""
import asyncio
import logging
import json
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
import numpy as np

import grpc
from grpc import aio
import nats
import torch
from transformers import (
    AutoTokenizer, AutoModelForCausalLM, 
    BitsAndBytesConfig, TextStreamer
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import asyncpg
from minio import Minio
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Import generated protobuf classes
import sys
sys.path.append('../../proto')
from llm_pb2 import (
    GenerationRequest, GenerationResponse, GenerationChunk,
    ChatRequest, ChatResponse, ChatChunk, ChatMessage,
    EmbeddingRequest, EmbeddingResponse,
    HealthRequest, HealthResponse,
    GenerationParameters, Context, ToolDefinition,
    FinishReason, UsageStats
)
import llm_pb2_grpc

from inference_core import config, setup_logging, Timer, HealthChecker, CircularBuffer

# Setup logging
setup_logging(config.monitoring.log_level, "inference-api")
logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('inference_requests_total', 'Total requests', ['method', 'status'])
REQUEST_DURATION = Histogram('inference_request_duration_seconds', 'Request duration')
TOKEN_COUNT = Counter('inference_tokens_total', 'Total tokens generated', ['model'])
MODEL_LOAD_TIME = Histogram('inference_model_load_seconds', 'Model loading time')
RAG_RETRIEVAL_TIME = Histogram('inference_rag_retrieval_seconds', 'RAG retrieval time')

class InferenceAPIService(llm_pb2_grpc.LLMInferenceServicer):
    """Main inference API service class."""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.embedding_model = None
        self.embedding_tokenizer = None
        self.db_engine = None
        self.minio_client = None
        self.nats_client = None
        self.health_checker = HealthChecker()
        self.conversation_buffer = CircularBuffer(1000)
        self.device = config.model.device
        
        # Add health checks
        self.health_checker.add_check("model", self._check_model_health)
        self.health_checker.add_check("database", self._check_database_health)
        self.health_checker.add_check("minio", self._check_minio_health)
        self.health_checker.add_check("nats", self._check_nats_health)
    
    async def GenerateStream(self, request: GenerationRequest, context: grpc.aio.ServicerContext) -> AsyncGenerator[GenerationChunk, None]:
        """Streaming text generation."""
        with Timer("generation_stream"):
            try:
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
            async with self.db_engine.begin() as conn:
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
            # Tokenize input
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            
            # Generate with streaming
            with torch.no_grad():
                generated = self.model.generate(
                    inputs.input_ids,
                    max_new_tokens=params.max_tokens,
                    temperature=params.temperature,
                    top_p=params.top_p,
                    top_k=int(params.top_k) if params.top_k > 0 else None,
                    repetition_penalty=params.repetition_penalty,
                    do_sample=params.temperature > 0,
                    pad_token_id=self.tokenizer.eos_token_id,
                    streamer=None,  # TODO: Implement proper streaming
                    return_dict_in_generate=True,
                    output_scores=False
                )
            
            # Decode tokens
            generated_text = self.tokenizer.decode(generated.sequences[0], skip_special_tokens=True)
            response_text = generated_text[len(prompt):]
            
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
            # Tokenize input
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            input_tokens = inputs.input_ids.shape[1]
            
            # Generate
            with torch.no_grad():
                generated = self.model.generate(
                    inputs.input_ids,
                    max_new_tokens=params.max_tokens,
                    temperature=params.temperature,
                    top_p=params.top_p,
                    top_k=int(params.top_k) if params.top_k > 0 else None,
                    repetition_penalty=params.repetition_penalty,
                    do_sample=params.temperature > 0,
                    pad_token_id=self.tokenizer.eos_token_id,
                    return_dict_in_generate=True
                )
            
            # Decode response
            generated_text = self.tokenizer.decode(generated.sequences[0], skip_special_tokens=True)
            response_text = generated_text[len(prompt):]
            
            # Calculate usage stats
            completion_tokens = generated.sequences.shape[1] - input_tokens
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
            logger.info(f"Loading model: {config.model.name}")
            
            # Load main model with quantization if needed
            if config.model.device.startswith("cuda"):
                # Use 4-bit quantization for memory efficiency
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True
                )
                
                self.model = AutoModelForCausalLM.from_pretrained(
                    config.model.name,
                    quantization_config=quantization_config,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    trust_remote_code=True
                )
            else:
                self.model = AutoModelForCausalLM.from_pretrained(
                    config.model.name,
                    torch_dtype=torch.float16,
                    trust_remote_code=True
                ).to(self.device)
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                config.model.name,
                trust_remote_code=True
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Load embedding model (smaller model for efficiency)
            embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
            self.embedding_model = AutoModelForCausalLM.from_pretrained(embedding_model_name)
            self.embedding_tokenizer = AutoTokenizer.from_pretrained(embedding_model_name)
            
            logger.info("Models loaded successfully")
    
    async def _connect_services(self):
        """Connect to external services."""
        try:
            # Connect to database
            self.db_engine = create_async_engine(config.database.url)
            logger.info("Connected to database")
            
            # Connect to MinIO
            self.minio_client = Minio(
                config.minio.endpoint,
                access_key=config.minio.access_key,
                secret_key=config.minio.secret_key,
                secure=config.minio.secure
            )
            logger.info("Connected to MinIO")
            
            # Connect to NATS
            self.nats_client = await nats.connect(config.nats.url)
            logger.info("Connected to NATS")
            
        except Exception as e:
            logger.error(f"Failed to connect to services: {e}")
            raise
    
    async def _check_model_health(self) -> bool:
        """Check if model is loaded and ready."""
        return self.model is not None and self.tokenizer is not None
    
    async def _check_database_health(self) -> bool:
        """Check database connection health."""
        try:
            async with self.db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    async def _check_minio_health(self) -> bool:
        """Check MinIO connection health."""
        try:
            return self.minio_client.bucket_exists(config.minio.bucket_name)
        except Exception:
            return False
    
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
    """Start the gRPC server."""
    server = aio.server()
    
    # Add the service to the server
    llm_pb2_grpc.add_LLMInferenceServicer_to_server(inference_service, server)
    
    # Start server
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting Inference API server on {listen_addr}")
    
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







