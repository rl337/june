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

## 📚 Documentation

For comprehensive documentation, see the [Documentation Index](docs/README.md).

**Quick Links:**
- **[User Guide](docs/guides/USER_GUIDE.md)** - Getting started, webapp guide, Telegram bot guide, Gateway API guide
- **[Development Setup](docs/guides/DEVELOPMENT.md)** - Development environment setup, project structure, workflow, contributing guidelines
- **[Deployment Guide](docs/guides/DEPLOYMENT.md)** - Production deployment, cloud deployments, configuration, monitoring
- **[API Documentation](docs/API/)** - Complete API docs for all services
- **[Architecture Documentation](docs/architecture/ARCHITECTURE.md)** - System architecture, service architecture, design decisions
- **[Troubleshooting Guide](docs/guides/TROUBLESHOOTING.md)** - Common issues, debugging procedures, health checks
- **[Agent Development Guide](docs/guides/AGENTS.md)** - Guidelines for AI agents working on the project
- **[Agentic Capabilities](docs/architecture/AGENTIC_CAPABILITIES.md)** - Autonomous agent system documentation

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
MODEL_NAME=Qwen/Qwen3-30B-A3B-Thinking-2507  # HuggingFace model identifier
MODEL_DEVICE=cuda:0                            # Device to run model on (cuda:0, cpu, etc.)
MAX_CONTEXT_LENGTH=131072                      # Maximum context length in tokens
USE_YARN=true                                   # Enable YaRN for long context support
MODEL_TEMPERATURE=0.7                          # Default temperature for generation (0.0-2.0)
MODEL_MAX_TOKENS=2048                          # Default maximum tokens to generate
MODEL_TOP_P=0.9                                # Default top-p (nucleus) sampling parameter
MODEL_TOP_K=                                    # Optional: top-k sampling (leave empty to disable)
MODEL_REPETITION_PENALTY=                      # Optional: repetition penalty (leave empty to disable)

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

## 🚀 Production Deployment

This section provides comprehensive guidance for deploying June to production environments. Follow these guidelines to ensure a secure, scalable, and maintainable deployment.

### Production Deployment Checklist

Before deploying to production, ensure all items in this checklist are completed:

#### 1. SSL/TLS Configuration

**For External-Facing Services:**
- **SSL Certificate**: Valid SSL certificate for your domain (required for HTTPS endpoints)
  - Use Let's Encrypt for free certificates: `certbot certonly --standalone -d your-domain.com`
  - Or use certificates from a trusted CA
- **Certificate Location**: Store certificates securely (e.g., `/etc/ssl/certs/june/`)
- **Certificate Renewal**: Set up automatic renewal
  ```bash
  # Add to crontab for auto-renewal
  0 0 * * * certbot renew --quiet --deploy-hook "docker-compose restart gateway telegram"
  ```
- **TLS Configuration**: Configure reverse proxy (nginx/traefik) for TLS termination
- **Internal Services**: Use TLS for service-to-service communication in production

**For Telegram Webhook (if using):**
- Valid SSL certificate required (Telegram enforces HTTPS)
- Certificate must be trusted by Telegram servers
- Port 8443 must be accessible from internet

#### 2. Firewall Rules

**Inbound Rules:**
- **Gateway Service** (Port 8000): Allow from load balancer/reverse proxy only
- **Webapp** (Port 3001): Allow from load balancer/reverse proxy only
- **Telegram Webhook** (Port 8443): Allow from Telegram IP ranges
  - Telegram IP ranges: https://core.telegram.org/bots/webhooks#the-short-version
- **Monitoring** (Ports 9090, 3000, 3100, 16686): Restrict to internal network or VPN
- **Health Checks**: Allow health check endpoints from monitoring systems

**Outbound Rules:**
- Allow connections to external APIs (Telegram API, Hugging Face)
- Allow DNS resolution
- Allow package manager access (for updates)

**Network Security:**
- Use Docker networks to isolate services (`june_network`)
- Implement network policies to restrict inter-service communication
- Use VPN or private networks for service-to-service communication
- Block direct access to internal services from internet

#### 3. Environment Variables

Configure all production environment variables in `.env` or your secrets management system:

