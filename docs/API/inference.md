# Inference API (gRPC)

The Inference API provides gRPC endpoints for LLM (Large Language Model) inference, including text generation, chat, and embeddings.

**Current Implementation:** TensorRT-LLM (via Triton Inference Server)  
**Legacy Implementation:** inference-api service (available via `--profile legacy`)

## Service Definition

**Service Name:** `june.llm.LLMInference`

**Default Address:** `tensorrt-llm:8000` (TensorRT-LLM in home_infra/shared-network)  
**Legacy Address:** `inference-api:50051` (legacy inference-api service, requires `--profile legacy`)

## Protocol Buffer Definition

The service is defined in `proto/llm.proto`:

```protobuf
service LLMInference {
  rpc GenerateStream(GenerationRequest) returns (stream GenerationChunk);
  rpc Generate(GenerationRequest) returns (GenerationResponse);
  rpc ChatStream(ChatRequest) returns (stream ChatChunk);
  rpc Chat(ChatRequest) returns (ChatResponse);
  rpc Embed(EmbeddingRequest) returns (EmbeddingResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}
```

## Methods

### GenerateStream

Streaming text generation.

**Request:**
```protobuf
message GenerationRequest {
  string prompt = 1;
  GenerationParameters params = 2;
  Context context = 3;
  bool stream = 4;
}
```

**Response (stream):**
```protobuf
message GenerationChunk {
  string token = 1;
  bool is_final = 2;
  int32 index = 3;
  float logprob = 4;
  repeated ToolCall tool_calls = 5;
  FinishReason finish_reason = 6;
}
```

**Example (Python):**
```python
import grpc
from june_grpc_api import llm as llm_shim

async def generate_stream():
    # Default: TensorRT-LLM (tensorrt-llm:8000)
    # Legacy: inference-api (inference-api:50051)
    async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
        client = llm_shim.LLMClient(channel)
        
        request = llm_shim.GenerationRequest(
            prompt="Hello, how are you?",
            params=llm_shim.GenerationParameters(
                max_tokens=100,
                temperature=0.7
            )
        )
        
        async for chunk in client.generate_stream(request):
            print(chunk.token, end="", flush=True)
            if chunk.is_final:
                break

import asyncio
asyncio.run(generate_stream())
```

### Generate

One-shot text generation.

**Request:**
```protobuf
message GenerationRequest {
  string prompt = 1;
  GenerationParameters params = 2;
  Context context = 3;
  bool stream = 4;
}
```

**Response:**
```protobuf
message GenerationResponse {
  string text = 1;
  int32 tokens_generated = 2;
  float tokens_per_second = 3;
  repeated ToolCall tool_calls = 4;
  FinishReason finish_reason = 5;
  UsageStats usage = 6;
}
```

**Example (Python):**
```python
import grpc
from june_grpc_api import llm as llm_shim

async def generate():
    # Default: TensorRT-LLM (tensorrt-llm:8000)
    async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
        client = llm_shim.LLMClient(channel)
        
        request = llm_shim.GenerationRequest(
            prompt="Hello, how are you?",
            params=llm_shim.GenerationParameters(
                max_tokens=100,
                temperature=0.7
            )
        )
        
        response = await client.generate(request)
        print(response.text)
        print(f"Tokens: {response.tokens_generated}")
        print(f"Speed: {response.tokens_per_second} tokens/sec")

import asyncio
asyncio.run(generate())
```

### ChatStream

Streaming chat with conversation history.

**Request:**
```protobuf
message ChatRequest {
  repeated ChatMessage messages = 1;
  GenerationParameters params = 2;
  Context context = 3;
  bool stream = 4;
}

message ChatMessage {
  string role = 1;  // "system", "user", "assistant", "tool"
  string content = 2;
  string name = 3;
  FunctionCall function_call = 4;
  repeated ToolCall tool_calls = 5;
}
```

**Response (stream):**
```protobuf
message ChatChunk {
  string content_delta = 1;
  string role = 2;
  bool is_final = 3;
  repeated ToolCall tool_calls = 4;
  FinishReason finish_reason = 5;
}
```

**Example (Python):**
```python
import grpc
from june_grpc_api import llm as llm_shim

async def chat_stream():
    # Default: TensorRT-LLM (tensorrt-llm:8000)
    async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
        client = llm_shim.LLMClient(channel)
        
        messages = [
            llm_shim.ChatMessage(role="system", content="You are a helpful assistant."),
            llm_shim.ChatMessage(role="user", content="Hello!")
        ]
        
        request = llm_shim.ChatRequest(
            messages=messages,
            params=llm_shim.GenerationParameters(temperature=0.7)
        )
        
        async for chunk in client.chat_stream(request):
            print(chunk.content_delta, end="", flush=True)
            if chunk.is_final:
                break

import asyncio
asyncio.run(chat_stream())
```

