# AGENTS.md - Development Guide for June Agent

This document provides essential information for AI agents working on the June Agent project, including architecture details, development practices, and environment specifics.

## 📋 Task Management

**IMPORTANT:** Always check and update `TODO.md` before and after working on tasks.

- **Before starting work:** Review `TODO.md` for current tasks and priorities
- **After completing work:** Update `TODO.md` to mark completed tasks and add new tasks as needed
- **Keep TODO.md current:** This is the single source of truth for what needs to be done

The `TODO.md` file contains:
- Detailed task breakdowns for major features
- Implementation phases and dependencies
- Technical specifications and requirements
- Testing and deployment checklists

See `TODO.md` for the current Telegram voice-to-text-to-voice service implementation plan.

## 🏗️ Architecture Overview

June Agent is a microservices-based interactive autonomous agent system optimized for NVIDIA DGX Spark with the following architecture:

### Core Services
- **Gateway Service** (Port 8000) - FastAPI + WebSocket ingress with auth, rate limiting
- **Inference API** (Port 50051) - gRPC coordinator for LLM orchestration with RAG
- **STT Service** (Port 50052) - Speech-to-Text with Whisper, VAD, gRPC streaming
- **TTS Service** (Port 50053) - Text-to-Speech with FastSpeech2/HiFi-GAN streaming
- **Webapp Service** (Port 3000) - React-based Telegram-like chat interface

### Supporting Infrastructure
- **PostgreSQL + pgvector** (Port 5432) - RAG storage and conversation memory
- **MinIO** (Ports 9000/9001) - S3-compatible object storage
- **NATS** (Port 4222) - Pub/sub messaging
- **Prometheus** (Port 9090) - Metrics collection
- **Grafana** (Port 3000) - Dashboards
- **Loki** (Port 3100) - Log aggregation
- **Jaeger** (Port 16686) - Distributed tracing

## 🤖 Current Model Configuration

**Primary LLM:** `Qwen/Qwen3-30B-A3B-Thinking-2507`
- **Context Window:** 128k tokens with Yarn expansion
- **Device:** CUDA GPU 0 with MPS sharing
- **Quantization:** 4-bit for memory efficiency
- **Capabilities:** Advanced reasoning, tool use, RAG integration

**STT Model:** `openai/whisper-large-v3`
- **Features:** Voice Activity Detection (VAD), real-time streaming
- **Languages:** Multi-language support

**TTS Model:** `facebook/fastspeech2-en-ljspeech`
- **Features:** Multiple voices, prosody control, streaming output

## 🚨 CRITICAL: Model Cache Management

**STRICT POLICY:** Models MUST be downloaded using the authorized download script ONLY.

### Model Cache Directory
- **Location:** `/home/rlee/models`
- **Structure:**
  - `/home/rlee/models/huggingface/` - Hugging Face models
  - `/home/rlee/models/transformers/` - Transformers cache
  - `/home/rlee/models/whisper/` - Whisper models
  - `/home/rlee/models/tts/` - TTS models

### Authorized Model Download
**ONLY** use `scripts/download_models.py` for model downloads:

```bash
# Download all required models
python scripts/download_models.py --all

# Download specific model
python scripts/download_models.py --model Qwen/Qwen3-30B-A3B-Thinking-2507

# Check cache status
python scripts/download_models.py --status

# List authorized models
python scripts/download_models.py --list
```

### Runtime Model Loading
- **Services MUST use local cache only**
- **NO internet downloads during runtime**
- **Set environment variables:**
  - `MODEL_CACHE_DIR=/home/rlee/models`
  - `HUGGINGFACE_CACHE_DIR=/home/rlee/models/huggingface`
  - `TRANSFORMERS_CACHE_DIR=/home/rlee/models/transformers`

### Security Rules
1. **NEVER** allow services to download models automatically
2. **ALWAYS** use `local_files_only=True` in model loading
3. **VERIFY** models exist in cache before starting services
4. **AUDIT** model cache directory regularly

## 📁 Data Directory Structure

**Primary Data Directory:** `/home/rlee/june_data`
- **PostgreSQL:** `/home/rlee/june_data/postgres/` - Database files
- **MinIO:** `/home/rlee/june_data/minio/` - Object storage
- **NATS:** `/home/rlee/june_data/nats/data/` - Message broker data
- **NATS JetStream:** `/home/rlee/june_data/nats/jets_stream/` - Stream storage
- **Prometheus:** `/home/rlee/june_data/prometheus/` - Metrics data
- **Grafana:** `/home/rlee/june_data/grafana/` - Dashboard configs
- **Loki:** `/home/rlee/june_data/loki/` - Log aggregation
- **Logs:** `/home/rlee/june_data/logs/` - Application logs
- **Uploads:** `/home/rlee/june_data/uploads/` - User uploads
- **Backups:** `/home/rlee/june_data/backups/` - System backups

