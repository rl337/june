"""
Verify Qwen3 quantization command - Verifies quantization settings and monitors model performance.

Usage:
    poetry run -m essence verify-qwen3 [--json]

This command verifies quantization settings and monitors model performance:
- Checks quantization configuration from environment variables
- Verifies if quantization is actually being used in the loaded model
- Monitors GPU/CPU memory usage
- Checks model loading status
- Provides performance metrics
"""
import argparse
import json
import logging
import os
import sys
from typing import Dict, Any

from essence.command import Command

logger = logging.getLogger(__name__)


def check_environment_variables() -> Dict[str, Any]:
    """Check quantization-related environment variables."""
    env_vars = {
        'USE_QUANTIZATION': os.getenv('USE_QUANTIZATION', 'true'),
        'QUANTIZATION_BITS': os.getenv('QUANTIZATION_BITS', '8'),
        'MODEL_DEVICE': os.getenv('MODEL_DEVICE', 'cuda:0'),
        'MODEL_NAME': os.getenv('MODEL_NAME', 'Qwen/Qwen3-30B-A3B-Thinking-2507'),
        'MAX_CONTEXT_LENGTH': os.getenv('MAX_CONTEXT_LENGTH', '131072'),
    }
    
    # Parse boolean
    env_vars['USE_QUANTIZATION'] = env_vars['USE_QUANTIZATION'].lower() == 'true'
    # Parse int
    try:
        env_vars['QUANTIZATION_BITS'] = int(env_vars['QUANTIZATION_BITS'])
    except ValueError:
        env_vars['QUANTIZATION_BITS'] = 8
    
    return env_vars


def check_torch_availability() -> Dict[str, Any]:
    """Check PyTorch and CUDA availability."""
    result = {
        'torch_available': False,
        'cuda_available': False,
        'cuda_version': None,
        'gpu_count': 0,
        'gpu_name': None,
        'gpu_memory_total_gb': None,
        'gpu_memory_allocated_gb': None,
        'gpu_memory_reserved_gb': None,
        'gpu_compute_capability': None,
    }
    
    try:
        import torch
        result['torch_available'] = True
        result['torch_version'] = torch.__version__
        
        if torch.cuda.is_available():
            result['cuda_available'] = True
            result['cuda_version'] = torch.version.cuda
            result['gpu_count'] = torch.cuda.device_count()
            
            if result['gpu_count'] > 0:
                device = torch.cuda.current_device()
                props = torch.cuda.get_device_properties(device)
                result['gpu_name'] = props.name
                result['gpu_memory_total_gb'] = props.total_memory / (1024**3)
                
                # Get current memory usage
                result['gpu_memory_allocated_gb'] = torch.cuda.memory_allocated(device) / (1024**3)
                result['gpu_memory_reserved_gb'] = torch.cuda.memory_reserved(device) / (1024**3)
                
                # Get compute capability
                result['gpu_compute_capability'] = props.major, props.minor
                
    except ImportError:
        logger.warning("PyTorch not available")
    except Exception as e:
        logger.error(f"Error checking PyTorch/CUDA: {e}")
    
    return result


def check_bitsandbytes_availability() -> Dict[str, Any]:
    """Check if bitsandbytes is available for quantization."""
    result = {
        'bitsandbytes_available': False,
        'bitsandbytes_version': None,
    }
    
    try:
        import bitsandbytes as bnb
        result['bitsandbytes_available'] = True
        result['bitsandbytes_version'] = getattr(bnb, '__version__', 'unknown')
    except ImportError:
        logger.warning("bitsandbytes not available - quantization will not work")
    except Exception as e:
        logger.error(f"Error checking bitsandbytes: {e}")
    
    return result