### Chat

One-shot chat with conversation history.

**Request:**
```protobuf
message ChatRequest {
  repeated ChatMessage messages = 1;
  GenerationParameters params = 2;
  Context context = 3;
  bool stream = 4;
}
```

**Response:**
```protobuf
message ChatResponse {
  ChatMessage message = 1;
  int32 tokens_generated = 2;
  float tokens_per_second = 3;
  UsageStats usage = 4;
}
```

**Example (Python):**
```python
import grpc
from june_grpc_api import llm as llm_shim

async def chat():
    # Default: TensorRT-LLM (tensorrt-llm:8000)
    async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
        client = llm_shim.LLMClient(channel)
        
        messages = [
            llm_shim.ChatMessage(role="system", content="You are a helpful assistant."),
            llm_shim.ChatMessage(role="user", content="Hello!")
        ]
        
        request = llm_shim.ChatRequest(
            messages=messages,
            params=llm_shim.GenerationParameters(temperature=0.7)
        )
        
        response = await client.chat(request)
        print(response.message.content)

import asyncio
asyncio.run(chat())
```

### Embed

Generate embeddings for text.

**Request:**
```protobuf
message EmbeddingRequest {
  repeated string texts = 1;
  string model = 2;
}
```

**Response:**
```protobuf
message EmbeddingResponse {
  repeated float embeddings = 1;  // Flattened: [text1_dim1, text1_dim2, ..., textN_dimD]
  int32 dimension = 2;
}
```

**Example (Python):**
```python
import grpc
from june_grpc_api import llm as llm_shim

async def embed():
    # Default: TensorRT-LLM (tensorrt-llm:8000)
    async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
        client = llm_shim.LLMClient(channel)
        
        request = llm_shim.EmbeddingRequest(
            texts=["Hello world", "How are you?"],
            model="default"
        )
        
        response = await client.embed(request)
        print(f"Dimension: {response.dimension}")
        print(f"Embeddings: {len(response.embeddings)} floats")

import asyncio
asyncio.run(embed())
```

### HealthCheck

Check service health.

**Request:**
```protobuf
message HealthRequest {}
```

**Response:**
```protobuf
message HealthResponse {
  bool healthy = 1;
  string version = 2;
  string model_name = 3;
  int32 max_context_length = 4;
  bool supports_streaming = 5;
  repeated string available_tools = 6;
}
```

**Example (Python):**
```python
import grpc
from june_grpc_api import llm as llm_shim

async def health_check():
    # Default: TensorRT-LLM (tensorrt-llm:8000)
    async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
        client = llm_shim.LLMClient(channel)
        
        response = await client.health_check(llm_shim.HealthRequest())
        print(f"Healthy: {response.healthy}")
        print(f"Model: {response.model_name}")
        print(f"Max context: {response.max_context_length}")

import asyncio
asyncio.run(health_check())
```

## Message Types

### GenerationParameters

```protobuf
message GenerationParameters {
  int32 max_tokens = 1;
  float temperature = 2;
  float top_p = 3;
  float top_k = 4;
  float repetition_penalty = 5;
  repeated string stop_sequences = 6;
  int32 seed = 7;
}
```

**Parameters:**
- `max_tokens`: Maximum number of tokens to generate
- `temperature`: Sampling temperature (0.0-2.0, higher = more random)
- `top_p`: Nucleus sampling parameter (0.0-1.0)
- `top_k`: Top-k sampling parameter
- `repetition_penalty`: Penalty for repetition (1.0 = no penalty)
- `stop_sequences`: Sequences that stop generation
- `seed`: Random seed for reproducibility

### Context

```protobuf
message Context {
  string user_id = 1;
  string session_id = 2;
  repeated string rag_document_ids = 3;  // For RAG retrieval
  bool enable_tools = 4;
  repeated ToolDefinition available_tools = 5;
  int32 max_context_tokens = 6;
}
```

**Fields:**
- `user_id`: User identifier
- `session_id`: Session identifier
- `rag_document_ids`: Document IDs for RAG (Retrieval-Augmented Generation)
- `enable_tools`: Enable tool/function calling
- `available_tools`: List of available tools
- `max_context_tokens`: Maximum context window size

