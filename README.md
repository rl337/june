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

## 📋 Current Tasks

See `TODO.md` for detailed implementation tasks and current priorities.

**Current Focus:** Telegram voice-to-text-to-voice service integration

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

## 🤖 Telegram Bot Setup

June Agent includes a Telegram bot service that enables voice-to-text-to-voice interactions. Users can send voice messages, which are transcribed, processed by the LLM, and returned as voice responses.

### Getting Started

#### 1. Create a Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command and follow the prompts to create your bot
3. Copy the bot token provided by BotFather (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
4. Save the token securely - you'll need it for configuration

#### 2. Configure Environment Variables

Add the following to your `.env` file:

```bash
# Telegram Bot Configuration (Required)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Service URLs (Optional - defaults shown)
STT_URL=grpc://stt:50052          # STT service gRPC endpoint
TTS_URL=grpc://tts:50053          # TTS service gRPC endpoint
LLM_URL=grpc://inference-api:50051 # Inference API gRPC endpoint

# Webhook Configuration (Optional - for production)
TELEGRAM_USE_WEBHOOK=false        # Set to 'true' for webhook mode
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook  # Full webhook URL
TELEGRAM_WEBHOOK_PORT=8443        # Port for webhook server

# File Size Limits (Optional)
TELEGRAM_MAX_FILE_SIZE=20971520   # Maximum voice file size in bytes (default: 20MB)
```

#### 3. Add Telegram Service to Docker Compose

Add the following service to your `docker-compose.yml`:

```yaml
  # Telegram Bot Service
  telegram:
    build:
      context: .
      dockerfile: ./services/telegram/Dockerfile
    container_name: june-telegram
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - STT_URL=${STT_URL:-grpc://stt:50052}
      - TTS_URL=${TTS_URL:-grpc://tts:50053}
      - LLM_URL=${LLM_URL:-grpc://inference-api:50051}
      - TELEGRAM_USE_WEBHOOK=${TELEGRAM_USE_WEBHOOK:-false}
      - TELEGRAM_WEBHOOK_URL=${TELEGRAM_WEBHOOK_URL}
      - TELEGRAM_WEBHOOK_PORT=${TELEGRAM_WEBHOOK_PORT:-8443}
      - TELEGRAM_MAX_FILE_SIZE=${TELEGRAM_MAX_FILE_SIZE:-20971520}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    depends_on:
      - stt
      - tts
      - inference-api
    networks:
      - june_network
    healthcheck:
      test: ["CMD", "pgrep", "-f", "python.*main.py"]
      interval: 30s
      timeout: 10s
      start_period: 30s
      retries: 3
```

#### 4. Start the Service

```bash
# Start all services including Telegram bot
docker-compose up -d

# Check Telegram service status
docker-compose logs -f telegram

# Verify bot is running
docker-compose ps telegram
```

### Usage

#### Bot Commands

- `/start` - Initialize the bot and get welcome message
- `/help` - Display help information and usage instructions
- `/status` - Check service health status (STT, TTS, LLM)

#### Sending Voice Messages

1. Open your Telegram bot conversation
2. Tap the microphone icon (🎤) to record a voice message
3. Send the voice message
4. The bot will:
   - Show "🔄 Processing your voice message..."
   - Transcribe your voice using STT
   - Process the text through the LLM
   - Convert the response to speech using TTS
   - Send back a voice response

#### Voice Message Limits

- **Maximum duration**: ~60 seconds
- **Maximum file size**: 20 MB (configurable via `TELEGRAM_MAX_FILE_SIZE`)
- **Supported formats**: OGG/OPUS (Telegram's native format)

### Running Modes

#### Development Mode (Polling)

For local development, the bot uses polling mode (default):

```bash
# Ensure TELEGRAM_USE_WEBHOOK is not set or set to false
TELEGRAM_USE_WEBHOOK=false

# Start the service
docker-compose up -d telegram
```

The bot will continuously poll Telegram's servers for updates.

#### Production Mode (Webhook)

For production deployments, use webhook mode for better performance and reliability:

```bash
# Configure webhook
TELEGRAM_USE_WEBHOOK=true
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook
TELEGRAM_WEBHOOK_PORT=8443

# Ensure your server has:
# 1. Valid SSL certificate (HTTPS required)
# 2. Port 8443 accessible from internet
# 3. Firewall rules allowing Telegram IP ranges

# Start the service
docker-compose up -d telegram
```

**Webhook Setup Requirements:**
- Valid SSL/TLS certificate (Telegram requires HTTPS)
- Publicly accessible domain/IP
- Port forwarding or load balancer configured
- Firewall allows connections from Telegram servers

### Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ Yes | - | Bot token from BotFather |
| `STT_URL` | No | `grpc://stt:50052` | STT service gRPC endpoint |
| `TTS_URL` | No | `grpc://tts:50053` | TTS service gRPC endpoint |
| `LLM_URL` | No | `grpc://inference-api:50051` | Inference API gRPC endpoint |
| `TELEGRAM_USE_WEBHOOK` | No | `false` | Enable webhook mode |
| `TELEGRAM_WEBHOOK_URL` | No* | - | Webhook URL (required if `TELEGRAM_USE_WEBHOOK=true`) |
| `TELEGRAM_WEBHOOK_PORT` | No | `8443` | Webhook server port |
| `TELEGRAM_MAX_FILE_SIZE` | No | `20971520` | Max voice file size in bytes (20MB) |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

\* Required when `TELEGRAM_USE_WEBHOOK=true`

### Troubleshooting

#### Bot Not Responding

1. **Check bot token:**
   ```bash
   # Verify token is set
   docker-compose exec telegram env | grep TELEGRAM_BOT_TOKEN
   
   # Test token validity (run locally)
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
   ```

2. **Check service logs:**
   ```bash
   docker-compose logs -f telegram
   ```

3. **Verify dependencies are running:**
   ```bash
   docker-compose ps stt tts inference-api
   ```

#### Voice Messages Not Processing

1. **Check audio file size:**
   - Ensure file is under 20MB (or your configured limit)
   - Telegram has a ~1 minute duration limit

2. **Check STT service:**
   ```bash
   # Test STT service connectivity
   docker-compose exec telegram ping -c 3 stt
   
   # Check STT logs
   docker-compose logs stt
   ```

3. **Check audio format:**
   - Bot expects OGG/OPUS format from Telegram
   - Conversion to WAV/PCM is handled automatically

#### Webhook Issues

1. **SSL Certificate:**
   - Ensure valid HTTPS certificate (Let's Encrypt recommended)
   - Certificate must be trusted by Telegram servers

2. **Webhook URL:**
   ```bash
   # Verify webhook is set (replace YOUR_TOKEN)
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo"
   
   # Set webhook manually if needed
   curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://your-domain.com/webhook"}'
   ```

3. **Firewall:**
   - Allow inbound connections on port 8443
   - Telegram IP ranges: https://core.telegram.org/bots/webhooks

#### Service Connection Errors

1. **Check network connectivity:**
   ```bash
   # Test internal service connections
   docker-compose exec telegram ping -c 3 stt
   docker-compose exec telegram ping -c 3 tts
   docker-compose exec telegram ping -c 3 inference-api
   ```

2. **Verify gRPC endpoints:**
   - Ensure services are running: `docker-compose ps`
   - Check service ports are accessible within Docker network

3. **Check service health:**
   ```bash
   # Test STT health
   docker-compose exec stt grpc_health_probe -addr=:50052
   
   # Test TTS health  
   docker-compose exec tts grpc_health_probe -addr=:50053
   ```

#### Common Error Messages

- **"TELEGRAM_BOT_TOKEN environment variable is required"**
  - Solution: Set `TELEGRAM_BOT_TOKEN` in `.env` file

- **"Voice message too large"**
  - Solution: Send shorter voice messages or increase `TELEGRAM_MAX_FILE_SIZE`

- **"Transcription failed"**
  - Solution: Check STT service is running and accessible
  - Verify audio format is valid

- **"Error processing audio"**
  - Solution: Check audio format, file integrity, and service connectivity

### Development

#### Running Locally (Outside Docker)

```bash
# Navigate to telegram service
cd services/telegram

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_BOT_TOKEN=your_token_here
export STT_URL=grpc://localhost:50052
export TTS_URL=grpc://localhost:50053
export LLM_URL=grpc://localhost:50051

# Run the bot
python main.py
```

#### Testing

```bash
# Run unit tests
cd services/telegram
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

### Architecture

The Telegram bot service acts as an integration layer:

```
User → Telegram (Voice Message)
         ↓
   Telegram Bot Service
         ↓
   [Download OGG] → [Convert to WAV] → [STT Service] → Transcript
         ↓
   [LLM Service] → Response Text
         ↓
   [TTS Service] → Audio (PCM/WAV)
         ↓
   [Convert to OGG] → [Upload to Telegram] → User receives Voice Response
```

**Service Dependencies:**
- STT Service (Speech-to-Text) - transcribes voice messages
- TTS Service (Text-to-Speech) - converts responses to audio
- Inference API - processes text through LLM

**Key Features:**
- Automatic audio format conversion (OGG ↔ WAV/PCM)
- Real-time status updates for users
- Error handling and validation
- Support for both polling and webhook modes

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

## 🏆 Accomplishments

### Architecture & Modularity
- ✅ **Modular Package Architecture**: Created independently installable `inference-core` and `june-grpc-api` packages
- ✅ **Docker-First Development**: All tools and services run in containers for consistency and reproducibility
- ✅ **Base Docker Image**: Shared `june-base` image with common dependencies, reducing build times and image sizes
- ✅ **gRPC Shim Layer**: Object-oriented API wrapper around generated protobuf code for better maintainability
- ✅ **Strategy Pattern**: Abstracted inference logic (STT, TTS, LLM) into testable Strategy classes

### Testing Infrastructure
- ✅ **Comprehensive Test Suite**: 1000+ diverse test cases for TTS/STT validation (short, medium, long phrases)
- ✅ **Concurrent Test Execution**: Parallel test execution (10 concurrent) reducing test time by 5-10x
- ✅ **100% Pass Rate Target**: Rigorous validation ensuring TTS/STT reliability for E2E testing
- ✅ **Round-Trip Testing**: Full audio-to-text-to-audio pipeline validation through Gateway
- ✅ **Unit Test Coverage**: Comprehensive unit tests with mocks for all inference-core components

### Audio Processing Improvements
- ✅ **TTS/STT Accuracy**: Achieved 91% pass rate (improved from 36%) through:
  - Whisper model upgrade (tiny.en → base.en)
  - Optimized espeak TTS parameters (speed, amplitude, voice clarity)
  - Better audio resampling with scipy
  - Enhanced text normalization
- ✅ **Single Word Recognition**: Improved single-word TTS with optimized espeak parameters
- ✅ **Audio Format Handling**: Robust PCM to WAV conversion for STT compatibility

### Development Experience
- ✅ **Command-Line Tools**: Unified CLI framework with Command base class for all tools
- ✅ **Automated Build Scripts**: Package build automation for wheels and Docker images
- ✅ **Test Orchestration**: `run_all_checks.sh` script for automated testing across all packages
- ✅ **Validation Scripts**: Service validation scripts for quick health checks

## 🎯 Design Decisions

### Package Structure
- **Separate Packages**: `inference-core` and `june-grpc-api` as independent pip-installable packages
- **Shim Layer**: Object-oriented wrapper around generated gRPC code to abstract protobuf changes
- **Adapter Pattern**: Abstracted external dependencies (Whisper) behind interfaces for testability

### Docker Architecture
- **Base Image Pattern**: All services inherit from `june-base` for common dependencies
- **Service-Specific Images**: Minimal Dockerfiles that inherit from base
- **Package Dockerfiles**: Each package has its own Dockerfile for wheel building

### Testing Strategy
- **Tiered Testing**: Unit tests → Integration tests → E2E validation tests
- **Concurrent Execution**: Parallel test runs for efficiency
- **Validation Suite**: Comprehensive TTS/STT validation to ensure test infrastructure reliability
- **Mock Strategy**: Extensive use of mocks for external dependencies

### Model Management
- **Strict Cache Policy**: All models downloaded via authorized script, no runtime downloads
- **Centralized Cache**: `/home/rlee/models` as single source of truth
- **Local-Only Loading**: Services use `local_files_only=True` for security and reliability

### Service Communication
- **gRPC for Internal**: Service-to-service communication via gRPC for performance
- **REST/WebSocket for External**: Gateway provides HTTP/WebSocket APIs for clients
- **NATS for Events**: Pub/sub messaging for event-driven architecture

## 🔄 Roadmap

- [ ] Multi-language support
- [ ] Advanced tool integration
- [ ] Custom voice training
- [ ] Real-time translation
- [ ] Multi-modal input (images, video)
- [ ] Kubernetes deployment
- [ ] Advanced RAG capabilities
- [ ] Fine-tuning interface
- [ ] **Telegram Bot Integration**: Voice-to-text-to-voice service (see `TODO.md`)