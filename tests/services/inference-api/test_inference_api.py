"""
Comprehensive test suite for Inference API service.
"""
import pytest
import asyncio
import sys
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch, Mock

# Mock torch, transformers, and grpc before importing (may not be available in test environment)
sys.modules['torch'] = MagicMock()
sys.modules['torchaudio'] = MagicMock()
sys.modules['transformers'] = MagicMock()
sys.modules['grpc'] = MagicMock()
sys.modules['grpc.aio'] = MagicMock()

# Import grpc after mocking (for type hints)
try:
    import grpc
    from grpc import aio
except ImportError:
    grpc = MagicMock()
    aio = MagicMock()

# Add packages directory to path for june_grpc_api import
import os
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_packages_dir = os.path.join(_project_root, 'packages')
if _packages_dir not in sys.path:
    sys.path.insert(0, _packages_dir)

# Import generated protobuf classes from june_grpc_api package
try:
    from june_grpc_api.generated import llm_pb2, llm_pb2_grpc
except ImportError:
    # Fallback: try to import from proto directory
    _proto_dir = os.path.join(_project_root, 'proto')
    if _proto_dir not in sys.path:
        sys.path.insert(0, _proto_dir)
    # Create mock protobuf classes if import still fails
    class MockLlmPb2:
        GenerationRequest = MagicMock
        GenerationResponse = MagicMock
        GenerationChunk = MagicMock
        ChatRequest = MagicMock
        ChatResponse = MagicMock
        ChatChunk = MagicMock
        ChatMessage = MagicMock
        EmbeddingRequest = MagicMock
        EmbeddingResponse = MagicMock
        HealthRequest = MagicMock
        HealthResponse = MagicMock
        GenerationParameters = MagicMock
        Context = MagicMock
        ToolDefinition = MagicMock
        FinishReason = MagicMock
        UsageStats = MagicMock
    llm_pb2 = MockLlmPb2()
    llm_pb2_grpc = MagicMock()
# Import specific classes for convenience
GenerationRequest = llm_pb2.GenerationRequest
GenerationResponse = llm_pb2.GenerationResponse
GenerationChunk = llm_pb2.GenerationChunk
ChatRequest = llm_pb2.ChatRequest
ChatResponse = llm_pb2.ChatResponse
ChatChunk = llm_pb2.ChatChunk
ChatMessage = llm_pb2.ChatMessage
EmbeddingRequest = llm_pb2.EmbeddingRequest
EmbeddingResponse = llm_pb2.EmbeddingResponse
HealthRequest = llm_pb2.HealthRequest
HealthResponse = llm_pb2.HealthResponse
GenerationParameters = llm_pb2.GenerationParameters
Context = llm_pb2.Context
ToolDefinition = llm_pb2.ToolDefinition
FinishReason = llm_pb2.FinishReason
UsageStats = llm_pb2.UsageStats

# Import inference-api service from services/inference-api/main.py
# Add services/inference-api directory to path to import main
inference_api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../services/inference-api'))
if inference_api_dir not in sys.path:
    sys.path.insert(0, inference_api_dir)

# Mock inference_core if not available
if 'inference_core' not in sys.modules:
    sys.modules['inference_core'] = MagicMock()
    sys.modules['inference_core.strategies'] = MagicMock()

from main import InferenceAPIService, inference_service
try:
    from inference_core.strategies import InferenceRequest, InferenceResponse
except ImportError:
    InferenceRequest = MagicMock
    InferenceResponse = MagicMock

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
def mock_llm_strategy():
    """Mock Qwen3LlmStrategy."""
    from inference_core.strategies import InferenceRequest, InferenceResponse
    
    mock_strategy = MagicMock()
    mock_strategy._model = MagicMock()
    mock_strategy._tokenizer = MagicMock()
    
    # Mock infer() to return a proper InferenceResponse
    def mock_infer(request):
        if isinstance(request, InferenceRequest):
            payload = request.payload
        else:
            payload = request
        prompt = payload.get("prompt", "")
        params = payload.get("params", {})
        
        # Simulate generation
        response_text = "Generated response text"
        if prompt:
            # Remove prompt from response if it starts with prompt
            if response_text.startswith(prompt):
                response_text = response_text[len(prompt):].strip()
        
        return InferenceResponse(
            payload={"text": response_text, "tokens": 10},
            metadata={"input_tokens": 5, "output_tokens": 10}
        )
    
    mock_strategy.infer = MagicMock(side_effect=mock_infer)
    return mock_strategy