```bash
# Model Configuration
MODEL_NAME=Qwen/Qwen3-30B-A3B-Thinking-2507
MODEL_DEVICE=cuda:0
MAX_CONTEXT_LENGTH=131072
USE_YARN=true
MODEL_TEMPERATURE=0.7
MODEL_MAX_TOKENS=2048
MODEL_TOP_P=0.9
# Optional generation parameters (leave empty to use defaults):
# MODEL_TOP_K=
# MODEL_REPETITION_PENALTY=

# STT Configuration
STT_MODEL=openai/whisper-large-v3
STT_DEVICE=cuda:0

# TTS Configuration
TTS_MODEL=facebook/fastspeech2-en-ljspeech
TTS_DEVICE=cuda:0

# Telegram Bot Configuration (if using)
TELEGRAM_BOT_TOKEN=your_production_bot_token
TELEGRAM_USE_WEBHOOK=true
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook
TELEGRAM_WEBHOOK_PORT=8443
TELEGRAM_REQUEST_TIMEOUT=30.0
TELEGRAM_RATE_LIMIT_PER_MINUTE=10
TELEGRAM_RATE_LIMIT_PER_HOUR=100
TELEGRAM_RATE_LIMIT_PER_DAY=500

# Database
POSTGRES_PASSWORD=strong_random_password_here
POSTGRES_USER=june
POSTGRES_DB=june

# MinIO
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=strong_random_password_here

# Authentication
JWT_SECRET=strong_random_secret_here

# Hugging Face Token
HUGGINGFACE_TOKEN=your_huggingface_token

# gRPC Connection Pooling
GRPC_MAX_CONNECTIONS_PER_SERVICE=10
GRPC_KEEPALIVE_TIME_MS=30000
GRPC_KEEPALIVE_TIMEOUT_MS=5000

# Logging
LOG_LEVEL=INFO  # Use INFO for production, DEBUG for troubleshooting

# Data Directories
JUNE_DATA_DIR=/var/lib/june/data
MODEL_CACHE_DIR=/var/lib/june/models
```

**Secrets Management Best Practices:**
- Never commit secrets to version control
- Use environment variables or secrets manager (AWS Secrets Manager, HashiCorp Vault, Kubernetes Secrets)
- Rotate secrets regularly
- Use different secrets for each environment (dev, staging, production)

#### 4. Resource Limits

Configure resource limits in `docker-compose.yml` for each service:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # Maximum CPU usage
      memory: 4G       # Maximum memory usage
    reservations:
      cpus: '0.5'      # Reserved CPU
      memory: 1G       # Reserved memory
```

**Recommended Resource Limits:**
- **Gateway**: 2 CPU, 2GB RAM
- **Inference API**: 4 CPU, 8GB RAM (GPU required)
- **STT Service**: 2 CPU, 4GB RAM (GPU required)
- **TTS Service**: 2 CPU, 4GB RAM (GPU required)
- **Telegram Service**: 2 CPU, 2GB RAM
- **PostgreSQL**: 2 CPU, 4GB RAM
- **MinIO**: 1 CPU, 2GB RAM
- **NATS**: 1 CPU, 1GB RAM

Adjust based on your expected load and available resources. Monitor actual usage and adjust accordingly.

#### 5. Monitoring and Alerting Setup

June includes comprehensive monitoring infrastructure. Set up monitoring before going to production:

**Prometheus Metrics Collection:**
- Prometheus is configured to scrape metrics from all services
- Access Prometheus UI at `http://localhost:9090`
- Metrics are exposed at `/metrics` endpoint for each service:
  - Gateway: `http://gateway:8000/metrics`
  - Inference API: `http://inference-api:8001/metrics`
  - STT: `http://stt:8002/metrics`
  - TTS: `http://tts:8003/metrics`
  - Orchestrator: `http://orchestrator:8005/metrics`
  - TODO Service: `http://todo-mcp-service:8004/metrics`

**Grafana Dashboards:**
- Access Grafana at `http://localhost:3000` (default: admin/admin)
- Dashboards are automatically provisioned from `config/grafana/provisioning/dashboards/`
- Key dashboards:
  - Service health overview
  - Request metrics (counts, latencies, throughput)
  - Resource usage (CPU, memory, GPU)
  - Service-specific metrics (STT/TTS/LLM)

**Log Aggregation (Loki):**
- Loki aggregates logs from all services
- Access Loki at `http://localhost:3100`
- Configure log retention policies based on storage capacity
- Set up log rotation to prevent disk space issues

**Distributed Tracing (Jaeger):**
- Jaeger collects distributed traces across services
- Access Jaeger UI at `http://localhost:16686`
- Use traces to debug performance issues and understand request flow

**Alerting Configuration:**
Configure alerts for:
- **Service Downtime**: Alert when health checks fail
- **High Error Rates**: Alert when error rate exceeds threshold (e.g., >5%)
- **Resource Exhaustion**: Alert when CPU/memory usage >80%
- **GPU Utilization**: Alert when GPU usage is consistently low or high
- **Database Issues**: Alert on connection pool exhaustion, slow queries
- **Rate Limit Violations**: Alert on excessive rate limit hits
- **Disk Space**: Alert when disk usage >80%

**Example Prometheus Alert Rules:**
```yaml
groups:
  - name: june_alerts
    rules:
      - alert: ServiceDown
        expr: up{job="gateway"} == 0
        for: 5m
        annotations:
          summary: "Gateway service is down"
      
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"
```

#### 6. Logging and Troubleshooting Guide

**Log Levels:**
- **DEBUG**: Detailed information for debugging (development only)
- **INFO**: General informational messages (production default)
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error messages for failures

**Log Locations:**
- Container logs: `docker-compose logs -f <service-name>`
- Loki aggregated logs: `http://localhost:3100`
- Service-specific logs: Check `JUNE_DATA_DIR` for log files

**Structured Logging:**
All services use structured logging with:
- Timestamps
- Log levels
- Service names
- Request IDs (for tracing)
- Error context