**Environment Variable:** `JUNE_DATA_DIR=/home/rlee/june_data`

**Important:** This directory will grow very large over time and is excluded from git.

## 📦 Model Artifacts and Test Data Management

### Model Artifacts

All containers produce model artifacts (outputs, caches, generated content) that are mounted to the host filesystem:

**Model Artifacts Directory:** `/home/rlee/june_data/model_artifacts/`
- **STT:** `/home/rlee/june_data/model_artifacts/stt/`
- **TTS:** `/home/rlee/june_data/model_artifacts/tts/`
- **Inference API:** `/home/rlee/june_data/model_artifacts/inference-api/`
- **Gateway:** `/home/rlee/june_data/model_artifacts/gateway/`

These directories are mounted into containers at `/app/model_artifacts/` and persist across container restarts.

**Docker Compose Configuration:**
Each service has a volume mount:
```yaml
volumes:
  - ${JUNE_DATA_DIR:-/home/rlee/june_data}/model_artifacts/<service>:/app/model_artifacts
```

### Test Artifacts

Test runs create isolated test artifacts in timestamped directories:

**Test Data Directory:** `/home/rlee/june_test_data/`
- Individual test runs: `run_YYYYMMDD_HHMMSS/`
  - `input_audio/` - TTS-generated input audio
  - `output_audio/` - Gateway response audio
  - `transcripts/` - Text transcripts
  - `metadata/` - Test metadata JSON
  - `container_artifacts/` - Artifacts copied from containers after tests

### Test Orchestration

The `scripts/run_tests_with_artifacts.sh` script provides full test orchestration:

1. **Starts Fresh Containers** - Spins up a clean docker-compose environment
2. **Runs Tests** - Executes Gateway round-trip tests
3. **Collects Artifacts** - Copies model and test artifacts from containers
4. **Shuts Down** - Tears down containers after completion

**Usage:**
```bash
# Full test run with artifact collection
./scripts/run_tests_with_artifacts.sh

# With custom test limit
TEST_LIMIT=5 ./scripts/run_tests_with_artifacts.sh
```

**Important Notes:**
- Model artifacts persist in `june_data` and are shared across runs
- Test artifacts are isolated per test run
- All artifacts are excluded from git (see `.gitignore`)
- Artifacts can be very large - monitor disk space

## 🐳 Container Environment

### Docker-First Development Strategy
**CRITICAL:** All development tools and CLI utilities MUST run in Docker containers.

**Why Docker-First?**
- **Consistency:** Same environment across all developers
- **Dependency Isolation:** No conflicts with host system libraries
- **Reproducibility:** Guaranteed working environment
- **Security:** Isolated execution environment
- **Version Control:** Exact dependency versions locked

### CLI Tools Container
**Service:** `cli-tools` (Profile: `tools`)
- **Purpose:** All command-line tools and utilities
- **Base Image:** `python:3.11-slim`
- **Dependencies:** ML libraries, development tools, audio processing
- **Access:** `docker exec -it june-cli-tools bash`

**Available Tools:**
- Model download script (`scripts/download_models.py`)
- Development utilities (black, isort, flake8, mypy)
- Testing tools (pytest, pytest-cov)
- Audio processing (whisper, TTS, librosa)

### Shared gRPC API Package (june-grpc-api)
- Location: `dev/june/packages/june-grpc-api`
- Contents: Only proto IDLs in `proto/` (e.g., `asr.proto`, `tts.proto`, `llm.proto`).
- Build: Stubs are generated at image build time inside each service container; no generated code is checked in.
- Install flow (each service Dockerfile):
  - Generate stubs with `grpcio-tools` into `june_grpc_api/` inside the build context.
  - Build a wheel (`python -m build`) and `pip install` the resulting wheel.
- Imports in services:
  - `from june_grpc_api import asr_pb2, asr_pb2_grpc`
- Benefits: Single source of truth, no sys.path hacks, deterministic imports, faster builds, simpler CI.

### GPU Configuration
- **Single GPU Sharing:** All services share GPU 0 via CUDA MPS
- **Memory Management:** Paged KV cache, model quantization
- **CUDA Environment Variables:**
  - `CUDA_VISIBLE_DEVICES=0`
  - `CUDA_MPS_ENABLE_PER_CTX_SM_PARTITIONING=1`

### Docker Compose Services
All services are orchestrated via `docker-compose.yml` with:
- Health checks for all services
- Volume mounts for model cache and data persistence
- Network isolation with `june_network`
- Resource limits and GPU allocation

## 📁 Project Structure

