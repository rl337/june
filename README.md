# June Agent - Interactive Autonomous Agent

June is an interactive autonomous agent system built with microservices architecture, featuring speech-to-text, text-to-speech, and LLM orchestration capabilities. The system is optimized for NVIDIA DGX Spark with GPU sharing and CUDA MPS.

## 🏗️ Architecture Overview

June follows GPT5's recommended microservices architecture with the following components:

### Core Services

- **Gateway Service** - FastAPI + WebSocket ingress with authentication, rate limiting, and streaming
- **Inference API** - gRPC coordinator for LLM orchestration with RAG and tool invocation
- **STT Service** - Speech-to-Text with Whisper, VAD, and gRPC streaming
- **TTS Service** - Text-to-Speech with FastSpeech2/HiFi-GAN and streaming
- **Webapp Service** - React-based Telegram-like chat interface

### CLI Tools Container
- **Purpose:** Development tools and model management
- **Access:** `docker exec -it june-cli-tools bash`
- **Profile:** `tools` (use `--profile tools` to start)

**Available Tools:**
- Model download script (`scripts/download_models.py`)
- Development utilities (black, isort, flake8, mypy)
- Testing tools (pytest, pytest-cov)
- Audio processing (whisper, TTS, librosa)

### Supporting Infrastructure

- **PostgreSQL + pgvector** - Long-term memory, conversation state, and RAG storage
- **MinIO** - S3-compatible object storage for audio, transcripts, and model artifacts
- **NATS** - Low-latency pub/sub messaging for events and control
- **Prometheus + Grafana** - Metrics collection and dashboards
- **Loki** - Log aggregation
- **Jaeger** - Distributed tracing

## 🛠️ CLI Tools Usage

### Model Management
```bash
# Start CLI tools container
docker compose --profile tools up -d cli-tools

# Download all required models
docker exec -it june-cli-tools python scripts/download_models.py --all

# Check model cache status
docker exec -it june-cli-tools python scripts/download_models.py --status

# List authorized models
docker exec -it june-cli-tools python scripts/download_models.py --list
```

### Development Tools
```bash
# Access CLI container
docker exec -it june-cli-tools bash

# Code formatting
black /app/scripts/
isort /app/scripts/

# Linting and testing
flake8 /app/scripts/
mypy /app/scripts/
pytest /app/scripts/
```

## 🚀 Quick Start

### Prerequisites

- NVIDIA DGX Spark with CUDA support
- Docker and Docker Compose
- NVIDIA Container Toolkit
- Python 3.10+

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd june
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start the system:**
   ```bash
   docker-compose up -d
   ```

4. **Verify services are running:**
   ```bash
   docker-compose ps
   ```

5. **Access the webapp:**
   ```bash
   # Open browser to http://localhost:3001
   # Login with any username to start chatting
   ```

### Configuration

Key environment variables in `.env`:

```bash
# Model Configuration
MODEL_NAME=Qwen/Qwen2.5-32B-Instruct
MODEL_DEVICE=cuda:0
MAX_CONTEXT_LENGTH=131072
USE_YARN=true

# STT Configuration
STT_MODEL=openai/whisper-large-v3
STT_DEVICE=cuda:0

# TTS Configuration
TTS_MODEL=facebook/fastspeech2-en-ljspeech
TTS_DEVICE=cuda:0

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Hugging Face Token
HUGGINGFACE_TOKEN=your_huggingface_token

# Database
POSTGRES_PASSWORD=changeme

# MinIO
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=changeme
```

## 🧪 Test Modes

June Agent supports two test configurations for different testing scenarios:

### 1. Full Mock Mode
**Purpose:** Test deployment and connectivity between services
- All services run in pass-through mode
- No real model inference
- Tests service communication and deployment
- Fast execution, no model dependencies

**Usage:**
```bash
# Set mock mode
source ./scripts/set_test_mode.sh mock
export $(grep -v '^#' .env | xargs)
docker compose up -d

# Run mock mode tests
python scripts/comprehensive_pipeline_test.py
```

### 2. STT/TTS Round-Trip Mode
**Purpose:** Test audio pipeline accuracy with real models via Gateway
- TTS and STT services use real models (espeak/Whisper)
- Gateway and Inference run in mock mode
- Tests full user flow: **Text → TTS → Audio → Gateway → Audio → STT → Text**
- **Two conversions tested:**
  1. **Input:** Text → TTS → Audio (simulating user sending audio)
  2. **Output:** Gateway Audio → STT → Text (validating Gateway response)