**Troubleshooting Steps:**

1. **Check Service Health:**
   ```bash
   # Check all services
   docker-compose ps
   
   # Check specific service health
   curl http://localhost:8000/health  # Gateway
   curl http://localhost:8080/health  # Telegram
   curl http://localhost:8005/health  # Orchestrator
   ```

2. **Review Logs:**
   ```bash
   # View logs for specific service
   docker-compose logs -f gateway
   docker-compose logs -f inference-api
   docker-compose logs -f stt
   ```

3. **Check Metrics:**
   - Access Prometheus: `http://localhost:9090`
   - Query metrics: `rate(http_requests_total[5m])`
   - Check error rates: `rate(http_requests_total{status=~"5.."}[5m])`

4. **Check Resource Usage:**
   ```bash
   # Container resource usage
   docker stats
   
   # System resource usage
   docker-compose exec node-exporter curl http://localhost:9100/metrics
   ```

5. **Check Network Connectivity:**
   ```bash
   # Test internal service connections
   docker-compose exec gateway ping -c 3 inference-api
   docker-compose exec gateway ping -c 3 postgres
   ```

#### 7. Performance Tuning Recommendations

**Database Optimization:**
- **Connection Pooling**: Configure appropriate pool sizes
  ```python
  # PostgreSQL connection pool
  POSTGRES_POOL_SIZE=20
  POSTGRES_MAX_OVERFLOW=10
  ```
- **Query Optimization**: Add indexes for frequently queried columns
- **Vacuum and Analyze**: Schedule regular VACUUM and ANALYZE operations
- **Connection Limits**: Set appropriate `max_connections` in PostgreSQL

**gRPC Optimization:**
- **Connection Pooling**: Reuse connections across requests
  ```bash
  GRPC_MAX_CONNECTIONS_PER_SERVICE=20  # Increase for high load
  ```
- **Keepalive Settings**: Tune keepalive intervals
  ```bash
  GRPC_KEEPALIVE_TIME_MS=30000
  GRPC_KEEPALIVE_TIMEOUT_MS=5000
  ```
- **Request Timeouts**: Set appropriate timeouts for your use case
- **Streaming**: Use streaming for large responses to reduce memory usage

**GPU Optimization:**
- **CUDA MPS**: Enable Multi-Process Service for concurrent GPU usage
  ```bash
  CUDA_MPS_ENABLE_PER_CTX_SM_PARTITIONING=1
  ```
- **Model Quantization**: Use quantized models to reduce memory usage
- **Batch Processing**: Batch requests when possible to improve throughput
- **Context Management**: Optimize context length based on use case

**Caching:**
- **Response Caching**: Cache frequently requested responses
- **Model Caching**: Models are cached in `MODEL_CACHE_DIR`
- **Database Query Caching**: Use connection pooling and query caching

**Rate Limiting:**
- Tune rate limits based on actual usage patterns
- Monitor rate limit hits and adjust accordingly
- Use different limits for different user tiers

#### 8. Security Best Practices

**Secrets Management:**
- **Never Commit Secrets**: Use `.gitignore` to exclude `.env` files
- **Use Secrets Manager**: AWS Secrets Manager, HashiCorp Vault, Kubernetes Secrets
- **Rotate Secrets Regularly**: Set up rotation schedule for all secrets
- **Separate Environments**: Use different secrets for dev/staging/production
- **Access Control**: Limit access to secrets (principle of least privilege)

**Network Security:**
- **TLS/HTTPS**: Use TLS for all external communications
- **Internal Networks**: Use Docker networks to isolate services
- **Firewall Rules**: Restrict access to internal services
- **VPN Access**: Use VPN for administrative access
- **Network Policies**: Implement network policies (Kubernetes NetworkPolicies)

**Authentication and Authorization:**
- **JWT Secrets**: Use strong, random JWT secrets
- **Token Expiration**: Set appropriate token expiration times
- **Rate Limiting**: Implement rate limiting to prevent abuse
- **Input Validation**: Validate all user inputs
- **SQL Injection Prevention**: Use parameterized queries

**Container Security:**
- **Base Images**: Use official, regularly updated base images
- **Image Scanning**: Scan images for vulnerabilities
- **Non-Root Users**: Run containers as non-root users when possible
- **Resource Limits**: Set resource limits to prevent resource exhaustion attacks
- **Read-Only Filesystems**: Use read-only filesystems where possible

**Data Security:**
- **Encryption at Rest**: Encrypt sensitive data in databases and object storage
- **Encryption in Transit**: Use TLS for all network communications
- **Backup Encryption**: Encrypt backups
- **Data Retention**: Implement data retention policies
- **PII Handling**: Follow regulations for handling personally identifiable information

#### 9. Backup and Recovery Procedures

**Data Backup Strategy:**

1. **PostgreSQL Backups:**
   ```bash
   # Automated daily backup
   docker-compose exec postgres pg_dump -U june june > backup_$(date +%Y%m%d).sql
   
   # Restore from backup
   docker-compose exec -T postgres psql -U june june < backup_20240101.sql
   ```