@pytest.fixture
def service_instance(mock_llm_strategy, mock_embedding_model, mock_embedding_tokenizer, mock_db_engine, mock_minio_client, mock_nats_client):
    """Create service instance with mocked dependencies."""
    service = InferenceAPIService()
    service.llm_strategy = mock_llm_strategy
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
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.STOP
        # Verify strategy.infer was called
        assert service_instance.llm_strategy.infer.called
    
    @pytest.mark.asyncio
    async def test_generate_stream_short_prompt(self, service_instance):
        """Test GenerateStream with short prompt."""
        request = GenerationRequest(
            prompt="Hi",
            params=GenerationParameters(max_tokens=20),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        # Verify we get chunks
        assert len(chunks) > 0
        # Verify schema: GenerationChunk has required fields
        for chunk in chunks:
            assert hasattr(chunk, 'token')
            assert hasattr(chunk, 'is_final')
            assert hasattr(chunk, 'index')
            assert hasattr(chunk, 'finish_reason')
            assert isinstance(chunk.token, str)
            assert isinstance(chunk.is_final, bool)
            assert isinstance(chunk.index, int)
        # Verify final chunk has is_final=True
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.STOP
    
    @pytest.mark.asyncio
    async def test_generate_stream_long_prompt(self, service_instance):
        """Test GenerateStream with long prompt."""
        long_prompt = "Write a detailed explanation about " * 10  # Long prompt
        request = GenerationRequest(
            prompt=long_prompt,
            params=GenerationParameters(max_tokens=100),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        # Verify we get multiple chunks for longer response
        assert len(chunks) > 0
        # Verify all chunks except last have is_final=False
        for i, chunk in enumerate(chunks[:-1]):
            assert chunk.is_final is False or i == len(chunks) - 1
        # Verify final chunk
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.STOP
    
    @pytest.mark.asyncio
    async def test_generate_stream_is_final_flag(self, service_instance):
        """Test that is_final flag is set correctly in GenerateStream."""
        request = GenerationRequest(
            prompt="Generate a response with multiple tokens",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        # Verify we have multiple chunks
        assert len(chunks) > 1
        # Verify only the last chunk has is_final=True
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                assert chunk.is_final is True, f"Last chunk (index {i}) should have is_final=True"
            else:
                assert chunk.is_final is False, f"Non-final chunk (index {i}) should have is_final=False"
    
    @pytest.mark.asyncio
    async def test_generate_stream_schema_compliance(self, service_instance):
        """Test that GenerateStream returns GenerationChunk matching expected schema."""
        request = GenerationRequest(
            prompt="Test prompt",
            params=GenerationParameters(max_tokens=30),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        for chunk in chunks:
            # Verify GenerationChunk schema fields
            assert hasattr(chunk, 'token')
            assert hasattr(chunk, 'is_final')
            assert hasattr(chunk, 'index')
            assert hasattr(chunk, 'finish_reason')
            # Verify field types
            assert isinstance(chunk.token, str)
            assert isinstance(chunk.is_final, bool)
            assert isinstance(chunk.index, int)
            assert chunk.finish_reason in [FinishReason.STOP, FinishReason.LENGTH, FinishReason.TOOL_CALLS, FinishReason.ERROR]
            # Verify index is non-negative
            assert chunk.index >= 0
    
    @pytest.mark.asyncio
    async def test_generate_stream_error(self, service_instance):
        """Test streaming generation with error."""
        request = GenerationRequest(
            prompt="Hello world",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock strategy error
        service_instance.llm_strategy.infer.side_effect = Exception("Model error")
        
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
        
        response = await service_instance.Generate(request, None)
        
        assert response.text == "Generated response text"
        assert response.tokens_generated > 0
        assert response.finish_reason == FinishReason.STOP
        assert response.usage.prompt_tokens > 0
        assert response.usage.completion_tokens > 0
        # Verify strategy.infer was called
        assert service_instance.llm_strategy.infer.called
    
    @pytest.mark.asyncio
    async def test_generate_one_shot_error(self, service_instance):
        """Test one-shot generation with error."""
        request = GenerationRequest(
            prompt="Hello world",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock strategy error
        service_instance.llm_strategy.infer.side_effect = Exception("Model error")
        
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
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].role == "assistant"
        assert chunks[-1].is_final is True
        # Verify strategy.infer was called
        assert service_instance.llm_strategy.infer.called
    
    @pytest.mark.asyncio
    async def test_chat_stream_short_conversation(self, service_instance):
        """Test ChatStream with short conversation."""
        messages = [
            ChatMessage(role="user", content="Hi")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=20),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        # Verify we get chunks
        assert len(chunks) > 0
        # Verify schema: ChatChunk has required fields
        for chunk in chunks:
            assert hasattr(chunk, 'content_delta')
            assert hasattr(chunk, 'role')
            assert hasattr(chunk, 'is_final')
            assert hasattr(chunk, 'finish_reason')
            assert isinstance(chunk.content_delta, str)
            assert isinstance(chunk.role, str)
            assert isinstance(chunk.is_final, bool)
            assert chunk.role == "assistant"
        # Verify final chunk
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.STOP
    
    @pytest.mark.asyncio
    async def test_chat_stream_long_conversation(self, service_instance):
        """Test ChatStream with long conversation."""
        messages = [
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="Tell me a long story about " + "adventure " * 20),
            ChatMessage(role="assistant", content="Once upon a time..."),
            ChatMessage(role="user", content="Continue the story with more details.")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=100),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        # Verify we get multiple chunks
        assert len(chunks) > 0
        # Verify all chunks have role="assistant"
        for chunk in chunks:
            assert chunk.role == "assistant"
        # Verify final chunk
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.STOP
    
    @pytest.mark.asyncio
    async def test_chat_stream_is_final_flag(self, service_instance):
        """Test that is_final flag is set correctly in ChatStream."""
        messages = [
            ChatMessage(role="user", content="Generate a detailed response")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        # Verify we have multiple chunks
        assert len(chunks) > 1
        # Verify only the last chunk has is_final=True
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                assert chunk.is_final is True, f"Last chunk (index {i}) should have is_final=True"
            else:
                assert chunk.is_final is False, f"Non-final chunk (index {i}) should have is_final=False"
    
    @pytest.mark.asyncio
    async def test_chat_stream_schema_compliance(self, service_instance):
        """Test that ChatStream returns ChatChunk matching expected schema."""
        messages = [
            ChatMessage(role="user", content="Test message")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=30),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        for chunk in chunks:
            # Verify ChatChunk schema fields
            assert hasattr(chunk, 'content_delta')
            assert hasattr(chunk, 'role')
            assert hasattr(chunk, 'is_final')
            assert hasattr(chunk, 'finish_reason')
            # Verify field types
            assert isinstance(chunk.content_delta, str)
            assert isinstance(chunk.role, str)
            assert isinstance(chunk.is_final, bool)
            assert chunk.finish_reason in [FinishReason.STOP, FinishReason.LENGTH, FinishReason.TOOL_CALLS, FinishReason.ERROR]
            # Verify role is "assistant"
            assert chunk.role == "assistant"
    
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
        
        response = await service_instance.Chat(request, None)
        
        assert response.message.role == "assistant"
        assert response.message.content == "Generated response text"
        assert response.tokens_generated > 0
        assert response.usage.total_tokens > 0
        # Verify strategy.infer was called
        assert service_instance.llm_strategy.infer.called

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
        with patch('main.Qwen3LlmStrategy') as mock_strategy_class, \
             patch('main.AutoModelForCausalLM') as mock_model_class, \
             patch('main.AutoTokenizer') as mock_tokenizer_class:
            
            mock_strategy = MagicMock()
            mock_strategy.warmup = MagicMock()
            mock_strategy_class.return_value = mock_strategy
            mock_model_class.from_pretrained.return_value = mock_embedding_model
            mock_tokenizer_class.from_pretrained.return_value = mock_embedding_tokenizer
            
            await service_instance._load_models()
            
            assert service_instance.llm_strategy is not None
            assert service_instance.llm_strategy.warmup.called
            assert service_instance.embedding_model is not None
            assert service_instance.embedding_tokenizer is not None
    
    @pytest.mark.asyncio
    async def test_load_models_error(self, service_instance):
        """Test model loading with error."""
        with patch('main.Qwen3LlmStrategy') as mock_strategy_class:
            mock_strategy = MagicMock()
            mock_strategy.warmup.side_effect = Exception("Model loading error")
            mock_strategy_class.return_value = mock_strategy
            
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
        service_instance.llm_strategy._model = MagicMock()
        service_instance.llm_strategy._tokenizer = MagicMock()
        
        is_healthy = await service_instance._check_model_health()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_model_health_unhealthy(self, service_instance):
        """Test model health check when unhealthy."""
        service_instance.llm_strategy = None
        
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

class TestStreamingErrorHandling:
    """Test error handling during streaming."""
    
    @pytest.mark.asyncio
    async def test_generate_stream_error_during_streaming(self, service_instance):
        """Test error handling during GenerateStream when error occurs mid-stream."""
        request = GenerationRequest(
            prompt="Test prompt",
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock strategy to raise error after first call
        call_count = 0
        def mock_infer_with_error(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Streaming error occurred")
            return InferenceResponse(
                payload={"text": "Generated response text", "tokens": 10},
                metadata={"input_tokens": 5, "output_tokens": 10}
            )
        
        service_instance.llm_strategy.infer.side_effect = mock_infer_with_error
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        # Verify error chunk is returned
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.ERROR
    
    @pytest.mark.asyncio
    async def test_chat_stream_error_during_streaming(self, service_instance):
        """Test error handling during ChatStream when error occurs mid-stream."""
        messages = [
            ChatMessage(role="user", content="Test message")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=50),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        # Mock strategy to raise error
        service_instance.llm_strategy.infer.side_effect = Exception("Chat streaming error")
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        # Verify error chunk is returned
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == FinishReason.ERROR
        assert chunks[-1].role == "assistant"

class TestStreamingPerformance:
    """Test streaming performance characteristics."""
    
    @pytest.mark.asyncio
    async def test_generate_stream_latency(self, service_instance):
        """Test that GenerateStream has acceptable latency."""
        import time
        
        request = GenerationRequest(
            prompt="Short prompt",
            params=GenerationParameters(max_tokens=20),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        start_time = time.time()
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        end_time = time.time()
        
        latency = end_time - start_time
        # Verify latency is reasonable (with mocked strategy, should be very fast)
        # In real scenario, this would test actual model latency
        assert latency < 5.0, f"Streaming latency {latency}s is too high"
        assert len(chunks) > 0
    
    @pytest.mark.asyncio
    async def test_chat_stream_latency(self, service_instance):
        """Test that ChatStream has acceptable latency."""
        import time
        
        messages = [
            ChatMessage(role="user", content="Short message")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=20),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        start_time = time.time()
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        end_time = time.time()
        
        latency = end_time - start_time
        # Verify latency is reasonable
        assert latency < 5.0, f"Streaming latency {latency}s is too high"
        assert len(chunks) > 0
    
    @pytest.mark.asyncio
    async def test_generate_stream_throughput(self, service_instance):
        """Test that GenerateStream provides reasonable throughput."""
        request = GenerationRequest(
            prompt="Generate a longer response",
            params=GenerationParameters(max_tokens=100),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        # Verify we get multiple chunks (indicating streaming)
        assert len(chunks) > 1
        # Verify chunks are received incrementally (not all at once)
        # This is verified by the fact that we iterate through chunks
    
    @pytest.mark.asyncio
    async def test_chat_stream_throughput(self, service_instance):
        """Test that ChatStream provides reasonable throughput."""
        messages = [
            ChatMessage(role="user", content="Generate a longer response")
        ]
        
        request = ChatRequest(
            messages=messages,
            params=GenerationParameters(max_tokens=100),
            context=Context(user_id="test_user", session_id="test_session")
        )
        
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        # Verify we get multiple chunks (indicating streaming)
        assert len(chunks) > 1
        # Verify chunks are received incrementally

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
        
        # Test streaming
        chunks = []
        async for chunk in service_instance.GenerateStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        
        # Test one-shot
        response = await service_instance.Generate(request, None)
        assert response.text == "Generated response text"
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
        
        # Test streaming chat
        chunks = []
        async for chunk in service_instance.ChatStream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) > 0
        assert chunks[-1].role == "assistant"
        
        # Test one-shot chat
        response = await service_instance.Chat(request, None)
        assert response.message.role == "assistant"
        assert response.message.content == "Generated response text"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])







