"""
Comprehensive test suite for Inference API service.
"""
import pytest
import asyncio
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import torch
import grpc
from grpc import aio

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

from main import InferenceAPIService, inference_service

@pytest.fixture
def mock_model():
    """Mock transformer model."""
    mock_model = MagicMock()
    mock_model.generate = MagicMock()
    mock_model.to = MagicMock(return_value=mock_model)
    return mock_model

@pytest.fixture
def mock_tokenizer():
    """Mock tokenizer."""
    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {
        "input_ids": torch.tensor([[1, 2, 3, 4, 5]]),
        "attention_mask": torch.tensor([[1, 1, 1, 1, 1]])
    }
    mock_tokenizer.decode = MagicMock(return_value="Generated response text")
    mock_tokenizer.eos_token_id = 2
    mock_tokenizer.pad_token = "<pad>"
    return mock_tokenizer

@pytest.fixture
def mock_embedding_model():
    """Mock embedding model."""
    mock_model = MagicMock()
    mock_model.return_value = MagicMock(
        last_hidden_state=torch.randn(2, 10, 384)
    )
    return mock_model

@pytest.fixture
def mock_embedding_tokenizer():
    """Mock embedding tokenizer."""
    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {
        "input_ids": torch.tensor([[1, 2, 3], [4, 5, 6]]),
        "attention_mask": torch.tensor([[1, 1, 1], [1, 1, 1]])
    }
    return mock_tokenizer

@pytest.fixture
def mock_db_engine():
    """Mock database engine."""
    mock_engine = AsyncMock()
    mock_conn = AsyncMock()
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = [
        Mock(id="doc1", title="Test Doc", content="Test content", source_url="http://test.com", metadata={})
    ]
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__aenter__.return_value = mock_conn
    return mock_engine

@pytest.fixture
def mock_minio_client():
    """Mock MinIO client."""
    mock_minio = MagicMock()
    mock_minio.bucket_exists.return_value = True
    return mock_minio