2. **MinIO Backups:**
   ```bash
   # Backup MinIO data
   docker-compose exec minio mc mirror /data /backup/minio
   ```

3. **Configuration Backups:**
   - Backup `docker-compose.yml`
   - Backup `.env` files (securely)
   - Backup `config/` directory
   - Backup Grafana dashboards and Prometheus rules

4. **Model Cache Backups:**
   - Models are large; consider backing up model cache separately
   - Use incremental backups for model cache

**Backup Schedule:**
- **Database**: Daily full backups, hourly incremental backups
- **Object Storage**: Daily backups
- **Configuration**: Weekly backups
- **Model Cache**: Monthly backups (models change infrequently)

**Recovery Procedures:**

1. **Service Failure Recovery:**
   ```bash
   # Restart failed service
   docker-compose restart <service-name>
   
   # Check service health
   curl http://localhost:<port>/health
   ```

2. **Database Recovery:**
   ```bash
   # Stop services using database
   docker-compose stop gateway inference-api
   
   # Restore database
   docker-compose exec -T postgres psql -U june june < backup.sql
   
   # Restart services
   docker-compose start gateway inference-api
   ```

3. **Full System Recovery:**
   - Restore database from backup
   - Restore MinIO data
   - Restore configuration files
   - Restart all services
   - Verify system health

**Disaster Recovery Plan:**
- Document recovery procedures
- Test backup restoration regularly
- Maintain off-site backups
- Document recovery time objectives (RTO) and recovery point objectives (RPO)

#### 10. Scaling Guidelines

**Horizontal Scaling:**

All stateless services can be scaled horizontally:

```bash
# Scale Gateway service
docker-compose up -d --scale gateway=3

# Scale Telegram voice workers
docker-compose up -d --scale telegram-voice-worker=5

# Use load balancer for Gateway
# Configure nginx/traefik to load balance across multiple Gateway instances
```

**Stateless Services (can scale horizontally):**
- Gateway
- Telegram service
- Telegram voice workers
- Orchestrator
- TODO service

**Stateful Services (require special handling):**
- PostgreSQL: Use read replicas for read scaling, connection pooling
- MinIO: Use MinIO distributed mode for horizontal scaling
- NATS: Use NATS clustering for horizontal scaling

**Vertical Scaling:**

Increase resource limits for services that need more resources:

```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'      # Increase from 2.0
      memory: 8G       # Increase from 4G
```

**GPU Services Scaling:**
- Inference API, STT, TTS require GPU access
- Use CUDA MPS to share GPU across services
- For multiple GPUs, distribute services across GPUs
- Consider GPU memory requirements when scaling

**Load Balancing:**
- Use nginx, traefik, or cloud load balancer for Gateway
- Configure health checks for load balancer
- Use sticky sessions if needed (not required for stateless services)

**Auto-Scaling:**
- Monitor metrics (CPU, memory, request rate)
- Set up auto-scaling based on metrics
- Use Kubernetes HPA or similar for automatic scaling

#### 11. Health Check Endpoints Documentation

All services expose health check endpoints for monitoring:

**HTTP Health Checks:**

| Service | Endpoint | Port | Description |
|---------|----------|------|-------------|
| Gateway | `GET /health` | 8000 | Checks NATS and gRPC services |
| Telegram | `GET /health` | 8080 | Checks STT, TTS, LLM services |
| Orchestrator | `GET /health` | 8005 | Checks agent status |
| TODO Service | `GET /health` | 8004 | Basic health check |
| Webapp | Health check via Docker | 3001 | Container health check |

**gRPC Health Checks:**

| Service | Method | Port | Description |
|---------|--------|------|-------------|
| Inference API | `HealthCheck` | 50051 | Checks model, database, MinIO, NATS |
| STT | `HealthCheck` | 50052 | Checks model and NATS |
| TTS | `HealthCheck` | 50053 | Checks model and NATS |

**Infrastructure Health Checks:**

| Service | Endpoint | Port | Description |
|---------|----------|------|-------------|
| PostgreSQL | `pg_isready` | 5432 | Database readiness |
| MinIO | `GET /minio/health/live` | 9000 | Object storage health |
| NATS | `GET /healthz` | 8222 | Messaging health |
| Prometheus | `GET /-/healthy` | 9090 | Metrics collection health |
| Grafana | `GET /api/health` | 3000 | Dashboard health |
| Loki | `GET /ready` | 3100 | Log aggregation health |

**Health Check Usage:**

```bash
# Check Gateway health
curl http://localhost:8000/health

# Check Telegram health
curl http://localhost:8080/health

# Check gRPC service health (requires grpc_health_probe)
docker-compose exec inference-api grpc_health_probe -addr=:50051

# Check all services
docker-compose ps
```

**Health Check Response Format:**

```json
{
  "status": "healthy",
  "checks": {
    "nats": true,
    "grpc_services": true
  }
}
```

#### 12. Production Environment Variable Reference