- Validates complete end-to-end pipeline as real users would experience it

**Usage:**
```bash
# Set round-trip mode
source ./scripts/set_test_mode.sh stt_tts_roundtrip
export $(grep -v '^#' .env | xargs)
docker compose up -d

# Generate Alice in Wonderland dataset (if needed)
python scripts/generate_alice_dataset.py

# Run Gateway round-trip tests
python scripts/test_round_trip_gateway.py
```

### Mode Configuration

The test mode is controlled by environment variables:
- `JUNE_TEST_MODE` - Overall test mode (`mock` or `stt_tts_roundtrip`)
- `STT_MODE` - STT service mode (`mock` or `real`)
- `TTS_MODE` - TTS service mode (`mock` or `real`)
- `GATEWAY_MODE` - Gateway service mode (`mock` or `real`)
- `INFERENCE_MODE` - Inference service mode (`mock` or `real`)

**Quick Mode Switch:**
```bash
# Use the mode switcher script
./scripts/set_test_mode.sh mock              # Full mock
./scripts/set_test_mode.sh stt_tts_roundtrip # STT/TTS round-trip

# Check current configuration
python scripts/test_pipeline_modes.py --show-config

# Run tests for specific mode
python scripts/test_pipeline_modes.py --mode mock
python scripts/test_pipeline_modes.py --mode stt_tts_roundtrip
python scripts/test_pipeline_modes.py --mode both  # Test both
```

## 🔧 Service Details

### Gateway Service (Port 8000)

**Features:**
- FastAPI REST API with WebSocket support
- JWT authentication and rate limiting
- Request routing to backend services
- Prometheus metrics collection

**Endpoints:**
- `GET /health` - Health check
- `GET /status` - Service status
- `GET /metrics` - Prometheus metrics
- `POST /auth/token` - Create JWT token
- `POST /chat` - REST API chat
- `WebSocket /ws/{user_id}` - Real-time communication

### Inference API Service (Port 50051)

**Features:**
- gRPC server for LLM orchestration
- Qwen2.5-32B-Instruct with Yarn context expansion (128k tokens)
- RAG integration with pgvector
- Tool invocation capabilities
- Streaming and one-shot generation

**gRPC Methods:**
- `GenerateStream` - Streaming text generation
- `Generate` - One-shot text generation
- `ChatStream` - Streaming chat with conversation history
- `Chat` - One-shot chat
- `Embed` - Generate embeddings
- `HealthCheck` - Health check

### STT Service (Port 50052)

**Features:**
- Whisper-based speech recognition
- Voice Activity Detection (VAD)
- Real-time streaming and batch processing
- Multiple audio format support

**gRPC Methods:**
- `RecognizeStream` - Streaming speech recognition
- `Recognize` - One-shot speech recognition
- `HealthCheck` - Health check

### TTS Service (Port 50053)

**Features:**
- FastSpeech2/HiFi-GAN text-to-speech
- Multiple voice support
- Prosody control (speed, pitch, energy)
- Streaming audio output

**gRPC Methods:**
- `SynthesizeStream` - Streaming TTS synthesis
- `Synthesize` - One-shot TTS synthesis
- `HealthCheck` - Health check

### Webapp Service (Port 3001)

**Features:**
- React-based Telegram-like chat interface
- Real-time WebSocket communication
- Voice message recording and playback
- Text-to-speech conversion
- Authentication and user management

**Interface:**
- Modern, responsive design
- Voice recording with visual feedback
- Message history and timestamps
- Audio playback controls
- Typing indicators

## 🧪 Testing

### Running Tests

Each service has comprehensive test suites:

```bash
# Gateway service tests
cd services/gateway
python -m pytest tests/ -v

# Inference API tests
cd services/inference-api
python -m pytest tests/ -v

# STT service tests
cd services/stt
python -m pytest tests/ -v

# TTS service tests
cd services/tts
python -m pytest tests/ -v

# Integration tests
cd tests/integration
python -m pytest test_system_integration.py -v
```

### Test Coverage

Each service includes:
- Unit tests for all components
- Integration tests for service interactions
- Mock tests for external dependencies
- Performance tests for concurrent requests
- Error handling tests

## 📊 Monitoring

### Metrics

Prometheus metrics are available at:
- Gateway: `http://localhost:8000/metrics`
- Inference API: `http://localhost:8001/metrics`
- STT: `http://localhost:8002/metrics`
- TTS: `http://localhost:8003/metrics`

### Dashboards