@pytest.fixture
def mock_nats_client():
    """Mock NATS client."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    return mock_nats

@pytest.fixture
def service_instance(mock_model, mock_tokenizer, mock_embedding_model, mock_embedding_tokenizer, mock_db_engine, mock_minio_client, mock_nats_client):
    """Create service instance with mocked dependencies."""
    service = InferenceAPIService()
    service.model = mock_model
    service.tokenizer = mock_tokenizer
    service.embedding_model = mock_embedding_model
    service.embedding_tokenizer = mock_embedding_tokenizer
    service.db_engine = mock_db_engine
    service.minio_client = mock_minio_client
    service.nats_client = mock_nats_client
    return service

class TestGeneration:
    """Test text generation functionality."""
    
    @pytest.mark.asyncio
    async def test_generate_stream_success(self, service_instance):
        """Test successful streaming generation."""
        request = GenerationRequest(
            prompt="Hello world",
            params=GenerationParameters(
                max_tokens=50,
                temperature=0.7,
                top_p=0.9
            ),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock model generation
        mock_output = MagicMock()
        mock_output.sequences = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]])
        service_instance.model.generate.return_value = mock_output
        service_instance.tokenizer.decode.return_value = "Hello world Generated response text"
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.STOP
    
    @pytest.mark.asyncio
    async def test_generate_stream_error(self, service_instance):
        """Test streaming generation with error."""
        request = GenerationRequest(
            prompt="Hello world",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock model error
        service_instance.model.generate.side_effect = Exception("Model error")
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) == 1
        assert chunks[0].is_final is True
        assert chunks[0].finish_reason == FinishReason.ERROR
    
    @pytest.mark.asyncio
    async def test_generate_one_shot_success(self, service_instance):
        """Test successful one-shot generation."""
        request = GenerationRequest(
            prompt="Hello world",
            params=GenerationParameters(
                max_tokens=50,
                temperature=0.7
            ),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock model generation
        mock_output = MagicMock()
        mock_output.sequences = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]])
        service_instance.model.generate.return_value = mock_output
        service_instance.tokenizer.decode.return_value = "Hello world Generated response text"
        
        response = await service_instance.Generate(request, None)
        
        assert response.text == "Generated response text"
        assert response.tokens_generated > 0
        assert response.finish_reason == FinishReason.STOP
        assert response.usage.prompt_tokens > 0
        assert response.usage.completion_tokens > 0
    
    @pytest.mark.asyncio
    async def test_generate_one_shot_error(self, service_instance):
        """Test one-shot generation with error."""
        request = GenerationRequest(
            prompt="Hello world",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock model error
        service_instance.model.generate.side_effect = Exception("Model error")
        
        context = MagicMock()
        response = await service_instance.Generate(request, context)
        
        assert response.text == ""
        context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

class TestChat:
    """Test chat functionality."""
    
    @pytest.mark.asyncio
    async def test_chat_stream_success(self, service_instance):
        """Test successful streaming chat."""
        messages = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there!"),
            ChatMessage(role="user", content="How are you?")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock model generation
        mock_output = MagicMock()
        mock_output.sequences = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]])
        service_instance.model.generate.return_value = mock_output
        service_instance.tokenizer.decode.return_value = "Human: Hello\n\nAssistant: Hi there!\n\nHuman: How are you?\n\nAssistant: Generated response text"
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].role == "assistant"
        assert chunks[-1].is_final is True
    
    @pytest.mark.asyncio
    async def test_chat_one_shot_success(self, service_instance):
        """Test successful one-shot chat."""
        messages = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there!"),
            ChatMessage(role="user", content="How are you?")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock model generation
        mock_output = MagicMock()
        mock_output.sequences = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]])
        service_instance.model.generate.return_value = mock_output
        service_instance.tokenizer.decode.return_value = "Human: Hello\n\nAssistant: Hi there!\n\nHuman: How are you?\n\nAssistant: Generated response text"
        
        response = await service_instance.Chat(request, None)
        
        assert response.message.role == "assistant"
        assert response.message.content == "Generated response text"
        assert response.tokens_generated > 0
        assert response.usage.total_tokens > 0

class TestEmbeddings:
    """Test embedding generation."""
    
    @pytest.mark.asyncio
    async def test_embed_success(self, service_instance):
        """Test successful embedding generation."""
        request = EmbeddingRequest(
            texts=["Hello world", "Test text"],
            model="test-model"
        )
        
        # Mock embedding generation
        mock_embeddings = torch.randn(2, 384)
        service_instance.embedding_model.return_value = MagicMock(
            last_hidden_state=mock_embeddings.unsqueeze(0)
        )
        
        response = await service_instance.Embed(request, None)
        
        assert len(response.embeddings) == 2 * 384  # 2 texts * 384 dimensions
        assert response.dimension == 384
    
    @pytest.mark.asyncio
    async def test_embed_error(self, service_instance):
        """Test embedding generation with error."""
        request = EmbeddingRequest(
            texts=["Hello world"],
            model="test-model"
        )
        
        # Mock embedding error
        service_instance.embedding_model.side_effect = Exception("Embedding error")
        
        context = MagicMock()
        response = await service_instance.Embed(request, context)
        
        assert len(response.embeddings) == 0
        context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

class TestHealthCheck:
    """Test health check functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, service_instance):
        """Test health check when all services are healthy."""
        with patch.object(service_instance, '_check_model_health', return_value=True), \
             patch.object(service_instance, '_check_database_health', return_value=True), \
             patch.object(service_instance, '_check_minio_health', return_value=True), \
             patch.object(service_instance, '_check_nats_health', return_value=True):
            
            request = HealthRequest()
            response = await service_instance.HealthCheck(request, None)
            
            assert response.healthy is True
            assert response.version == "0.2.0"
            assert response.model_name is not None
            assert response.max_context_length > 0
            assert response.supports_streaming is True
            assert len(response.available_tools) > 0
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, service_instance):
        """Test health check when services are unhealthy."""
        with patch.object(service_instance, '_check_model_health', return_value=False), \
             patch.object(service_instance, '_check_database_health', return_value=True), \
             patch.object(service_instance, '_check_minio_health', return_value=True), \
             patch.object(service_instance, '_check_nats_health', return_value=True):
            
            request = HealthRequest()
            response = await service_instance.HealthCheck(request, None)
            
            assert response.healthy is False