Complete reference of all production environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| **Model Configuration** |
| `MODEL_NAME` | No | `Qwen/Qwen3-30B-A3B-Thinking-2507` | HuggingFace model identifier |
| `MODEL_DEVICE` | No | `cuda:0` | GPU device for LLM (cuda:0, cpu, etc.) |
| `MAX_CONTEXT_LENGTH` | No | `131072` | Maximum context length in tokens |
| `USE_YARN` | No | `true` | Enable YaRN for long context support |
| `MODEL_TEMPERATURE` | No | `0.7` | Default temperature for generation (0.0-2.0) |
| `MODEL_MAX_TOKENS` | No | `2048` | Default maximum tokens to generate |
| `MODEL_TOP_P` | No | `0.9` | Default top-p (nucleus) sampling parameter |
| `MODEL_TOP_K` | No | - | Optional: top-k sampling (leave empty to disable) |
| `MODEL_REPETITION_PENALTY` | No | - | Optional: repetition penalty (leave empty to disable) |
| **STT Configuration** |
| `STT_MODEL` | No | `openai/whisper-large-v3` | STT model name |
| `STT_DEVICE` | No | `cuda:0` | GPU device for STT |
| **TTS Configuration** |
| `TTS_MODEL` | No | `facebook/fastspeech2-en-ljspeech` | TTS model name |
| `TTS_DEVICE` | No | `cuda:0` | GPU device for TTS |
| **Telegram Bot** |
| `TELEGRAM_BOT_TOKEN` | Yes* | - | Bot token from BotFather |
| `TELEGRAM_USE_WEBHOOK` | No | `false` | Enable webhook mode |
| `TELEGRAM_WEBHOOK_URL` | No** | - | Webhook URL |
| `TELEGRAM_WEBHOOK_PORT` | No | `8443` | Webhook server port |
| `TELEGRAM_REQUEST_TIMEOUT` | No | `30.0` | Request timeout (seconds) |
| `TELEGRAM_RATE_LIMIT_PER_MINUTE` | No | `10` | Max requests per minute |
| `TELEGRAM_RATE_LIMIT_PER_HOUR` | No | `100` | Max requests per hour |
| `TELEGRAM_RATE_LIMIT_PER_DAY` | No | `500` | Max requests per day |
| `TELEGRAM_MAX_FILE_SIZE` | No | `20971520` | Max file size (20MB) |
| **Database** |
| `POSTGRES_PASSWORD` | Yes | `changeme` | PostgreSQL password |
| `POSTGRES_USER` | No | `june` | PostgreSQL user |
| `POSTGRES_DB` | No | `june` | PostgreSQL database |
| **MinIO** |
| `MINIO_ROOT_USER` | No | `admin` | MinIO admin user |
| `MINIO_ROOT_PASSWORD` | Yes | `changeme` | MinIO admin password |
| **Authentication** |
| `JWT_SECRET` | No | `change-this-secret` | JWT signing secret |
| **External Services** |
| `HUGGINGFACE_TOKEN` | Yes* | - | Hugging Face API token |
| **gRPC Configuration** |
| `GRPC_MAX_CONNECTIONS_PER_SERVICE` | No | `10` | Max gRPC connections |
| `GRPC_KEEPALIVE_TIME_MS` | No | `30000` | Keepalive interval (ms) |
| `GRPC_KEEPALIVE_TIMEOUT_MS` | No | `5000` | Keepalive timeout (ms) |
| **Logging** |
| `LOG_LEVEL` | No | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| **Data Directories** |
| `JUNE_DATA_DIR` | No | `/home/rlee/june_data` | Data directory |
| `MODEL_CACHE_DIR` | No | `/home/rlee/models` | Model cache directory |
| `JUNE_TEST_DATA_DIR` | No | `/home/rlee/june_test_data` | Test data directory |
| **Service URLs** |
| `STT_URL` | No | `grpc://stt:50052` | STT service endpoint |
| `TTS_URL` | No | `grpc://tts:50053` | TTS service endpoint |
| `LLM_URL` | No | `grpc://inference-api:50051` | Inference API endpoint |
| `NATS_URL` | No | `nats://nats:4222` | NATS messaging endpoint |
| `POSTGRES_URL` | No | Auto | PostgreSQL connection string |
| `MINIO_ENDPOINT` | No | `minio:9000` | MinIO endpoint |
| **Monitoring** |
| `GRAFANA_PASSWORD` | No | `admin` | Grafana admin password |

\* Required if using Telegram bot  
\** Required if `TELEGRAM_USE_WEBHOOK=true`

### Troubleshooting Common Issues

#### Service Won't Start

**Symptoms:** Service fails to start or crashes immediately

**Diagnosis:**
```bash
# Check service logs
docker-compose logs <service-name>

# Check environment variables
docker-compose exec <service-name> env

# Check service status
docker-compose ps
```

**Common Causes:**
- Missing required environment variables
- Invalid configuration values
- Port conflicts
- Insufficient resources (CPU/memory)
- Missing dependencies (other services not running)
- Database connection failures

