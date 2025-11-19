# Model Compilation Guide

This guide covers downloading and compiling models for the June system.

## Available Tools

### Model Tools Container

The `model-tools` container provides all necessary tools for downloading and preparing models:

```bash
# Start the container
docker compose up -d model-tools

# Access the container
docker exec -it june-model-tools bash
```

**Available tools:**
- `huggingface-cli` / `hf` - Download models from HuggingFace
- `whisper` - OpenAI Whisper for STT
- Python 3.10 with PyTorch, Transformers, etc.

## Model Downloads

### Whisper (STT)

```bash
docker exec june-model-tools huggingface-cli download openai/whisper-large-v3 --cache-dir /models
```

Model will be cached at: `/home/rlee/models/models--openai--whisper-large-v3/`

### TTS Model

```bash
docker exec june-model-tools huggingface-cli download facebook/fastspeech2-en-ljspeech --cache-dir /models
```

Model will be cached at: `/home/rlee/models/models--facebook--fastspeech2-en-ljspeech/`

### Qwen3-30B-A3B-Thinking-2507 (LLM)

The model should already be downloaded at:
`/home/rlee/models/models--Qwen--Qwen3-30B-A3B-Thinking-2507/`

## TensorRT-LLM Compilation

**Status:** ⚠️ Requires NVIDIA TensorRT-LLM build container

The Triton Inference Server container (`nvcr.io/nvidia/tritonserver:24.10-py3`) does **not** include TensorRT-LLM build tools. You need a separate TensorRT-LLM build container.

### Option 1: Use NVIDIA TensorRT-LLM Container (Recommended)

NVIDIA provides TensorRT-LLM containers with build tools. You'll need to:

1. **Get TensorRT-LLM container** from NVIDIA NGC (requires NVIDIA account):
   ```bash
   docker pull nvcr.io/nvidia/tensorrt-llm:latest
   ```

2. **Compile the model**:
   ```bash
   MODEL_DIR="/home/rlee/models/models--Qwen--Qwen3-30B-A3B-Thinking-2507/snapshots/144afc2f379b542fdd4e85a1fcd5e1f79112d95d"
   OUTPUT_DIR="/home/rlee/models/triton-repository/qwen3-30b/1"
   
   docker run --rm --gpus all \
     -v /home/rlee/models:/models \
     -v /home/rlee/dev/june:/workspace \
     -e HF_HOME=/models \
     -e TRANSFORMERS_CACHE=/models \
     -e HF_HUB_CACHE=/models \
     nvcr.io/nvidia/tensorrt-llm:latest \
     trtllm-build \
       --checkpoint_dir "$MODEL_DIR" \
       --output_dir "$OUTPUT_DIR" \
       --gemm_plugin float16 \
       --gpt_attention_plugin float16 \
       --context_fmha enable \
       --quantization int8 \
       --max_batch_size 1 \
       --max_input_len 131072 \
       --max_output_len 2048
   ```

### Option 2: Build TensorRT-LLM from Source

If you need to build TensorRT-LLM from source, follow the [official TensorRT-LLM documentation](https://github.com/NVIDIA/TensorRT-LLM).

### Option 3: Use Compile-Model Command

The `compile-model` command provides guidance and templates:

```bash
cd /home/rlee/dev/june
poetry run python -m essence compile-model \
  --model qwen3-30b \
  --model-hf-name Qwen/Qwen3-30B-A3B-Thinking-2507 \
  --check-prerequisites \
  --generate-template \
  --generate-config \
  --generate-tokenizer-commands
```

This will:
- Check prerequisites (GPU, repository structure, etc.)
- Generate compilation command templates
- Create `config.pbtxt` file
- Provide tokenizer file copy commands

## After Compilation

1. **Copy tokenizer files** from HuggingFace model to Triton repository:
   ```bash
   MODEL_SNAPSHOT="/home/rlee/models/models--Qwen--Qwen3-30B-A3B-Thinking-2507/snapshots/144afc2f379b542fdd4e85a1fcd5e1f79112d95d"
   REPO_DIR="/home/rlee/models/triton-repository/qwen3-30b/1"
   
   cp "$MODEL_SNAPSHOT"/tokenizer*.json "$REPO_DIR/"
   cp "$MODEL_SNAPSHOT"/vocab*.json "$REPO_DIR/" 2>/dev/null || true
   cp "$MODEL_SNAPSHOT"/merges.txt "$REPO_DIR/" 2>/dev/null || true
   ```

2. **Verify model is ready**:
   ```bash
   poetry run python -m essence compile-model --model qwen3-30b --check-readiness
   ```

3. **Load the model**:
   ```bash
   poetry run python -m essence manage-tensorrt-llm --action load --model qwen3-30b
   ```

## Troubleshooting

### TTS Installation Failed

The `model-tools` container may not have TTS installed if Rust version is too old. This is optional - TTS models can still be downloaded and used in other containers.

### TensorRT-LLM Build Tools Not Found

The Triton Inference Server container is for **inference only**, not compilation. You need a separate TensorRT-LLM build container from NVIDIA NGC.

### GPU Not Detected in Container

Ensure Docker has GPU access:
```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

If this fails, install `nvidia-container-toolkit`:
```bash
# Ubuntu/Debian
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

## Next Steps

1. ✅ Model tools container created
2. ✅ Whisper model downloading
3. ✅ TTS model downloading
4. ⏳ Qwen3 compilation (requires TensorRT-LLM build container)
5. ⏳ Copy tokenizer files
6. ⏳ Load model into TensorRT-LLM

