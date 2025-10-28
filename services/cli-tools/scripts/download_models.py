#!/usr/bin/env python3
"""
Model Download Script - The ONLY authorized way to download models for June Agent.

This script is the single point of model acquisition and must be run independently
of the main infrastructure to prevent accidental downloads during runtime.

Usage:
    python download_models.py --model Qwen/Qwen3-30B-A3B-Thinking-2507
    python download_models.py --all
    python download_models.py --list
    python download_models.py --status
"""

import argparse
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional
import requests
from huggingface_hub import hf_hub_download, snapshot_download

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model cache directory
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "/models"))
HUGGINGFACE_CACHE_DIR = MODEL_CACHE_DIR / "huggingface"
TRANSFORMERS_CACHE_DIR = MODEL_CACHE_DIR / "transformers"
WHISPER_CACHE_DIR = MODEL_CACHE_DIR / "whisper"
TTS_CACHE_DIR = MODEL_CACHE_DIR / "tts"

# Authorized models for June Agent
AUTHORIZED_MODELS = {
    "llm": {
        "Qwen/Qwen3-30B-A3B-Thinking-2507": {
            "description": "Primary LLM with advanced reasoning capabilities",
            "size": "~60GB",
            "required": True
        }
    },
    "stt": {
        "openai/whisper-large-v3": {
            "description": "Speech-to-text model",
            "size": "~3GB",
            "required": True
        }
    },
    "tts": {
        "facebook/fastspeech2-en-ljspeech": {
            "description": "Text-to-speech model",
            "size": "~1GB",
            "required": True
        }
    },
    "embedding": {
        "sentence-transformers/all-MiniLM-L6-v2": {
            "description": "Embedding model for RAG",
            "size": "~90MB",
            "required": True
        }
    }
}

def ensure_cache_directories():
    """Ensure all cache directories exist."""
    directories = [
        MODEL_CACHE_DIR,
        HUGGINGFACE_CACHE_DIR,
        TRANSFORMERS_CACHE_DIR,
        WHISPER_CACHE_DIR,
        TTS_CACHE_DIR
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")

def get_huggingface_token() -> Optional[str]:
    """Get Hugging Face token from environment."""
    token = os.getenv("HUGGINGFACE_TOKEN")
    if not token or token == "your_huggingface_token_here":
        logger.warning("HUGGINGFACE_TOKEN not set or using placeholder")
        return None
    return token

def download_model(model_id: str, category: str) -> bool:
    """Download a specific model."""
    if model_id not in AUTHORIZED_MODELS[category]:
        logger.error(f"Model {model_id} not in authorized list for category {category}")
        return False
    
    model_info = AUTHORIZED_MODELS[category][model_id]
    logger.info(f"Downloading {model_id} ({model_info['size']})...")
    
    try:
        # Set cache directories
        os.environ["HF_HOME"] = str(HUGGINGFACE_CACHE_DIR)
        os.environ["TRANSFORMERS_CACHE"] = str(TRANSFORMERS_CACHE_DIR)
        
        # Download model
        token = get_huggingface_token()
        cache_dir = MODEL_CACHE_DIR / category
        
        if category == "llm":
            # For large models, download to specific cache directory
            snapshot_download(
                repo_id=model_id,
                cache_dir=str(cache_dir),
                token=token,
                local_files_only=False
            )
        else:
            # For smaller models, use default cache
            hf_hub_download(
                repo_id=model_id,
                cache_dir=str(cache_dir),
                token=token,
                local_files_only=False
            )
        
        logger.info(f"Successfully downloaded {model_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to download {model_id}: {e}")
        return False

def download_all_models() -> bool:
    """Download all required models."""
    logger.info("Starting download of all required models...")
    
    success = True
    for category, models in AUTHORIZED_MODELS.items():
        for model_id, model_info in models.items():
            if model_info["required"]:
                if not download_model(model_id, category):
                    success = False
    
    return success

def check_model_status() -> Dict[str, Dict[str, bool]]:
    """Check which models are available in cache."""
    status = {}
    
    for category, models in AUTHORIZED_MODELS.items():
        status[category] = {}
        cache_dir = MODEL_CACHE_DIR / category
        
        for model_id in models.keys():
            # Simple check - look for model files in cache
            model_exists = cache_dir.exists() and any(
                model_id.replace("/", "--") in str(path) 
                for path in cache_dir.rglob("*")
            )
            status[category][model_id] = model_exists
    
    return status

def list_models():
    """List all authorized models."""
    print("\n📋 Authorized Models for June Agent:")
    print("=" * 50)
    
    for category, models in AUTHORIZED_MODELS.items():
        print(f"\n🔹 {category.upper()}:")
        for model_id, model_info in models.items():
            required = "✅ REQUIRED" if model_info["required"] else "⚪ Optional"
            print(f"  • {model_id}")
            print(f"    Description: {model_info['description']}")
            print(f"    Size: {model_info['size']}")
            print(f"    Status: {required}")
            print()

def show_status():
    """Show current model cache status."""
    print("\n📊 Model Cache Status:")
    print("=" * 30)
    
    status = check_model_status()
    
    for category, models in status.items():
        print(f"\n🔹 {category.upper()}:")
        for model_id, exists in models.items():
            status_icon = "✅" if exists else "❌"
            print(f"  {status_icon} {model_id}")
    
    print(f"\n📁 Cache Directory: {MODEL_CACHE_DIR}")
    print(f"📁 Hugging Face Cache: {HUGGINGFACE_CACHE_DIR}")
    print(f"📁 Transformers Cache: {TRANSFORMERS_CACHE_DIR}")

def main():
    parser = argparse.ArgumentParser(description="Download models for June Agent")
    parser.add_argument("--model", help="Download specific model")
    parser.add_argument("--all", action="store_true", help="Download all required models")
    parser.add_argument("--list", action="store_true", help="List authorized models")
    parser.add_argument("--status", action="store_true", help="Show cache status")
    
    args = parser.parse_args()
    
    # Ensure cache directories exist
    ensure_cache_directories()
    
    if args.list:
        list_models()
    elif args.status:
        show_status()
    elif args.all:
        success = download_all_models()
        if success:
            logger.info("All models downloaded successfully!")
            sys.exit(0)
        else:
            logger.error("Some models failed to download")
            sys.exit(1)
    elif args.model:
        # Find which category the model belongs to
        found = False
        for category, models in AUTHORIZED_MODELS.items():
            if args.model in models:
                success = download_model(args.model, category)
                if success:
                    logger.info(f"Model {args.model} downloaded successfully!")
                    sys.exit(0)
                else:
                    logger.error(f"Failed to download {args.model}")
                    sys.exit(1)
                found = True
                break
        
        if not found:
            logger.error(f"Model {args.model} not found in authorized list")
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