**Solutions:**
- Verify all required environment variables are set
- Check port availability: `netstat -tuln | grep <port>`
- Increase resource limits if needed
- Ensure dependencies are running: `docker-compose ps`
- Check database connectivity: `docker-compose exec postgres pg_isready`

#### High Error Rates

**Symptoms:** High percentage of failed requests (5xx errors)

**Diagnosis:**
```bash
# Check error rates in Prometheus
# Query: rate(http_requests_total{status=~"5.."}[5m])

# Check service logs for errors
docker-compose logs -f <service-name> | grep ERROR

# Check service health
curl http://localhost:<port>/health
```

**Common Causes:**
- Service dependencies unavailable (STT/TTS/LLM)
- Database connection issues
- Resource exhaustion (CPU/memory/GPU)
- Network connectivity problems
- Invalid requests or configuration

**Solutions:**
- Verify all service dependencies are healthy
- Check database connectivity and connection pool
- Monitor resource usage: `docker stats`
- Check network connectivity between services
- Review error logs for specific error messages
- Verify configuration values

#### Performance Issues

**Symptoms:** Slow response times, high latency

**Diagnosis:**
```bash
# Check request latencies in Prometheus
# Query: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Check resource usage
docker stats

# Check GPU utilization
nvidia-smi

# Check database query performance
docker-compose exec postgres psql -U june -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

**Common Causes:**
- Insufficient resources (CPU/memory/GPU)
- Database query performance issues
- Network latency
- Inefficient model inference
- Connection pool exhaustion

**Solutions:**
- Increase resource limits for services
- Optimize database queries and add indexes
- Check network latency between services
- Optimize model inference (quantization, batching)
- Increase connection pool sizes
- Scale services horizontally

#### Database Connection Issues

**Symptoms:** Database connection errors, connection pool exhaustion

**Diagnosis:**
```bash
# Check database connectivity
docker-compose exec postgres pg_isready

# Check connection count
docker-compose exec postgres psql -U june -c "SELECT count(*) FROM pg_stat_activity;"

# Check database logs
docker-compose logs postgres
```

**Common Causes:**
- Database not running
- Incorrect connection string
- Connection pool too small
- Too many connections
- Database performance issues

**Solutions:**
- Ensure PostgreSQL is running: `docker-compose ps postgres`
- Verify connection string format
- Increase connection pool size
- Check `max_connections` setting in PostgreSQL
- Optimize slow queries

#### GPU Issues

**Symptoms:** GPU not available, CUDA errors, low GPU utilization

**Diagnosis:**
```bash
# Check GPU availability
nvidia-smi

# Check CUDA in container
docker-compose exec inference-api nvidia-smi

# Check CUDA MPS status
docker-compose exec inference-api ps aux | grep mps
```

**Common Causes:**
- NVIDIA Container Toolkit not installed
- GPU not accessible in container
- CUDA MPS not configured
- Insufficient GPU memory
- Multiple services competing for GPU

**Solutions:**
- Install NVIDIA Container Toolkit
- Verify GPU access: `docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi`
- Enable CUDA MPS: `CUDA_MPS_ENABLE_PER_CTX_SM_PARTITIONING=1`
- Monitor GPU memory usage
- Distribute services across multiple GPUs if available

#### Webhook Not Working (Telegram)

**Symptoms:** Telegram webhook not receiving updates

**Diagnosis:**
```bash
# Check webhook status
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Test webhook endpoint
curl -X POST https://your-domain.com/webhook -d '{"test": true}'

# Check SSL certificate
openssl s_client -connect your-domain.com:8443
```

**Common Causes:**
- Invalid SSL certificate
- Firewall blocking port 8443
- Incorrect webhook URL
- Telegram IP ranges blocked

**Solutions:**
- Verify SSL certificate is valid and trusted
- Check firewall rules allow Telegram IP ranges
- Verify webhook URL is correct and accessible
- Test webhook endpoint manually
- Check Telegram webhook documentation for IP ranges

#### Monitoring Not Working

**Symptoms:** Prometheus/Grafana not collecting metrics

**Diagnosis:**
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check service metrics endpoints
curl http://localhost:8000/metrics

# Check Prometheus configuration
docker-compose exec prometheus cat /etc/prometheus/prometheus.yml
```

**Common Causes:**
- Services not exposing metrics endpoints
- Prometheus configuration incorrect
- Network connectivity issues
- Service not running

**Solutions:**
- Verify services expose `/metrics` endpoints
- Check Prometheus configuration in `config/prometheus.yml`
- Verify network connectivity between Prometheus and services
- Ensure all services are running

### Additional Resources

- **Architecture Documentation**: See architecture overview in this README
- **API Documentation**: See API usage examples in this README
- **Development Setup**: See development section for local setup
- **Contributing Guidelines**: See contributing section for development workflow

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

## 📦 Standalone Service Deployment (Non-Container)

Some services (Telegram and Discord bots) can be deployed as standalone processes without Docker containers. This is useful for services that need direct access to the host system or when running `cursor-agent` processes.

### Prerequisites

- Python 3.10+
- Poetry installed (`pip install poetry`)
- Repository `.env` file configured with required environment variables (see Environment Configuration below)