class TestContextPreparation:
    """Test context preparation functionality."""
    
    @pytest.mark.asyncio
    async def test_prepare_context_without_rag(self, service_instance):
        """Test context preparation without RAG documents."""
        context = Context(
            user_id="test_user",
            session_id="test_session",
            enable_tools=True,
            available_tools=[ToolDefinition(name="test_tool", description="Test tool")]
        )
        
        context_data = await service_instance._prepare_context(context)
        
        assert context_data["user_id"] == "test_user"
        assert context_data["session_id"] == "test_session"
        assert len(context_data["rag_documents"]) == 0
        assert len(context_data["tools"]) == 1
    
    @pytest.mark.asyncio
    async def test_prepare_context_with_rag(self, service_instance):
        """Test context preparation with RAG documents."""
        context = Context(
            user_id="test_user",
            session_id="test_session",
            rag_document_ids=["doc1", "doc2"]
        )
        
        context_data = await service_instance._prepare_context(context)
        
        assert context_data["user_id"] == "test_user"
        assert len(context_data["rag_documents"]) == 1  # Mock returns 1 document
        assert context_data["rag_documents"][0]["id"] == "doc1"

class TestConversationFormatting:
    """Test conversation formatting functionality."""
    
    @pytest.mark.asyncio
    async def test_format_conversation_basic(self, service_instance):
        """Test basic conversation formatting."""
        messages = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there!"),
            ChatMessage(role="user", content="How are you?")
        ]
        
        context_data = {"rag_documents": []}
        
        formatted = await service_instance._format_conversation(messages, context_data)
        
        assert "Human: Hello" in formatted
        assert "Assistant: Hi there!" in formatted
        assert "Human: How are you?" in formatted
        assert formatted.endswith("\n\nAssistant:")
    
    @pytest.mark.asyncio
    async def test_format_conversation_with_rag(self, service_instance):
        """Test conversation formatting with RAG context."""
        messages = [
            ChatMessage(role="user", content="What is the capital of France?")
        ]
        
        context_data = {
            "rag_documents": [
                {
                    "title": "Geography Facts",
                    "content": "Paris is the capital of France."
                }
            ]
        }
        
        formatted = await service_instance._format_conversation(messages, context_data)
        
        assert "Context:" in formatted
        assert "Document: Geography Facts" in formatted
        assert "Paris is the capital of France." in formatted
        assert "Human: What is the capital of France?" in formatted

class TestRAGRetrieval:
    """Test RAG document retrieval."""
    
    @pytest.mark.asyncio
    async def test_retrieve_rag_documents_success(self, service_instance):
        """Test successful RAG document retrieval."""
        document_ids = ["doc1", "doc2"]
        
        documents = await service_instance._retrieve_rag_documents(document_ids)
        
        assert len(documents) == 1  # Mock returns 1 document
        assert documents[0]["id"] == "doc1"
        assert documents[0]["title"] == "Test Doc"
        assert documents[0]["content"] == "Test content"
    
    @pytest.mark.asyncio
    async def test_retrieve_rag_documents_error(self, service_instance):
        """Test RAG document retrieval with error."""
        # Mock database error
        service_instance.db_engine.begin.side_effect = Exception("Database error")
        
        document_ids = ["doc1"]
        documents = await service_instance._retrieve_rag_documents(document_ids)
        
        assert len(documents) == 0

class TestModelLoading:
    """Test model loading functionality."""
    
    @pytest.mark.asyncio
    async def test_load_models_success(self, service_instance):
        """Test successful model loading."""
        with patch('main.AutoModelForCausalLM') as mock_model_class, \
             patch('main.AutoTokenizer') as mock_tokenizer_class:
            
            mock_model_class.from_pretrained.return_value = mock_model
            mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
            
            await service_instance._load_models()
            
            assert service_instance.model is not None
            assert service_instance.tokenizer is not None
            assert service_instance.embedding_model is not None
            assert service_instance.embedding_tokenizer is not None
    
    @pytest.mark.asyncio
    async def test_load_models_error(self, service_instance):
        """Test model loading with error."""
        with patch('main.AutoModelForCausalLM') as mock_model_class:
            mock_model_class.from_pretrained.side_effect = Exception("Model loading error")
            
            with pytest.raises(Exception):
                await service_instance._load_models()