Grafana dashboards available at `http://localhost:3000`
- Default credentials: admin/admin

### Logs

Loki log aggregation available at `http://localhost:3100`

### Tracing

Jaeger tracing UI available at `http://localhost:16686`

## 🔌 API Usage

### REST API Example

```python
import requests
import json

# Create authentication token
response = requests.post("http://localhost:8000/auth/token", 
                        params={"user_id": "test_user"})
token = response.json()["access_token"]

# Send chat message
headers = {"Authorization": f"Bearer {token}"}
response = requests.post("http://localhost:8000/chat",
                        json={"type": "text", "text": "Hello, June!"},
                        headers=headers)
print(response.json())
```

### WebSocket Example

```python
import asyncio
import websockets
import json

async def chat_with_june():
    uri = "ws://localhost:8000/ws/test_user"
    async with websockets.connect(uri) as websocket:
        # Send text message
        await websocket.send(json.dumps({
            "type": "text",
            "text": "Hello, June!"
        }))
        
        # Receive response
        response = await websocket.recv()
        data = json.loads(response)
        print(f"Response: {data['text']}")

asyncio.run(chat_with_june())
```

### gRPC Example

```python
import grpc
from proto import llm_pb2, llm_pb2_grpc

# Connect to Inference API
channel = grpc.insecure_channel('localhost:50051')
stub = llm_pb2_grpc.LLMInferenceStub(channel)

# Generate text
request = llm_pb2.GenerationRequest(
    prompt="Write a short story about a robot.",
    params=llm_pb2.GenerationParameters(
        max_tokens=100,
        temperature=0.8
    )
)

response = stub.Generate(request)
print(f"Generated: {response.text}")
```

## 🐳 Docker Deployment

### Individual Services

Each service can be built and run independently:

```bash
# Build gateway service
cd services/gateway
docker build -t june-gateway .

# Run gateway service
docker run -p 8000:8000 june-gateway
```

### Full Stack

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## 🔧 Development

### Project Structure

```
june/
├── proto/                    # gRPC protobuf definitions
├── services/                 # Microservices
│   ├── gateway/             # Gateway service
│   ├── inference-api/       # Inference API service
│   ├── stt/                 # STT service
│   └── tts/                 # TTS service
├── shared/                   # Shared utilities and configuration
├── config/                   # Configuration files
├── tests/                    # Integration tests
├── docker-compose.yml        # Service orchestration
├── .env.example             # Environment template
└── pyproject.toml           # Python dependencies
```

### Adding New Services

1. Create service directory in `services/`
2. Add protobuf definitions in `proto/`
3. Implement service with gRPC server
4. Add comprehensive test suite
5. Create Dockerfile
6. Update docker-compose.yml
7. Add health checks and metrics

### Code Quality

The project uses:
- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking
- **pytest** for testing

Run quality checks:
```bash
poetry run black .
poetry run isort .
poetry run flake8
poetry run mypy
poetry run pytest
```

## 🚀 Performance Optimization

### GPU Optimization for DGX Spark

The system is optimized for single GPU deployment:

- **CUDA MPS**: Enables concurrent GPU usage across services
- **Model Quantization**: 4-bit quantization for memory efficiency
- **Context Expansion**: Yarn for 128k token context window
- **Streaming**: Real-time audio and text processing

### Memory Management

- **Paged KV Cache**: Efficient memory usage for LLM
- **Model Sharing**: Single GPU shared across all services
- **Audio Buffering**: Circular buffers for streaming audio

## 🔒 Security

- **JWT Authentication**: Secure token-based authentication
- **Rate Limiting**: Prevents abuse and ensures fair usage
- **Input Validation**: Comprehensive input sanitization
- **Network Security**: Internal service communication over gRPC

## 📈 Scaling

### Horizontal Scaling

- **Stateless Services**: All services are stateless and can be scaled horizontally
- **Load Balancing**: Gateway can be load balanced
- **Database Sharding**: PostgreSQL can be sharded for large datasets

### Vertical Scaling

- **GPU Memory**: Increase GPU memory for larger models
- **CPU Cores**: Add more CPU cores for concurrent processing
- **Storage**: Scale MinIO for larger audio/text storage

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the documentation
- Review the test suites for usage examples

## 🔄 Roadmap

- [ ] Multi-language support
- [ ] Advanced tool integration
- [ ] Custom voice training
- [ ] Real-time translation
- [ ] Multi-modal input (images, video)
- [ ] Kubernetes deployment
- [ ] Advanced RAG capabilities
- [ ] Fine-tuning interface