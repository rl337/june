"""
Download models command - The ONLY authorized way to download models for June Agent.

Usage:
    poetry run -m essence download-models --model Qwen/Qwen3-30B-A3B-Thinking-2507
    poetry run -m essence download-models --all
    poetry run -m essence download-models --list
    poetry run -m essence download-models --status

This script is the single point of model acquisition and must be run independently
of the main infrastructure to prevent accidental downloads during runtime.
"""
import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

try:
    import requests
    from huggingface_hub import hf_hub_download, snapshot_download
    import whisper
    from TTS.api import TTS
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    DEPENDENCIES_AVAILABLE = False
    IMPORT_ERROR = str(e)

from essence.command import Command

logger = logging.getLogger(__name__)

# Model cache directory
MODEL_CACHE_DIR = Path("/home/rlee/models")
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
        },
        "openai/whisper-medium": {
            "description": "Alternative STT model (smaller)",
            "size": "~1.5GB",
            "required": False
        }
    },
    "tts": {
        "facebook/fastspeech2-en-ljspeech": {
            "description": "Text-to-speech model",
            "size": "~500MB",
            "required": True
        },
        "tts_models/en/ljspeech/tacotron2-DDC": {
            "description": "Alternative TTS model",
            "size": "~200MB",
            "required": False
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


class ModelDownloader:
    """Handles model downloads with strict authorization checks."""
    
    def __init__(self):
        self.cache_dir = MODEL_CACHE_DIR
        self.hf_cache_dir = HUGGINGFACE_CACHE_DIR
        self.transformers_cache_dir = TRANSFORMERS_CACHE_DIR
        self.whisper_cache_dir = WHISPER_CACHE_DIR
        self.tts_cache_dir = TTS_CACHE_DIR
        
        # Create cache directories
        for cache_dir in [self.cache_dir, self.hf_cache_dir, self.transformers_cache_dir, 
                         self.whisper_cache_dir, self.tts_cache_dir]:
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created cache directory: {cache_dir}")
    
    def is_model_authorized(self, model_name: str) -> bool:
        """Check if a model is in the authorized list."""
        for category, models in AUTHORIZED_MODELS.items():
            if model_name in models:
                return True
        return False
    
    def get_model_category(self, model_name: str) -> Optional[str]:
        """Get the category of a model."""
        for category, models in AUTHORIZED_MODELS.items():
            if model_name in models:
                return category
        return None
    
    def download_huggingface_model(self, model_name: str, category: str) -> bool:
        """Download a Hugging Face model."""
        try:
            logger.info(f"Downloading Hugging Face model: {model_name}")
            
            # Set cache directories
            os.environ["HF_HOME"] = str(self.hf_cache_dir)
            os.environ["TRANSFORMERS_CACHE"] = str(self.transformers_cache_dir)
            
            # Download the model
            if category == "llm":
                # For large language models, download the entire repository
                snapshot_download(
                    repo_id=model_name,
                    cache_dir=self.hf_cache_dir,
                    local_files_only=False
                )
            else:
                # For other models, download specific files
                hf_hub_download(
                    repo_id=model_name,
                    cache_dir=self.hf_cache_dir,
                    local_files_only=False
                )
            
            logger.info(f"Successfully downloaded {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download {model_name}: {e}")
            return False
    
    def download_whisper_model(self, model_name: str) -> bool:
        """Download a Whisper model."""
        try:
            logger.info(f"Downloading Whisper model: {model_name}")
            
            # Set Whisper cache directory
            os.environ["WHISPER_CACHE_DIR"] = str(self.whisper_cache_dir)
            
            # Download the model
            whisper.load_model(model_name, download_root=str(self.whisper_cache_dir))
            
            logger.info(f"Successfully downloaded Whisper model: {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download Whisper model {model_name}: {e}")
            return False
    
    def download_tts_model(self, model_name: str) -> bool:
        """Download a TTS model."""
        try:
            logger.info(f"Downloading TTS model: {model_name}")
            
            # Set TTS cache directory
            os.environ["TTS_CACHE_DIR"] = str(self.tts_cache_dir)
            
            # Download the model
            TTS(model_name=model_name, progress_bar=True)
            
            logger.info(f"Successfully downloaded TTS model: {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download TTS model {model_name}: {e}")
            return False
    
    def download_model(self, model_name: str) -> bool:
        """Download a specific model."""
        if not self.is_model_authorized(model_name):
            logger.error(f"Model {model_name} is not authorized for download!")
            logger.error("Only models in the AUTHORIZED_MODELS list can be downloaded.")
            return False
        
        category = self.get_model_category(model_name)
        if not category:
            logger.error(f"Could not determine category for model: {model_name}")
            return False
        
        logger.info(f"Downloading {category} model: {model_name}")
        
        if category in ["llm", "embedding"]:
            return self.download_huggingface_model(model_name, category)
        elif category == "stt":
            return self.download_whisper_model(model_name)
        elif category == "tts":
            return self.download_tts_model(model_name)
        else:
            logger.error(f"Unknown model category: {category}")
            return False
    
    def download_all_required_models(self) -> bool:
        """Download all required models."""
        logger.info("Downloading all required models...")
        
        success = True
        for category, models in AUTHORIZED_MODELS.items():
            for model_name, model_info in models.items():
                if model_info["required"]:
                    if not self.download_model(model_name):
                        success = False
        
        return success
    
    def list_authorized_models(self):
        """List all authorized models."""
        print("\nAuthorized Models for June Agent:")
        print("=" * 50)
        
        for category, models in AUTHORIZED_MODELS.items():
            print(f"\n{category.upper()} Models:")
            for model_name, model_info in models.items():
                status = "REQUIRED" if model_info["required"] else "OPTIONAL"
                print(f"  • {model_name}")
                print(f"    Description: {model_info['description']}")
                print(f"    Size: {model_info['size']}")
                print(f"    Status: {status}")
                print()
    
    def check_model_exists(self, model_name: str) -> bool:
        """Check if a model exists in the cache."""
        category = self.get_model_category(model_name)
        if not category:
            return False
        
        if category in ["llm", "embedding"]:
            cache_path = self.hf_cache_dir / "models--" + model_name.replace("/", "--")
            return cache_path.exists()
        elif category == "stt":
            cache_path = self.whisper_cache_dir / f"{model_name}.pt"
            return cache_path.exists()
        elif category == "tts":
            cache_path = self.tts_cache_dir / model_name
            return cache_path.exists()
        
        return False
    
    def get_cache_status(self):
        """Get status of all models in cache."""
        print("\nModel Cache Status:")
        print("=" * 30)
        
        for category, models in AUTHORIZED_MODELS.items():
            print(f"\n{category.upper()} Models:")
            for model_name, model_info in models.items():
                exists = self.check_model_exists(model_name)
                status = "✓ CACHED" if exists else "✗ NOT CACHED"
                required = " (REQUIRED)" if model_info["required"] else ""
                print(f"  {status} {model_name}{required}")


class DownloadModelsCommand(Command):
    """Command for downloading models for June Agent."""
    
    @classmethod
    def get_name(cls) -> str:
        return "download-models"
    
    @classmethod
    def get_description(cls) -> str:
        return "Download models for June Agent (authorized models only)"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--model", "-m",
            help="Download specific model"
        )
        parser.add_argument(
            "--all", "-a",
            action="store_true",
            help="Download all required models"
        )
        parser.add_argument(
            "--list", "-l",
            action="store_true",
            help="List authorized models"
        )
        parser.add_argument(
            "--status", "-s",
            action="store_true",
            help="Check cache status"
        )
        parser.add_argument(
            "--force", "-f",
            action="store_true",
            help="Force re-download (not yet implemented)"
        )
    
    def init(self) -> None:
        """Initialize download models command."""
        if not DEPENDENCIES_AVAILABLE:
            error_msg = f"Required dependencies not available: {IMPORT_ERROR}"
            logger.error(error_msg)
            raise RuntimeError(f"{error_msg}\nInstall with: pip install huggingface_hub openai-whisper TTS")
    
    def run(self) -> None:
        """Run the model download command."""
        downloader = ModelDownloader()
        
        if self.args.list:
            downloader.list_authorized_models()
            return
        
        if self.args.status:
            downloader.get_cache_status()
            return
        
        if self.args.all:
            success = downloader.download_all_required_models()
            if success:
                logger.info("All required models downloaded successfully!")
            else:
                logger.error("Some models failed to download.")
                sys.exit(1)
        elif self.args.model:
            success = downloader.download_model(self.args.model)
            if success:
                logger.info(f"Model {self.args.model} downloaded successfully!")
            else:
                logger.error(f"Failed to download model {self.args.model}")
                sys.exit(1)
        else:
            # No action specified, show help
            logger.error("No action specified. Use --model, --all, --list, or --status")
            sys.exit(1)
    
    def cleanup(self) -> None:
        """Clean up download models command."""
        # No cleanup needed for this tool
        pass