def check_model_quantization_status() -> Dict[str, Any]:
    """Check if model is loaded and verify quantization status."""
    result = {
        'model_loaded': False,
        'quantization_detected': False,
        'quantization_type': None,
        'model_dtype': None,
        'model_device': None,
        'model_config': None,
    }
    
    try:
        from inference_core.config import config
        from inference_core.llm.qwen3_strategy import Qwen3LlmStrategy
        
        # Create strategy instance (this will use config from environment)
        strategy = Qwen3LlmStrategy()
        
        # Check if model is already loaded
        if strategy._model is not None:
            result['model_loaded'] = True
            result['model_device'] = str(next(strategy._model.parameters()).device)
            
            # Check model dtype
            result['model_dtype'] = str(next(strategy._model.parameters()).dtype)
            
            # Check for quantization
            # Quantized models typically have quantization_config or are wrapped
            model = strategy._model
            
            # Check if model is quantized (bitsandbytes wraps models)
            if hasattr(model, 'hf_quantizer'):
                result['quantization_detected'] = True
                result['quantization_type'] = 'bitsandbytes'
            elif hasattr(model, 'quantization_config'):
                result['quantization_detected'] = True
                quant_config = model.quantization_config
                if hasattr(quant_config, 'load_in_4bit'):
                    if quant_config.load_in_4bit:
                        result['quantization_type'] = '4-bit'
                    elif hasattr(quant_config, 'load_in_8bit') and quant_config.load_in_8bit:
                        result['quantization_type'] = '8-bit'
            elif hasattr(model, 'base_model') and hasattr(model.base_model, 'hf_quantizer'):
                # Model might be wrapped
                result['quantization_detected'] = True
                result['quantization_type'] = 'bitsandbytes (wrapped)'
            
            # Get model config info
            if hasattr(model, 'config'):
                config_dict = {
                    'model_type': getattr(model.config, 'model_type', None),
                    'vocab_size': getattr(model.config, 'vocab_size', None),
                    'max_position_embeddings': getattr(model.config, 'max_position_embeddings', None),
                }
                result['model_config'] = config_dict
            
            # Check strategy settings
            result['strategy_use_quantization'] = strategy.use_quantization
            result['strategy_quantization_bits'] = strategy.quantization_bits
            result['strategy_device'] = strategy.device
            
        else:
            logger.info("Model not loaded yet. Strategy configuration:")
            logger.info(f"  - use_quantization: {strategy.use_quantization}")
            logger.info(f"  - quantization_bits: {strategy.quantization_bits}")
            logger.info(f"  - device: {strategy.device}")
            
    except ImportError as e:
        logger.error(f"Failed to import inference_core: {e}")
    except Exception as e:
        logger.error(f"Error checking model quantization: {e}")
    
    return result