```
dev/june/
├── proto/                    # gRPC protobuf definitions
│   ├── asr.proto            # Speech-to-Text service
│   ├── tts.proto            # Text-to-Speech service
│   └── llm.proto            # LLM inference service
├── services/                 # Microservices
│   ├── gateway/             # FastAPI + WebSocket gateway
│   ├── inference-api/       # LLM orchestration
│   ├── stt/                 # Speech-to-Text
│   ├── tts/                 # Text-to-Speech
│   └── webapp/              # React chat interface
├── shared/                   # Common utilities
│   ├── config.py            # Configuration management
│   ├── utils.py             # Shared utilities
│   └── __init__.py
├── config/                   # Configuration files
│   ├── postgres-init.sql     # Database schema
│   ├── prometheus.yml        # Metrics config
│   ├── loki-config.yml       # Logging config
│   └── grafana/              # Dashboard configs
├── tests/integration/        # System integration tests
├── docker-compose.yml        # Service orchestration
├── .env.example             # Environment template
├── pyproject.toml           # Python dependencies
├── README.md                # User documentation
└── AGENTS.md                # This file
```

## 🔧 Development Practices

### Code Quality Standards
- **Python:** Black formatting, isort imports, flake8 linting, mypy type checking
- **TypeScript/React:** ESLint, Prettier formatting
- **Testing:** Comprehensive test suites for all services
- **Documentation:** Inline docstrings, README updates

### Testing Strategy
Each service includes:
- **Unit Tests:** Individual component testing
- **Integration Tests:** Service interaction testing
- **Mock Tests:** External dependency isolation
- **Performance Tests:** Concurrent request handling
- **Error Handling Tests:** Failure scenario coverage

### Service Communication
- **Internal:** gRPC for service-to-service communication
- **External:** REST API and WebSocket for client access
- **Messaging:** NATS for pub/sub events
- **Storage:** PostgreSQL for structured data, MinIO for objects

## 🚀 Deployment Commands

### Start Full System
```bash
cd dev/june
cp .env.example .env
# Edit .env with your configuration
docker-compose up -d
```

### Individual Service Development
```bash
# Build specific service
cd services/gateway
docker build -t june-gateway .

# Run with live reload
docker run -p 8000:8000 -v $(pwd):/app june-gateway
```

### Health Checks
```bash
# Run comprehensive health checks
./run_checks.sh

# Check specific service
curl http://localhost:8000/health  # Gateway
curl http://localhost:50051/health # Inference API (gRPC)
```

## 🔍 Monitoring and Debugging

### Metrics Endpoints
- Gateway: `http://localhost:8000/metrics`
- Inference API: `http://localhost:8001/metrics`
- STT: `http://localhost:8002/metrics`
- TTS: `http://localhost:8003/metrics`

### Dashboards
- Grafana: `http://localhost:3000` (admin/admin)
- Prometheus: `http://localhost:9090`
- Jaeger: `http://localhost:16686`

### Logs
```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f gateway
docker-compose logs -f inference-api
```

## 🎙️ STT Service Updates and Validation

### Current STT Implementation
- Model: Whisper `tiny.en` (CPU by default; can be set via `STT_DEVICE`).
- Service: gRPC with unary `Recognize` and streaming `RecognizeStream` (IDL in `asr.proto`).
- Container: Installs `openai-whisper`, `ffmpeg`, and the shared `june-grpc-api` package during build.

### Validation Dataset
- Source: Small subset of LibriSpeech (OpenSLR test-clean; capped to ~20 pairs for fast checks).
- Download script (runs inside CLI tools): `services/cli-tools/scripts/download_librispeech_small.py`
- Index output: `${JUNE_DATA_DIR}/datasets/librispeech_small/index.json` with `{id, audio, text}` pairs.

### Validation Methods
- Solo STT validation: `services/cli-tools/scripts/test_stt_validate.py`
  - Reads FLAC, converts to WAV 16k PCM, calls STT gRPC, compares hypotheses.
  - Quick metric: prefix-3 word match counts (sanity check). Example result: 10/20 (~50%).
  - Extendable to WER/CER using `jiwer` if needed.

### How to Run
```
# Start CLI tools and STT only
docker compose --profile tools up -d cli-tools
docker compose up -d stt

# Download dataset and run validation (script orchestrates both steps)
./scripts/validate_stt.sh
```

### Notes
- All generated artifacts and datasets are stored under `${JUNE_DATA_DIR}` and excluded from git.
- The STT container no longer bind-mounts service code to avoid masking generated gRPC stubs.

## 🛠️ Common Development Tasks

### Using CLI Tools Container
**Start CLI Tools:**
```bash
# Start CLI tools container
docker-compose --profile tools up -d cli-tools

# Access CLI tools
docker exec -it june-cli-tools bash
```

