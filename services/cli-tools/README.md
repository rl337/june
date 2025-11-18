# CLI Tools Container

This container provides all command-line tools and utilities for June Agent development and maintenance.

## Quick Start

```bash
# Start CLI tools container
docker compose --profile tools up -d cli-tools

# Access the container
docker exec -it june-cli-tools bash
```

## Available Tools

### Model Management
- **download_models.py** - Download authorized models to cache
- **Model validation** - Check model cache status
- **Cache management** - Organize models by category

### Audio Testing
- **audio_test_suite.py** - Comprehensive audio testing with real datasets
- **simple_audio_test.py** - Simple audio service testing
- **Test data management** - LibriSpeech, LJSpeech, synthetic datasets
- **Performance metrics** - WER, CER, MCD, MSE calculations

```bash
# Comprehensive audio testing suite
python scripts/audio_test_suite.py --test-all

# Simple audio service testing
python scripts/simple_audio_test.py --test-all

# Download test datasets
python scripts/audio_test_suite.py --download
```

### Development Tools
- **Code formatting** - black, isort
- **Linting** - flake8, mypy
- **Testing** - pytest, pytest-cov
- **Audio processing** - whisper, TTS, librosa

## Usage Examples

### Model Download
```bash
# Download all required models
poetry run -m essence download-models --all

# Download specific model
poetry run -m essence download-models --model Qwen/Qwen3-30B-A3B-Thinking-2507

# Check cache status
poetry run -m essence download-models --status

# List authorized models
poetry run -m essence download-models --list
```

### Development
```bash
# Code formatting
black /app/scripts/
isort /app/scripts/

# Linting
flake8 /app/scripts/
mypy /app/scripts/

# Testing
pytest /app/scripts/
```

## Environment Variables

- `MODEL_CACHE_DIR` - Model cache directory (default: `/models`)
- `HUGGINGFACE_TOKEN` - Hugging Face API token
- `HUGGINGFACE_CACHE_DIR` - Hugging Face cache directory
- `TRANSFORMERS_CACHE_DIR` - Transformers cache directory

## Adding New Tools

1. Add dependencies to `requirements-cli.txt`
2. Create tool script in `scripts/` directory
3. Update Dockerfile if system dependencies needed
4. Test tool in container
5. Update documentation

## Troubleshooting

### Docker Permission Issues
```bash
# Run setup script
./scripts/setup_docker.sh

# Or manually:
sudo usermod -aG docker $USER
newgrp docker
```

### Container Not Starting
```bash
# Check logs
docker compose logs cli-tools

# Rebuild container
docker compose build cli-tools
```
