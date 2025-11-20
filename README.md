# June - Voice-to-Voice AI Agent

June is a simplified voice-to-voice AI agent system that processes voice messages through speech-to-text, LLM, and text-to-speech pipelines. It supports both **Telegram** and **Discord** platforms.

## 🏗️ Architecture Overview

June uses a minimal microservices architecture with the following essential services:

### Core Services

- **Telegram Service** - Receives voice messages from Telegram, orchestrates the pipeline
- **Discord Service** - Receives voice messages from Discord, orchestrates the pipeline
- **STT Service** - Speech-to-text conversion using Whisper
- **TTS Service** - Text-to-speech conversion using FastSpeech2/espeak
- **TensorRT-LLM** - LLM processing using Qwen3 (via Triton Inference Server in home_infra/shared-network) - default
- **NVIDIA NIM** - Pre-built LLM inference containers (nim-qwen3:8001) - alternative, no compilation needed

**Note:** Legacy `inference-api` service is deprecated and disabled by default. All services now use TensorRT-LLM (default) or NVIDIA NIM for optimized GPU inference.

### Architecture Flow

```
User → Telegram/Discord (Voice Message)
  ↓
Telegram/Discord Service
  ↓
STT Service → Transcript
  ↓
TensorRT-LLM (tensorrt-llm:8000) → Response Text
  ↓
TTS Service → Audio
  ↓
Telegram/Discord Service → User (Voice Response)
```

### Infrastructure

**No Infrastructure Required for MVP:**
- All services communicate via gRPC directly
- Conversation storage: In-memory (in telegram/discord services)
- Rate limiting: In-memory (in telegram/discord services)

**Optional Infrastructure (from home_infra):**
- **TensorRT-LLM** - LLM inference service (Triton Inference Server) - available in shared-network as `tensorrt-llm:8000` (default)
- **NVIDIA NIM** - Pre-built LLM inference containers - available in shared-network as `nim-qwen3:8001` (alternative)
- **Jaeger** - Distributed tracing (OpenTelemetry) - available in shared-network
- **Prometheus + Grafana** - Metrics collection and visualization - available in shared-network
- **nginx** - Reverse proxy (replaces removed gateway service) - available in shared-network

## 🚀 Quick Start

### Prerequisites

- NVIDIA GPU with CUDA support (for STT, TTS, and LLM)
- Docker and Docker Compose
- NVIDIA Container Toolkit
- Python 3.10+ (for local development)

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