class TestServiceConnections:
    """Test service connection functionality."""
    
    @pytest.mark.asyncio
    async def test_connect_services_success(self, service_instance):
        """Test successful service connections."""
        with patch('main.create_async_engine') as mock_engine, \
             patch('main.Minio') as mock_minio, \
             patch('main.nats.connect') as mock_nats:
            
            mock_engine.return_value = mock_db_engine
            mock_minio.return_value = mock_minio_client
            mock_nats.return_value = mock_nats_client
            
            await service_instance._connect_services()
            
            assert service_instance.db_engine is not None
            assert service_instance.minio_client is not None
            assert service_instance.nats_client is not None
    
    @pytest.mark.asyncio
    async def test_connect_services_error(self, service_instance):
        """Test service connections with error."""
        with patch('main.create_async_engine') as mock_engine:
            mock_engine.side_effect = Exception("Connection error")
            
            with pytest.raises(Exception):
                await service_instance._connect_services()

class TestHealthChecks:
    """Test individual health check methods."""
    
    @pytest.mark.asyncio
    async def test_check_model_health_healthy(self, service_instance):
        """Test model health check when healthy."""
        service_instance.model = mock_model
        service_instance.tokenizer = mock_tokenizer
        
        is_healthy = await service_instance._check_model_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_model_health_unhealthy(self, service_instance):
        """Test model health check when unhealthy."""
        service_instance.model = None
        service_instance.tokenizer = None
        
        is_healthy = await service_instance._check_model_health()
        assert is_healthy is False
    
    @pytest.mark.asyncio
    async def test_check_database_health_healthy(self, service_instance):
        """Test database health check when healthy."""
        is_healthy = await service_instance._check_database_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_database_health_unhealthy(self, service_instance):
        """Test database health check when unhealthy."""
        service_instance.db_engine.begin.side_effect = Exception("Database error")
        
        is_healthy = await service_instance._check_database_health()
        assert is_healthy is False
    
    @pytest.mark.asyncio
    async def test_check_minio_health_healthy(self, service_instance):
        """Test MinIO health check when healthy."""
        is_healthy = await service_instance._check_minio_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_minio_health_unhealthy(self, service_instance):
        """Test MinIO health check when unhealthy."""
        service_instance.minio_client.bucket_exists.side_effect = Exception("MinIO error")
        
        is_healthy = await service_instance._check_minio_health()
        assert is_healthy is False
    
    @pytest.mark.asyncio
    async def test_check_nats_health_healthy(self, service_instance):
        """Test NATS health check when healthy."""
        is_healthy = await service_instance._check_nats_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_nats_health_unhealthy(self, service_instance):
        """Test NATS health check when unhealthy."""
        service_instance.nats_client = None
        
        is_healthy = await service_instance._check_nats_health()
        assert is_healthy is False

# Integration tests
class TestInferenceAPIIntegration:
    """Integration tests for Inference API service."""
    
    @pytest.mark.asyncio
    async def test_full_generation_flow(self, service_instance):
        """Test complete generation flow."""
        # Test streaming generation
        request = GenerationRequest(
            prompt="Write a short story about a robot.",
            params=GenerationParameters(
                max_tokens=100,
                temperature=0.8,
                top_p=0.9
            ),
            context=Context(
                user_id="test_user",
                session_id="test_session",
                enable_tools=True
            )
        )
        
        # Mock successful generation
        mock_output = MagicMock()
        mock_output.sequences = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]])
        service_instance.model.generate.return_value = mock_output
        service_instance.tokenizer.decode.return_value = "Write a short story about a robot. Once upon a time, there was a robot named Robo."
        
        # Test streaming
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        
        # Test one-shot
        response = await service_instance.Generate(request, None)
        assert response.text == "Once upon a time, there was a robot named Robo."
        assert response.tokens_generated > 0
    
    @pytest.mark.asyncio
    async def test_full_chat_flow(self, service_instance):
        """Test complete chat flow."""
        messages = [
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="2+2 equals 4."),
            ChatMessage(role="user", content="What about 3+3?")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(
                user_id="test_user",
                session_id="test_session",
                enable_tools=True
            )
        )
        
        # Mock successful generation
        mock_output = MagicMock()
        mock_output.sequences = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]])
        service_instance.model.generate.return_value = mock_output
        service_instance.tokenizer.decode.return_value = "System: You are a helpful assistant.\n\nHuman: What is 2+2?\n\nAssistant: 2+2 equals 4.\n\nHuman: What about 3+3?\n\nAssistant: 3+3 equals 6."
        
        # Test streaming chat
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].role == "assistant"
        
        # Test one-shot chat
        response = await service_instance.Chat(request, None)
        assert response.message.role == "assistant"
        assert response.message.content == "3+3 equals 6."

if __name__ == "__main__":
    pytest.main([__file__, "-v"])







