# Scripts Directory

This directory contains authorized scripts for June Agent system management.

## Model Management

### `download_models.py`
**The ONLY authorized way to download models for June Agent.**

This script enforces strict model management policies:
- Only downloads models from the AUTHORIZED_MODELS list
- Downloads to the designated cache directory (`/home/rlee/models`)
- Prevents accidental downloads during runtime
- Provides model cache status and management

**Usage:**
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

**Security Features:**
- Whitelist of authorized models only
- No internet access during runtime
- Centralized model cache management
- Audit trail for model downloads

## Important Notes

- **NEVER** modify services to download models automatically
- **ALWAYS** use this script for model acquisition
- **VERIFY** models exist in cache before starting services
- **AUDIT** model cache directory regularly

## Model Cache Structure

```
/home/rlee/models/
├── huggingface/          # Hugging Face models
├── transformers/         # Transformers cache
├── whisper/              # Whisper models
└── tts/                  # TTS models
```
