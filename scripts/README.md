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

## Dataset Management

### `generate_alice_dataset.py`
**Generates test dataset from Alice's Adventures in Wonderland.**

This script downloads Alice's Adventures in Wonderland from Project Gutenberg and extracts random 2-3 sentence passages for audio testing.

**Usage:**
```bash
# Generate dataset (downloads book if needed)
python scripts/generate_alice_dataset.py
```

**Output:**
- Book stored at: `${JUNE_DATA_DIR}/datasets/alice_in_wonderland/alice_adventures_in_wonderland.txt`
- Dataset stored at: `${JUNE_DATA_DIR}/datasets/alice_in_wonderland/alice_dataset.json`

**Features:**
- Downloads book from Project Gutenberg (automatically cached locally)
- Extracts random 2-3 sentence passages
- Filters by length (50-500 characters)
- Generates 100 unique passages
- Stores metadata and statistics

### `test_round_trip_alice.py`
**Runs round-trip audio validation tests using Alice dataset.**

Tests the complete audio pipeline: Text → TTS → Audio → STT → Text using the Alice in Wonderland passages.

**Usage:**
```bash
# Run round-trip tests (requires generated dataset)
python scripts/test_round_trip_alice.py
```

**Features:**
- Tests all passages in the dataset (or subset)
- Calculates accuracy metrics (exact match, word accuracy, char accuracy)
- Generates comprehensive test reports
- Stores results in JSON format

**Output:**
- Results stored at: `${JUNE_DATA_DIR}/datasets/alice_in_wonderland/round_trip_test_results.json`

**Note:** The test uses espeak for TTS (if available) or falls back to synthetic audio generation. Real STT uses duration-based estimation for now (to be replaced with Whisper).