def generate_report(env_vars: Dict[str, Any], torch_info: Dict[str, Any], 
                   bnb_info: Dict[str, Any], model_info: Dict[str, Any]) -> str:
    """Generate a human-readable report."""
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("Qwen3 Quantization Verification Report")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    # Environment Variables
    report_lines.append("Environment Variables:")
    report_lines.append(f"  USE_QUANTIZATION: {env_vars['USE_QUANTIZATION']}")
    report_lines.append(f"  QUANTIZATION_BITS: {env_vars['QUANTIZATION_BITS']}")
    report_lines.append(f"  MODEL_DEVICE: {env_vars['MODEL_DEVICE']}")
    report_lines.append(f"  MODEL_NAME: {env_vars['MODEL_NAME']}")
    report_lines.append(f"  MAX_CONTEXT_LENGTH: {env_vars['MAX_CONTEXT_LENGTH']}")
    report_lines.append("")
    
    # PyTorch/CUDA Info
    report_lines.append("PyTorch/CUDA Status:")
    report_lines.append(f"  PyTorch Available: {torch_info['torch_available']}")
    if torch_info['torch_available']:
        report_lines.append(f"  PyTorch Version: {torch_info.get('torch_version', 'unknown')}")
        report_lines.append(f"  CUDA Available: {torch_info['cuda_available']}")
        if torch_info['cuda_available']:
            report_lines.append(f"  CUDA Version: {torch_info.get('cuda_version', 'unknown')}")
            report_lines.append(f"  GPU Count: {torch_info['gpu_count']}")
            if torch_info['gpu_count'] > 0:
                report_lines.append(f"  GPU Name: {torch_info.get('gpu_name', 'unknown')}")
                if torch_info.get('gpu_memory_total_gb'):
                    report_lines.append(f"  GPU Memory Total: {torch_info['gpu_memory_total_gb']:.2f} GB")
                if torch_info.get('gpu_memory_allocated_gb'):
                    report_lines.append(f"  GPU Memory Allocated: {torch_info['gpu_memory_allocated_gb']:.2f} GB")
                if torch_info.get('gpu_memory_reserved_gb'):
                    report_lines.append(f"  GPU Memory Reserved: {torch_info['gpu_memory_reserved_gb']:.2f} GB")
                if torch_info.get('gpu_compute_capability'):
                    major, minor = torch_info['gpu_compute_capability']
                    report_lines.append(f"  GPU Compute Capability: {major}.{minor} (sm_{major}{minor})")
    report_lines.append("")
    
    # BitsAndBytes Info
    report_lines.append("BitsAndBytes Status:")
    report_lines.append(f"  BitsAndBytes Available: {bnb_info['bitsandbytes_available']}")
    if bnb_info['bitsandbytes_available']:
        report_lines.append(f"  BitsAndBytes Version: {bnb_info.get('bitsandbytes_version', 'unknown')}")
    report_lines.append("")
    
    # Model Status
    report_lines.append("Model Status:")
    report_lines.append(f"  Model Loaded: {model_info['model_loaded']}")
    if model_info['model_loaded']:
        report_lines.append(f"  Model Device: {model_info.get('model_device', 'unknown')}")
        report_lines.append(f"  Model Dtype: {model_info.get('model_dtype', 'unknown')}")
        report_lines.append(f"  Quantization Detected: {model_info['quantization_detected']}")
        if model_info['quantization_detected']:
            report_lines.append(f"  Quantization Type: {model_info.get('quantization_type', 'unknown')}")
        report_lines.append(f"  Strategy Use Quantization: {model_info.get('strategy_use_quantization', 'unknown')}")
        report_lines.append(f"  Strategy Quantization Bits: {model_info.get('strategy_quantization_bits', 'unknown')}")
        report_lines.append(f"  Strategy Device: {model_info.get('strategy_device', 'unknown')}")
    else:
        report_lines.append(f"  Strategy Use Quantization: {model_info.get('strategy_use_quantization', 'unknown')}")
        report_lines.append(f"  Strategy Quantization Bits: {model_info.get('strategy_quantization_bits', 'unknown')}")
        report_lines.append(f"  Strategy Device: {model_info.get('strategy_device', 'unknown')}")
    report_lines.append("")
    
    # Verification Summary
    report_lines.append("Verification Summary:")
    quantization_configured = env_vars['USE_QUANTIZATION']
    quantization_bits = env_vars['QUANTIZATION_BITS']
    
    if not torch_info['cuda_available']:
        report_lines.append("  ⚠️  CUDA not available - quantization requires GPU")
    elif not bnb_info['bitsandbytes_available']:
        report_lines.append("  ⚠️  BitsAndBytes not available - quantization will not work")
    elif quantization_configured and quantization_bits in [4, 8]:
        if model_info['model_loaded']:
            if model_info['quantization_detected']:
                detected_bits = model_info.get('quantization_type', '')
                expected_bits = f"{quantization_bits}-bit"
                if expected_bits in detected_bits or str(quantization_bits) in detected_bits:
                    report_lines.append(f"  ✅ Quantization configured and active: {quantization_bits}-bit")
                else:
                    report_lines.append(f"  ⚠️  Quantization configured ({quantization_bits}-bit) but detected type: {model_info.get('quantization_type', 'unknown')}")
            else:
                report_lines.append(f"  ⚠️  Quantization configured ({quantization_bits}-bit) but not detected in loaded model")
        else:
            report_lines.append(f"  ℹ️  Quantization configured ({quantization_bits}-bit) - model not loaded yet")
    elif not quantization_configured:
        report_lines.append("  ℹ️  Quantization not configured (USE_QUANTIZATION=false)")
    else:
        report_lines.append(f"  ⚠️  Invalid quantization bits: {quantization_bits} (expected 4 or 8)")
    
    report_lines.append("")
    report_lines.append("=" * 80)
    
    return "\n".join(report_lines)


class VerifyQwen3Command(Command):
    """Command for verifying Qwen3 quantization settings and model performance."""
    
    @classmethod
    def get_name(cls) -> str:
        return "verify-qwen3"
    
    @classmethod
    def get_description(cls) -> str:
        return "Verify Qwen3 quantization settings and monitor model performance"
    
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output results as JSON",
        )
    
    def init(self) -> None:
        """Initialize verify Qwen3 command."""
        # No initialization needed for this tool
        pass
    
    def run(self) -> None:
        """Run the verification and generate report."""
        logger.info("Starting Qwen3 quantization verification...")
        
        # Check environment variables
        env_vars = check_environment_variables()
        
        # Check PyTorch/CUDA
        torch_info = check_torch_availability()
        
        # Check BitsAndBytes
        bnb_info = check_bitsandbytes_availability()
        
        # Check model quantization status
        model_info = check_model_quantization_status()
        
        # Generate and print report
        report = generate_report(env_vars, torch_info, bnb_info, model_info)
        print(report)
        
        # Also output JSON if requested
        if self.args.json:
            output = {
                'environment_variables': env_vars,
                'torch_info': torch_info,
                'bitsandbytes_info': bnb_info,
                'model_info': model_info,
            }
            print("\n" + "=" * 80)
            print("JSON Output:")
            print("=" * 80)
            print(json.dumps(output, indent=2, default=str))
    
    def cleanup(self) -> None:
        """Clean up verify Qwen3 command."""
        # No cleanup needed for this tool
        pass