### Building a Service

The build process creates a tarball containing a pristine virtual environment and all necessary code:

```bash
# Build a service (e.g., telegram or discord)
./scripts/build.sh <service-name>

# Example: Build telegram service
./scripts/build.sh telegram

# Example: Build discord service
./scripts/build.sh discord
```

The build script will:
1. Create a pristine Python virtual environment
2. Install all dependencies (minimal set for telegram/discord, full poetry install for others)
3. Copy the essence module and service code
4. Create a run script (`run.sh`) that executes `python -m essence <service-name>-service`
5. Package everything into a tarball in `build/` directory
6. Automatically clean up old builds, keeping only the last 3

**Output:**
- Tarball: `build/june-<service-name>-<timestamp>.tar.gz`
- Checksum: `build/june-<service-name>-<timestamp>.tar.gz.sha256`

**Important:** The `.env` file is **not** included in the build. Environment variables are sourced at runtime from the repository's `.env` file via the `ENV_SH` mechanism (see Environment Configuration below).

### Command Pattern Architecture

All services use a reflection-based command discovery system:

- **Automatic Discovery**: Commands are discovered automatically by scanning `essence.commands` for `Command` subclasses using Python's `inspect` and `pkgutil` modules
- **No Manual Registration**: No manual registration required - commands are found via Python reflection at runtime
- **Discovery Process**: 
  - The `essence.__main__.get_commands()` function iterates through all modules in `essence.commands`
  - For each module, it uses `inspect.getmembers()` to find classes that are subclasses of `Command`
  - Command names are extracted via `command_class.get_name()` method
  - Commands are cached after first discovery for performance
- **Service Invocation**: Services are invoked via: `python -m essence <service-name>-service [args...]`
- **Command Interface**: Each command implements the `essence.command.Command` interface with:
  - `get_name()` - Returns the command name (e.g., "telegram-service")
  - `get_description()` - Returns command description for help text
  - `add_args(parser)` - Adds command-specific arguments to argparse parser
  - `__init__(args)` - Initializes the command with parsed arguments
  - `execute()` - Executes the command (calls `init()`, `run()`, and `cleanup()` lifecycle methods)

### Environment Configuration

Services source environment variables from the repository's `.env` file at runtime using the **ENV_SH mechanism**:

1. **Repository `.env` file**: Located at the project root (`/home/rlee/dev/june/.env`)
2. **ENV_SH Environment Variable**: The deploy script sets `ENV_SH` environment variable to point to the repo's `.env` file path
3. **Runtime Sourcing in run.sh**: The generated `run.sh` script checks for `ENV_SH` and sources it before starting the service:
   ```bash
   if [ -n "${ENV_SH:-}" ] && [ -f "${ENV_SH}" ]; then
       echo "Sourcing environment from: ${ENV_SH}"
       set -a  # Automatically export all variables
       source "${ENV_SH}"
       set +a
   ```
4. **Fallback**: If `ENV_SH` is not set, services fall back to a local `.env` file in the service directory (if present)
5. **Verification**: The console log will show "Sourcing environment from: <path>" when ENV_SH is successfully sourced

**Benefits:**
- `.env` file stays in one place (repo root) - no need to copy it to each deployment
- No secrets in build artifacts - environment variables are not included in tarballs
- Easy to update environment variables without rebuilding - just update the repo's `.env` file
- Supports both development and production deployments - same mechanism works everywhere
- Centralized configuration management - all services use the same `.env` file

**Required Environment Variables:**
- `SERVICE_NAME`: Service name (set automatically by deploy script)
- `TELEGRAM_BOT_TOKEN`: Telegram bot token (for telegram service)
- `DISCORD_BOT_TOKEN`: Discord bot token (for discord service)
- Service-specific ports and configuration

### Deploying a Service

The deploy script handles stopping the previous version, deploying the new version, and starting the service:

```bash
# Deploy a service
./scripts/deploy.sh <service-name> <tarball-name>

# Example: Deploy telegram service
./scripts/deploy.sh telegram june-telegram-20240101-120000.tar.gz

# Example: Deploy discord service
./scripts/deploy.sh discord june-discord-20240101-120000.tar.gz
```

The deploy script will:
1. Verify the tarball checksum
2. Stop the previous version if running (graceful shutdown with SIGTERM)
3. Remove the old deployment from `/usr/local/june/<service-name>` (or `~/.local/run/june/<service-name>` for non-root)
4. Extract the new tarball
5. **Verify deployment structure** (checks for required files, essence module importability, command discovery)
6. Set `ENV_SH` to point to the repository's `.env` file
7. Start the service in the background with proper logging

**Service Locations:**
- Runtime directory: `/usr/local/june/<service-name>/` (or `~/.local/run/june/<service-name>` for non-root)
- Console logs: `/var/log/june/<service-name>.console` (or `~/.local/log/june/<service-name>.console` for non-root)
- Application logs: `/var/log/june/<service-name>.log` (or `~/.local/log/june/<service-name>.log` for non-root)
- PID file: `<runtime-dir>/service.pid`