3. **Configure Telegram/Discord bots:**
   - **Telegram:** Get bot token from [@BotFather](https://t.me/botfather)
   - **Discord:** Create bot application at https://discord.com/developers/applications

4. **Start the services:**
   ```bash
   docker compose up -d
   ```

5. **Verify services are running:**
   ```bash
   docker compose ps
   ```

### Configuration

Key environment variables in `.env`:

```bash
# Model Configuration
MODEL_NAME=Qwen/Qwen3-30B-A3B-Thinking-2507
MODEL_DEVICE=cuda:0
MAX_CONTEXT_LENGTH=131072

# STT Configuration
STT_MODEL=openai/whisper-large-v3
STT_DEVICE=cuda:0

# TTS Configuration
TTS_MODEL=facebook/fastspeech2-en-ljspeech
TTS_DEVICE=cuda:0

# Telegram Bot (Required for Telegram service)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Discord Bot (Required for Discord service)
DISCORD_BOT_TOKEN=your_discord_bot_token

# Hugging Face Token
HUGGINGFACE_TOKEN=your_huggingface_token

# Tracing (Optional - connects to Jaeger in shared-network)
ENABLE_TRACING=true
JAEGER_ENDPOINT=http://common-jaeger:14268/api/traces
JAEGER_AGENT_HOST=common-jaeger
JAEGER_AGENT_PORT=6831
```

## 📊 Observability

### OpenTelemetry Tracing

All services support distributed tracing via OpenTelemetry:

- **Configuration:** Set `ENABLE_TRACING=true` in environment variables
- **Jaeger Endpoint:** `http://common-jaeger:14268/api/traces` (in shared-network)
- **View Traces:** Access Jaeger UI at `http://localhost:16686` (if Jaeger is running in shared-network)

**Tracing Features:**
- Full request flow: Telegram/Discord → STT → LLM → TTS → Telegram/Discord
- gRPC call tracing with automatic context propagation
- HTTP request tracing for health/metrics endpoints
- Voice processing operation tracing (download, enhancement, transcription, synthesis)

### Prometheus Metrics

All services expose Prometheus metrics:

- **Telegram Service:** `http://localhost:8080/metrics`
- **Discord Service:** `http://localhost:8081/metrics`
- **STT Service:** `http://localhost:8002/metrics`
- **TTS Service:** `http://localhost:8003/metrics`
- **Inference API:** `http://localhost:8001/metrics`

**Key Metrics:**
- `http_requests_total` - HTTP request counts (method, endpoint, status_code)
- `http_request_duration_seconds` - HTTP request latencies
- `grpc_requests_total` - gRPC request counts (service, method, status_code)
- `grpc_request_duration_seconds` - gRPC request latencies
- `voice_messages_processed_total` - Voice message processing counts (platform, status)
- `voice_processing_duration_seconds` - Voice processing durations
- `stt_transcription_duration_seconds` - STT transcription durations
- `tts_synthesis_duration_seconds` - TTS synthesis durations
- `llm_generation_duration_seconds` - LLM generation durations
- `errors_total` - Error counts (service, error_type)
- `service_health` - Service health status (1 = healthy, 0 = unhealthy)

**Grafana Dashboards:**
- Access Grafana at `http://localhost:3000` (if running in shared-network)
- Metrics are scraped by Prometheus (if configured in home_infra)

## 🤖 Telegram Bot Setup

### Getting Started

1. **Create a Telegram Bot:**
   - Open Telegram and search for [@BotFather](https://t.me/botfather)
   - Send `/newbot` and follow prompts
   - Copy the bot token

2. **Configure Environment:**
   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```

3. **Start the Service:**
   ```bash
   docker compose up -d telegram
   ```

4. **Use the Bot:**
   - Open your Telegram bot conversation
   - Send a voice message
   - Receive a voice response

### Bot Commands

- `/start` - Initialize the bot
- `/help` - Display help information
- `/status` - Check service health status
- `/language <code>` - Set language preference (e.g., `/language en`)

## 🧠 Qwen3 Model Setup

### Overview

June uses Qwen3-30B-A3B-Thinking-2507 for LLM inference. The model runs in Docker containers with GPU support.

### Prerequisites

- **NVIDIA GPU** with 20GB+ VRAM (for Qwen3-30B with quantization)
- **NVIDIA Container Toolkit** installed and configured
- **Docker** with GPU support enabled

### Quick Setup

**Option A: Automated Workflow (Recommended)**
```bash
# Run the operational workflow script for guided setup
./scripts/setup_qwen3_operational.sh
```

This script orchestrates all setup steps: pre-flight checks, model download, service startup guidance, and verification.

**Option B: Manual Setup**

0. **Pre-flight environment check (recommended):**
   ```bash
   # Validate environment readiness before proceeding
   poetry run python -m essence check-environment
   ```
   **Note:** This checks Docker, GPU, NVIDIA Container Toolkit, HUGGINGFACE_TOKEN, and other prerequisites. Fix any issues before proceeding.

1. **Download the model (containerized):**
   ```bash
   # Download model in container (no host pollution)
   docker compose run --rm cli-tools \
     poetry run python -m essence download-models --model Qwen/Qwen3-30B-A3B-Thinking-2507
   ```

2. **Set up model repository structure:**
   ```bash
   # Create Triton model repository structure
   poetry run python -m essence setup-triton-repository --action create --model qwen3-30b
   ```

3. **Validate compilation prerequisites:**
   ```bash
   # Check GPU, repository structure, and get compilation guidance
   poetry run python -m essence compile-model --model qwen3-30b --check-prerequisites --generate-template
   ```

4. **Compile the model** (requires TensorRT-LLM build tools):
   - Use the compilation template from step 3
   - See `docs/guides/TENSORRT_LLM_SETUP.md` for detailed compilation instructions

5. **Start TensorRT-LLM service (in home_infra):**
   ```bash
   # TensorRT-LLM is set up in home_infra and connected via shared-network
   # June services will automatically connect to tensorrt-llm:8000
   # See REFACTOR_PLAN.md Phase 15 for TensorRT-LLM setup instructions
   ```

6. **Load the compiled model:**
   ```bash
   # Load model into TensorRT-LLM
   poetry run python -m essence manage-tensorrt-llm --action load --model qwen3-30b
   
   # Verify model is loaded
   poetry run python -m essence manage-tensorrt-llm --action status --model qwen3-30b
   ```

7. **Verify TensorRT-LLM is accessible:**
   ```bash
   # Check that TensorRT-LLM is running and ready
   poetry run python -m essence verify-tensorrt-llm
   
   # Legacy inference-api service available via: docker compose --profile legacy up -d inference-api
   ```

### Model Configuration

Key environment variables in `docker-compose.yml`:

```yaml
MODEL_NAME: "Qwen/Qwen3-30B-A3B-Thinking-2507"
MODEL_DEVICE: "cuda:0"
MAX_CONTEXT_LENGTH: 131072
QUANTIZATION_BITS: 8  # 8-bit quantization for memory efficiency
```

### GPU Requirements

- **Minimum**: 20GB VRAM (with 8-bit quantization)
- **Recommended**: 24GB+ VRAM for optimal performance
- **CPU Fallback**: **FORBIDDEN** for large models (30B+) - Service will fail to start if GPU is not available (see Critical Requirements in REFACTOR_PLAN.md)

### Container-First Approach

**All model operations happen in containers:**
- ✅ Model downloads in containers
- ✅ Model files in Docker volumes (`/home/rlee/models` → `/models` in container)
- ✅ All Python dependencies in container images
- ✅ No host system pollution

See `QWEN3_SETUP_PLAN.md` for detailed setup instructions.

## 🤖 Coding Agent

### Overview

The coding agent provides an interface for sending coding tasks to the Qwen3 model. It supports:
- **Tool calling** - File operations, code execution, directory listing
- **Multi-turn conversations** - Maintains context across interactions
- **Sandboxed execution** - All operations run in isolated containers

### Usage

**Option 1: CLI Command (Recommended for quick tasks)**

```bash
# Run a single task
poetry run python -m essence coding-agent --task "Write a function to calculate fibonacci numbers"

# Run in interactive mode
poetry run python -m essence coding-agent --interactive

# Specify workspace directory
poetry run python -m essence coding-agent --task "Your task here" --workspace-dir /path/to/workspace
```

**Option 2: Python API (For programmatic use)**

```python
from essence.agents.coding_agent import CodingAgent

# Initialize agent (defaults to TensorRT-LLM)
agent = CodingAgent(
    llm_url="tensorrt-llm:8000",  # Default: TensorRT-LLM in home_infra/shared-network
    model_name="Qwen/Qwen3-30B-A3B-Thinking-2507",
)

# Set workspace directory
agent.set_workspace("/workspace")

# Send a coding task
response = agent.send_coding_task(
    task_description="Write a function to calculate fibonacci numbers",
    context={"language": "python"},
)

# Process streaming response
for chunk in response:
    print(chunk, end="", flush=True)
```

### Available Tools

- `read_file` - Read file contents
- `write_file` - Write/create files
- `list_files` - List directory contents
- `read_directory` - Get detailed directory information
- `execute_command` - Run shell commands (sandboxed, 30s timeout)

### Benchmark Evaluation

Run coding benchmarks to evaluate the agent (requires TensorRT-LLM service running):

```bash
# Ensure TensorRT-LLM is running with model loaded
poetry run python -m essence manage-tensorrt-llm --action status --model qwen3-30b

# Run benchmarks (defaults to tensorrt-llm:8000)
poetry run python -m essence run-benchmarks --dataset humaneval --max-tasks 10

# Or run in container
docker compose run --rm cli-tools \
  poetry run python -m essence run-benchmarks --dataset humaneval --max-tasks 10

# Review results
poetry run python -m essence review-sandbox /tmp/benchmarks/results humaneval_0
```

**Note:** The `run-benchmarks` command defaults to `tensorrt-llm:8000` for TensorRT-LLM. Use `--llm-url inference-api:50051` for the legacy service.

See `docs/guides/QWEN3_BENCHMARK_EVALUATION.md` for detailed benchmark evaluation guide.

## 💬 Discord Bot Setup

### Getting Started

1. **Create a Discord Bot:**
   - Go to https://discord.com/developers/applications
   - Create a new application
   - Create a bot and copy the token
   - Invite bot to your server with appropriate permissions

2. **Configure Environment:**
   ```bash
   DISCORD_BOT_TOKEN=your_bot_token_here
   ```

3. **Start the Service:**
   ```bash
   docker compose up -d discord
   ```

4. **Use the Bot:**
   - Send a text message in Discord
   - Bot will respond with generated text

## 🏥 Health Checks

All services expose health check endpoints:

- **Telegram:** `http://localhost:8080/health`
- **Discord:** `http://localhost:8081/health`
- **STT:** `http://localhost:8002/health` (gRPC health check)
- **TTS:** `http://localhost:8003/health` (gRPC health check)
- **Inference API:** `http://localhost:8001/health` (gRPC health check)

## 🧪 Testing

### Run Tests

```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/path/to/test_file.py

# Run with coverage
poetry run pytest --cov=essence --cov-report=html
```

## 📁 Project Structure

```
june/
├── essence/                    # Core service implementations
│   ├── services/
│   │   ├── telegram/          # Telegram bot service code
│   │   ├── discord/           # Discord bot service code
│   │   └── shared_metrics.py  # Shared Prometheus metrics
│   ├── chat/                  # Shared chat/conversation utilities
│   └── commands/              # Command pattern implementations
├── services/                   # Service Dockerfiles and configuration
│   ├── telegram/              # Telegram Dockerfile
│   ├── discord/               # Discord Dockerfile
│   ├── stt/                   # STT Dockerfile
│   ├── tts/                   # TTS Dockerfile
│   └── inference-api/         # Legacy Inference API Dockerfile (disabled by default)
├── packages/                   # Shared packages
│   ├── inference-core/        # Core inference logic
│   └── june-grpc-api/         # gRPC API definitions
├── config/                     # Configuration files
├── docker-compose.yml          # Service orchestration
├── pyproject.toml              # Python dependencies
└── README.md                   # This file
```

## 🔧 Development

### Running Services Locally

Services use the `essence` command pattern:

```bash
# Run telegram service
poetry run python -m essence telegram-service

# Run discord service
poetry run python -m essence discord-service
```

### Code Organization

- **All Python code lives in `essence/`** - Services import from essence package
- **`services/` directories** - Contain only Dockerfiles and configuration
- **Shared code** - `essence/chat/` module used by both Telegram and Discord

### Building Services

```bash
# Build all services
docker compose build

# Build specific service
docker compose build telegram discord

# Rebuild without cache
docker compose build --no-cache telegram
```

## 📚 Documentation

- **[Refactoring Plan](REFACTOR_PLAN.md)** - Current refactoring status and TODO items
- **[Agent Development Guide](docs/guides/AGENTS.md)** - Guidelines for AI agents working on the project
- **[Documentation Index](docs/README.md)** - Complete documentation overview

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check service logs
docker compose logs <service-name>

# Check environment variables
docker compose exec <service-name> env

# Check service status
docker compose ps
```

### Health Check Fails

```bash
# Check health endpoint
curl http://localhost:8080/health  # Telegram
curl http://localhost:8081/health  # Discord

# Check service dependencies
docker compose ps stt tts  # TensorRT-LLM is in home_infra/shared-network
```

### Metrics Not Appearing

```bash
# Check metrics endpoint
curl http://localhost:8080/metrics  # Telegram
curl http://localhost:8081/metrics  # Discord

# Verify Prometheus is scraping (if configured)
curl http://localhost:9090/api/v1/targets
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