**Model Management:**
```bash
# Download all models
docker exec -it june-cli-tools python scripts/download_models.py --all

# Download specific model
docker exec -it june-cli-tools python scripts/download_models.py --model Qwen/Qwen3-30B-A3B-Thinking-2507

# Check model status
docker exec -it june-cli-tools python scripts/download_models.py --status

# List authorized models
docker exec -it june-cli-tools python scripts/download_models.py --list
```

**Development Tools:**
```bash
# Code formatting
docker exec -it june-cli-tools black /app/scripts/
docker exec -it june-cli-tools isort /app/scripts/

# Linting
docker exec -it june-cli-tools flake8 /app/scripts/
docker exec -it june-cli-tools mypy /app/scripts/

# Testing
docker exec -it june-cli-tools pytest /app/scripts/
```

### Adding New CLI Tools
1. **Add dependencies** to `services/cli-tools/requirements-cli.txt`
2. **Create tool script** in `services/cli-tools/scripts/`
3. **Update Dockerfile** if system dependencies needed
4. **Test tool** in CLI container
5. **Update documentation** with usage instructions

### Adding New Features
1. **Update protobuf schemas** if needed
2. **Implement service logic** with comprehensive tests
3. **Update docker-compose.yml** for new services
4. **Add health checks** and metrics
5. **Update documentation**

### Adding New Models
1. **Add to AUTHORIZED_MODELS** in `scripts/download_models.py`
2. **Update download script** with new model category
3. **Test model download** using the script
4. **Update service code** to use local cache only
5. **Verify no internet access** during runtime
6. **Update documentation** with new model info

### Debugging Issues
1. **Check service health** with `./run_checks.sh`
2. **Review logs** for error messages
3. **Verify GPU allocation** with `nvidia-smi`
4. **Test individual services** in isolation
5. **Check network connectivity** between services

### Performance Optimization
1. **Monitor GPU memory usage** with `nvidia-smi`
2. **Check Prometheus metrics** for bottlenecks
3. **Profile service performance** with timing logs
4. **Optimize model loading** and inference
5. **Scale services horizontally** if needed

## 🔐 Security Considerations

### Authentication
- JWT tokens for API access
- Rate limiting to prevent abuse
- Input validation and sanitization

### Network Security
- Internal service communication over gRPC
- External access through Gateway only
- CORS configuration for webapp

### Data Protection
- Environment variables for secrets
- Secure storage of audio/text data
- User session management

## 📊 Performance Characteristics

### Expected Performance
- **Text Generation:** ~50-100 tokens/second
- **Speech Recognition:** ~2-3x real-time
- **Text-to-Speech:** ~1-2x real-time
- **Memory Usage:** ~20-30GB GPU memory
- **Latency:** <500ms for simple requests

### Scaling Considerations
- **Horizontal:** Stateless services can be scaled
- **Vertical:** GPU memory limits model size
- **Database:** PostgreSQL can be sharded
- **Storage:** MinIO can be clustered

## 🎯 Future Development Areas

### Planned Features
- **Multi-language Support:** Language detection and translation
- **Advanced RAG:** Document ingestion and retrieval
- **Custom Voice Training:** User-specific voice models
- **Tool Integration:** External API connections
- **Fine-tuning Interface:** Model customization UI

### Architecture Improvements
- **Kubernetes Deployment:** Production orchestration
- **Service Mesh:** Advanced networking
- **Caching Layer:** Redis for performance
- **Load Balancing:** Multiple gateway instances

## 🚨 Troubleshooting Guide

### Common Issues

**GPU Memory Errors:**
- Check `nvidia-smi` for memory usage
- Reduce model quantization or context length
- Restart services to clear memory

**Service Connection Errors:**
- Verify docker-compose network configuration
- Check service health endpoints
- Review NATS connectivity

**Model Loading Failures:**
- Verify Hugging Face token
- Check internet connectivity
- Clear model cache if corrupted

**WebSocket Connection Issues:**
- Check Gateway service status
- Verify authentication tokens
- Review browser console for errors

### Recovery Procedures
1. **Full System Restart:** `docker-compose down && docker-compose up -d`
2. **Service-Specific Restart:** `docker-compose restart <service>`
3. **Data Reset:** Remove volumes and restart
4. **Model Cache Clear:** Remove `~/.cache/huggingface` volume

## 📝 Development Notes

### Current Limitations
- Single GPU deployment only
- Limited to English language models
- Basic tool integration
- No persistent user sessions

### Technical Debt
- WebSocket authentication needs improvement
- Error handling could be more granular
- Metrics collection needs expansion
- Test coverage could be higher

### Known Issues
- Occasional GPU memory fragmentation
- WebSocket reconnection handling
- Audio format compatibility
- Model loading race conditions

---

**Last Updated:** December 2024  
**Version:** 0.2.0  
**Maintainer:** June Agent Team