**Deployment Verification:**
The deploy script automatically performs comprehensive verification before starting the service:

1. **File Structure Verification**: Checks for required files:
   - `run.sh` - Service startup script
   - `venv/bin/python3` - Python interpreter in virtual environment
   - `essence/__main__.py` - Essence module entry point
   - `essence/command/__init__.py` - Command base class
   - `essence/commands` - Commands directory

2. **Module Import Verification**: Verifies the essence module can be imported:
   ```bash
   python3 -c "import sys; sys.path.insert(0, '.'); import essence; print('✓ Essence module importable')"
   ```

3. **Command Discovery Verification**: Verifies commands can be discovered via reflection:
   ```bash
   python3 -c "from essence.__main__ import get_commands; cmds = get_commands(); print(f'✓ Discovered {len(cmds)} command(s)')"
   ```
   - This ensures the reflection-based command discovery system is working
   - Lists all discovered commands (e.g., `telegram-service`, `discord-service`, `tts`)
   - If discovery fails, a warning is shown but deployment continues

4. **Checksum Verification**: If a `.sha256` checksum file exists, the tarball integrity is verified before extraction

**Verification Failure Handling:**
- If file structure verification fails: Deployment is aborted with a list of missing files
- If module import fails: Deployment is aborted with an error message
- If command discovery fails: A warning is shown but deployment continues (service may still work)

**Verification Output:**
The deploy script provides clear feedback during verification:
```
Verifying deployment structure...
Verifying essence module...
✓ Essence module importable
Verifying command discovery...
✓ Discovered 3 command(s): ['discord-service', 'telegram-service', 'tts']
```

### Testing Services

Both Telegram and Discord services expose HTTP endpoints for testing:

#### Telegram Service (Port 8080)

```bash
# Health check
curl http://localhost:8080/health | jq

# Test agent message endpoint
curl -X POST http://localhost:8080/api/agent/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, this is a test"}' | jq

# Metrics endpoint
curl http://localhost:8080/metrics
```

#### Discord Service (Port 8081)

```bash
# Health check
curl http://localhost:8081/health | jq

# Metrics endpoint
curl http://localhost:8081/metrics
```

### Service Management

#### Viewing Logs

```bash
# Console output (stdout/stderr)
tail -f /var/log/june/<service-name>.console

# Application logs
tail -f /var/log/june/<service-name>.log
```

#### Stopping a Service

```bash
# Stop using PID file
kill $(cat /var/run/june/<service-name>/service.pid)

# Or stop by process name
pkill -f "essence <service-name>-service"
```

#### Restarting a Service

```bash
# Stop the service
kill $(cat /var/run/june/<service-name>/service.pid)

# Wait a moment
sleep 2

# Start again (service will auto-start from deploy, or manually):
cd /var/run/june/<service-name>
./run.sh >> /var/log/june/<service-name>.console 2>&1 &
echo $! > service.pid
```

### Environment Configuration

Before deploying, ensure required environment variables are set in `/var/run/june/<service-name>/.env`:

**Telegram Service:**
```bash
SERVICE_NAME=telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_SERVICE_PORT=8080
# ... other required variables
```

**Discord Service:**
```bash
SERVICE_NAME=discord
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_SERVICE_PORT=8081
# ... other required variables
```

### Command Pattern

All services use the `essence` command pattern:

```bash
# Services are run via:
poetry run -m essence <service-name>-service [args...]

# Or directly with Python:
python -m essence <service-name>-service [args...]
```

Available commands:
- `telegram-service` - Telegram bot service
- `discord-service` - Discord bot service
- `tts` - Text-to-Speech service (future)
- `stt` - Speech-to-Text service (future)

Each command implements the `essence.command.Command` interface with:
- `init()` - Initialize the service
- `run()` - Run the service (blocking)
- `cleanup()` - Clean up resources on shutdown

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

June Agent implements comprehensive security measures to protect the system and user data:

- **JWT Authentication**: Secure token-based authentication with access and refresh tokens
- **Rate Limiting**: Prevents abuse and ensures fair usage with per-user, per-IP, and per-endpoint limits
- **Input Validation**: Comprehensive input sanitization using june-security package
- **Security Headers**: Protection against XSS, clickjacking, and other web vulnerabilities
- **Data Encryption**: Encryption at rest and in transit (TLS/HTTPS)
- **Security Monitoring**: Threat detection, audit logging, and security metrics
- **Network Security**: Internal service communication over gRPC with TLS support

**For comprehensive security documentation, see:**
- **[Security Documentation](docs/SECURITY.md)** - Complete security guide covering architecture, practices, and procedures
- **[Security Runbook](docs/SECURITY_RUNBOOK.md)** - Operational security procedures and incident response
- **[Security Audit Report](docs/SECURITY_AUDIT_REPORT.md)** - Security audit findings and recommendations
- **[Security Headers](docs/SECURITY_HEADERS.md)** - Security headers configuration
- **[Rate Limiting](docs/RATE_LIMITING.md)** - Rate limiting implementation details
- **[june-security Package](packages/june-security/README.md)** - Security package documentation

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