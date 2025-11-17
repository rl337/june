#!/usr/bin/env python3
"""
Download Qwen3-30B-A3B-Thinking-2507 model in a container.

This script downloads the model to the /models volume mount.
All operations happen in the container - no host system pollution.

Usage (from container):
    python /app/root_scripts/download_qwen3.py

Or from host:
    docker compose run --rm cli-tools python /app/root_scripts/download_qwen3.py
"""
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    model_name = os.getenv('MODEL_NAME', 'Qwen/Qwen3-30B-A3B-Thinking-2507')
    cache_dir = os.getenv('MODEL_CACHE_DIR', '/models')
    huggingface_cache_dir = os.getenv('HUGGINGFACE_CACHE_DIR', f'{cache_dir}/huggingface')
    token = os.getenv('HUGGINGFACE_TOKEN')
    
    logger.info(f"Downloading {model_name} to {huggingface_cache_dir}")
    logger.info(f"Model cache directory: {cache_dir}")
    
    if not token:
        logger.warning("HUGGINGFACE_TOKEN not set - model may be gated and require authentication")
        logger.warning("Set HUGGINGFACE_TOKEN environment variable if download fails")
    
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        import torch
        
        logger.info("✓ transformers and torch imported successfully")
        
        # Create cache directory if it doesn't exist
        os.makedirs(huggingface_cache_dir, exist_ok=True)
        
        # Set HuggingFace cache environment variables
        os.environ['HF_HOME'] = huggingface_cache_dir
        os.environ['TRANSFORMERS_CACHE'] = huggingface_cache_dir
        
        logger.info("Downloading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=huggingface_cache_dir,
            token=token,
            trust_remote_code=True
        )
        logger.info("✓ Tokenizer downloaded successfully")
        
        # Check if model is already downloaded
        model_path = Path(huggingface_cache_dir) / "hub" / f"models--{model_name.replace('/', '--')}"
        if model_path.exists():
            logger.info(f"Model directory exists at {model_path}")
            logger.info("Checking if model files are complete...")
            # Check for key model files
            safetensors_files = list(model_path.rglob("*.safetensors"))
            if safetensors_files:
                logger.info(f"Found {len(safetensors_files)} safetensors files")
                logger.info("Model appears to be already downloaded. Skipping download.")
                logger.info("To force re-download, delete the model directory first.")
                return
        
        # Download model files without loading into memory
        # The model will be quantized when loaded by inference-api service
        logger.info("Downloading model files (this may take a while)...")
        logger.info("Note: Model will be quantized when loaded by inference-api service")
        
        # Use snapshot_download to download all files without loading the model
        try:
            from huggingface_hub import snapshot_download
            logger.info("Using huggingface_hub.snapshot_download for efficient download...")
            model_path = snapshot_download(
                repo_id=model_name,
                cache_dir=huggingface_cache_dir,
                token=token,
                local_files_only=False,
                resume_download=True
            )
            logger.info(f"✓ Model files downloaded successfully to {model_path}")
            model_path_obj = Path(model_path)
        except ImportError:
            logger.warning("huggingface_hub not available, using transformers download...")
            # Fallback: download by loading model (requires more memory)
            # This is less efficient but works if huggingface_hub is not available
            model_kwargs = {
                "cache_dir": huggingface_cache_dir,
                "token": token,
                "trust_remote_code": True,
                "local_files_only": False,
            }
            
            # Try to use device_map if accelerate is available
            try:
                import accelerate
                model_kwargs["device_map"] = "cpu"  # Use CPU for download, not GPU
                model_kwargs["low_cpu_mem_usage"] = True
            except ImportError:
                logger.warning("accelerate not available - downloading without device_map")
            
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                **model_kwargs
            )
            logger.info("✓ Model downloaded successfully")
            # Get the actual model path from cache
            model_path_obj = Path(huggingface_cache_dir) / "hub" / f"models--{model_name.replace('/', '--')}"
        
        logger.info(f"Model cached at: {huggingface_cache_dir}")
        
        # Check model size
        if model_path_obj.exists():
            import subprocess
            result = subprocess.run(
                ['du', '-sh', str(model_path_obj)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info(f"Model size: {result.stdout.strip()}")
        
    except ImportError as e:
        logger.error(f"Failed to import required packages: {e}")
        logger.error("Make sure transformers, torch, and bitsandbytes are installed in the container")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        logger.error("Check HUGGINGFACE_TOKEN if model is gated")
        sys.exit(1)

if __name__ == "__main__":
    main()