### ToolDefinition

```protobuf
message ToolDefinition {
  string name = 1;
  string description = 2;
  string parameters_schema = 3;  // JSON schema
}
```

### ToolCall

```protobuf
message ToolCall {
  string id = 1;
  string type = 2;  // "function"
  FunctionCall function = 3;
}

message FunctionCall {
  string name = 1;
  string arguments = 2;  // JSON string
}
```

### FinishReason

```protobuf
enum FinishReason {
  STOP = 0;        // Natural stop
  LENGTH = 1;      // Max tokens reached
  TOOL_CALLS = 2;  // Tool calls requested
  ERROR = 3;       // Error occurred
}
```

### UsageStats

```protobuf
message UsageStats {
  int32 prompt_tokens = 1;
  int32 completion_tokens = 2;
  int32 total_tokens = 3;
  int32 prompt_cache_hits = 4;
}
```

## Error Handling

gRPC errors follow standard gRPC status codes:

- `OK (0)`: Success
- `INVALID_ARGUMENT (3)`: Invalid request parameters
- `NOT_FOUND (5)`: Resource not found
- `RESOURCE_EXHAUSTED (8)`: Rate limit or quota exceeded
- `INTERNAL (13)`: Internal server error
- `UNAVAILABLE (14)`: Service unavailable

**Example Error Handling (Python):**
```python
import grpc
from june_grpc_api import llm as llm_shim

async def generate_with_error_handling():
    try:
        # Default: TensorRT-LLM (tensorrt-llm:8000)
        async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
            client = llm_shim.LLMClient(channel)
            request = llm_shim.GenerationRequest(prompt="Hello")
            response = await client.generate(request)
            print(response.text)
    except grpc.aio.AioRpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            print(f"Invalid argument: {e.details()}")
        elif e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            print(f"Rate limit exceeded: {e.details()}")
        else:
            print(f"Error: {e.code()}: {e.details()}")

import asyncio
asyncio.run(generate_with_error_handling())
```

## Connection Pooling

For production use, use connection pooling to manage gRPC channels efficiently:

```python
from june_grpc_api.grpc_pool import get_grpc_pool

async def use_pool():
    pool = get_grpc_pool()
    async with pool.get_llm_channel() as channel:
        client = llm_shim.LLMClient(channel)
        # Use client...
```

## Streaming Best Practices

1. **Handle chunks incrementally**: Process chunks as they arrive for better UX
2. **Check `is_final` flag**: Final chunk indicates completion
3. **Handle errors**: Streams can fail mid-stream
4. **Cancel streams**: Cancel unused streams to free resources

**Example:**
```python
async def robust_stream():
    try:
            # Default: TensorRT-LLM (tensorrt-llm:8000)
            async with grpc.aio.insecure_channel("tensorrt-llm:8000") as channel:
                client = llm_shim.LLMClient(channel)
                request = llm_shim.GenerationRequest(prompt="Hello", stream=True)
            
            async for chunk in client.generate_stream(request):
                if chunk.token:
                    print(chunk.token, end="", flush=True)
                if chunk.is_final:
                    if chunk.finish_reason == llm_shim.FinishReason.STOP:
                        print("\n[Completed]")
                    elif chunk.finish_reason == llm_shim.FinishReason.LENGTH:
                        print("\n[Max tokens reached]")
                    break
    except Exception as e:
        print(f"Stream error: {e}")
```

## Authentication

gRPC authentication can be configured via channel credentials. For production, use TLS:

```python
import grpc

# TLS credentials
# Default: TensorRT-LLM (tensorrt-llm:8000)
credentials = grpc.ssl_channel_credentials()
channel = grpc.aio.secure_channel("tensorrt-llm:8000", credentials)
```

## Rate Limiting

Rate limiting is handled at the service level. Direct gRPC connections may have different limits. Check service documentation for specific rate limits.

## Migration from inference-api to TensorRT-LLM

The project is migrating from the legacy `inference-api` service to TensorRT-LLM for optimized GPU inference. 

**Current Status:**
- ✅ TensorRT-LLM is the default implementation (`tensorrt-llm:8000`)
- ✅ All services default to TensorRT-LLM
- ⏳ Legacy `inference-api` service still available via `--profile legacy` for backward compatibility

**To use legacy inference-api:**
- Set `LLM_URL=grpc://inference-api:50051` environment variable
- Start service with `docker compose --profile legacy up -d inference-api`

**See:** `docs/guides/TENSORRT_LLM_SETUP.md` for TensorRT-LLM setup and migration guide.
