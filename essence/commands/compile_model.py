"""
Model compilation helper command - Validates prerequisites and provides guidance for TensorRT-LLM model compilation.

Usage:
    poetry run -m essence compile-model --model qwen3-30b [--check-prerequisites] [--generate-template]

This command helps with Phase 15 Task 4: Model compilation for TensorRT-LLM.
It validates prerequisites, checks model repository structure, and provides compilation guidance.

Note: Actual model compilation requires TensorRT-LLM build tools and must be done manually
or via external scripts. This command provides validation and guidance only.
"""
import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from essence.command import Command
from essence.commands.setup_triton_repository import TritonRepositoryManager

logger = logging.getLogger(__name__)


def check_tensorrt_llm_build_tools() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if TensorRT-LLM build tools are available.
    
    Returns:
        Tuple of (success, message, details_dict)
    """
    details = {
        'tools_available': False,
        'trtllm_build_available': False,
        'python_available': False,
        'docker_available': False,
    }
    
    # Check if we're in a container with TensorRT-LLM build tools
    # TensorRT-LLM build tools are typically available in NVIDIA containers
    try:
        result = subprocess.run(
            ['which', 'trtllm-build'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            details['trtllm_build_available'] = True
            details['tools_available'] = True
    except Exception:
        pass
    
    # Check Python (required for build scripts)
    try:
        result = subprocess.run(
            ['python3', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            details['python_available'] = True
            details['python_version'] = result.stdout.strip()
    except Exception:
        pass
    
    # Check Docker (for containerized builds)
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            details['docker_available'] = True
            details['docker_version'] = result.stdout.strip()
    except Exception:
        pass
    
    if details['tools_available']:
        return True, "TensorRT-LLM build tools available", details
    elif details['docker_available']:
        return False, "TensorRT-LLM build tools not found in PATH (may need to use Docker container)", details
    else:
        return False, "TensorRT-LLM build tools not available", details


def check_model_repository_structure(model_name: str, repository_path: str = "/home/rlee/models/triton-repository") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if model repository structure exists and is valid.
    
    Returns:
        Tuple of (success, message, details_dict)
    """
    manager = TritonRepositoryManager(repository_path=repository_path)
    is_valid, missing_files, message = manager.validate_model_structure(model_name, version="1")
    
    details = {
        'model_name': model_name,
        'repository_path': repository_path,
        'structure_exists': is_valid,
        'missing_files': missing_files,
        'model_dir': str(Path(repository_path) / model_name / "1")
    }
    
    return is_valid, message, details


def check_gpu_availability() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check GPU availability for model compilation.
    
    Returns:
        Tuple of (success, message, details_dict)
    """
    details = {
        'gpu_available': False,
        'gpu_count': 0,
        'gpu_info': []
    }
    
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if lines and lines[0]:
                details['gpu_available'] = True
                details['gpu_count'] = len(lines)
                for line in lines:
                    parts = line.split(', ')
                    if len(parts) >= 3:
                        details['gpu_info'].append({
                            'name': parts[0],
                            'memory_total': parts[1],
                            'memory_free': parts[2]
                        })
                return True, f"GPU available: {len(lines)} GPU(s) detected", details
        return False, "nvidia-smi not available or no GPUs detected", details
        
    except FileNotFoundError:
        return False, "nvidia-smi not found (GPU may not be available)", details
    except subprocess.TimeoutExpired:
        return False, "nvidia-smi timeout (GPU check failed)", details
    except Exception as e:
        return False, f"Error checking GPU: {e}", details


def check_model_files(model_name: str, repository_path: str = "/home/rlee/models/triton-repository") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if model files are already compiled and present.
    
    Returns:
        Tuple of (success, message, details_dict)
    """
    model_dir = Path(repository_path) / model_name / "1"
    details = {
        'model_dir': str(model_dir),
        'exists': model_dir.exists(),
        'has_config': False,
        'has_engine_files': False,
        'has_tokenizer': False,
        'files_found': []
    }
    
    if not model_dir.exists():
        return False, f"Model directory does not exist: {model_dir}", details
    
    # Check for config.pbtxt
    config_file = model_dir / "config.pbtxt"
    if config_file.exists():
        details['has_config'] = True
        details['files_found'].append('config.pbtxt')
    
    # Check for engine files (typical TensorRT-LLM output)
    engine_files = list(model_dir.glob("*.engine"))
    if engine_files:
        details['has_engine_files'] = True
        details['files_found'].extend([f.name for f in engine_files])
    
    # Check for tokenizer files
    tokenizer_files = list(model_dir.glob("tokenizer*.json")) + list(model_dir.glob("vocab*.json"))
    if tokenizer_files:
        details['has_tokenizer'] = True
        details['files_found'].extend([f.name for f in tokenizer_files])
    
    if details['has_config'] and details['has_engine_files']:
        return True, f"Model appears to be compiled (found config.pbtxt and engine files)", details
    elif details['has_config']:
        return False, "Model directory exists but missing engine files (compilation incomplete)", details
    else:
        return False, "Model directory exists but missing required files (needs compilation)", details


def generate_compilation_template(model_name: str, model_hf_name: str = None) -> str:
    """
    Generate a compilation command template for the model.
    
    Args:
        model_name: Local model name (e.g., "qwen3-30b")
        model_hf_name: HuggingFace model name (e.g., "Qwen/Qwen3-30B-A3B-Thinking-2507")
    
    Returns:
        Template string with compilation instructions
    """
    if not model_hf_name:
        # Try to infer from model_name
        if "qwen3-30b" in model_name.lower():
            model_hf_name = "Qwen/Qwen3-30B-A3B-Thinking-2507"
        else:
            model_hf_name = f"<HUGGINGFACE_MODEL_NAME>"
    
    template = f"""# Model Compilation Template for {model_name}

## Prerequisites
- NVIDIA GPU with 20GB+ VRAM
- TensorRT-LLM build tools (in Docker container or installed)
- Model downloaded to /home/rlee/models/{model_hf_name}
- Model repository structure created at /home/rlee/models/triton-repository/{model_name}/1/

## Compilation Steps

### Option 1: Using TensorRT-LLM Docker Container (Recommended)

```bash
# Run TensorRT-LLM build container
docker run --rm --gpus all \\
  -v /home/rlee/models:/models \\
  -v /home/rlee/dev/june:/workspace \\
  nvcr.io/nvidia/tensorrt-llm:latest \\
  trtllm-build \\
    --checkpoint_dir /models/{model_hf_name} \\
    --output_dir /models/triton-repository/{model_name}/1/ \\
    --gemm_plugin float16 \\
    --gpt_attention_plugin float16 \\
    --context_fmha enable \\
    --quantization int8 \\
    --max_batch_size 1 \\
    --max_input_len 131072 \\
    --max_output_len 2048
```

### Option 2: Using Python Build Script

```bash
# In a container with TensorRT-LLM installed
python3 -m tensorrt_llm.build \\
  --checkpoint_dir /models/{model_hf_name} \\
  --output_dir /models/triton-repository/{model_name}/1/ \\
  --quantization int8 \\
  --max_batch_size 1 \\
  --max_input_len 131072 \\
  --max_output_len 2048
```

### Option 3: Using trtllm-build Command

```bash
trtllm-build \\
  --checkpoint_dir /models/{model_hf_name} \\
  --output_dir /models/triton-repository/{model_name}/1/ \\
  --quantization int8 \\
  --max_batch_size 1 \\
  --max_input_len 131072 \\
  --max_output_len 2048
```

## After Compilation

1. **Create config.pbtxt** in the model directory (see setup-triton-repository README.md)
2. **Copy tokenizer files** from HuggingFace model to model directory
3. **Validate structure**: `poetry run -m essence setup-triton-repository --action validate --model {model_name}`
4. **Load model**: `poetry run -m essence manage-tensorrt-llm --action load --model {model_name}`

## Notes

- Replace `<HUGGINGFACE_MODEL_NAME>` with actual model name if different
- Adjust quantization (int8/int4) based on GPU memory
- Adjust max_input_len/max_output_len based on requirements
- See TensorRT-LLM documentation for advanced options
"""
    return template


class CompileModelCommand(Command):
    """Command for validating model compilation prerequisites and providing guidance."""
    
    @classmethod
    def get_name(cls) -> str:
        return "compile-model"
    
    def init(self) -> None:
        """Initialize command arguments."""
        self.parser = argparse.ArgumentParser(
            description="Validate prerequisites and provide guidance for TensorRT-LLM model compilation",
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        self.parser.add_argument(
            '--model',
            type=str,
            required=True,
            help='Model name (e.g., qwen3-30b)'
        )
        self.parser.add_argument(
            '--model-hf-name',
            type=str,
            default=None,
            help='HuggingFace model name (e.g., Qwen/Qwen3-30B-A3B-Thinking-2507)'
        )
        self.parser.add_argument(
            '--repository-path',
            type=str,
            default='/home/rlee/models/triton-repository',
            help='Path to Triton model repository (default: /home/rlee/models/triton-repository)'
        )
        self.parser.add_argument(
            '--check-prerequisites',
            action='store_true',
            help='Check all prerequisites for model compilation'
        )
        self.parser.add_argument(
            '--generate-template',
            action='store_true',
            help='Generate compilation command template'
        )
        self.parser.add_argument(
            '--json',
            action='store_true',
            help='Output results as JSON'
        )
        
        self.args = self.parser.parse_args()
    
    def run(self) -> None:
        """Run the compilation helper command."""
        import json
        
        model_name = self.args.model
        results = {
            'model_name': model_name,
            'checks': {},
            'ready': False,
            'issues': []
        }
        
        # Check prerequisites
        if self.args.check_prerequisites:
            print("🔍 Checking prerequisites for model compilation...\n")
            
            # Check GPU
            gpu_ok, gpu_msg, gpu_details = check_gpu_availability()
            results['checks']['gpu'] = {
                'success': gpu_ok,
                'message': gpu_msg,
                'details': gpu_details
            }
            status = "✅" if gpu_ok else "❌"
            print(f"{status} GPU: {gpu_msg}")
            if not gpu_ok:
                results['issues'].append(f"GPU: {gpu_msg}")
            
            # Check model repository structure
            repo_ok, repo_msg, repo_details = check_model_repository_structure(
                model_name, self.args.repository_path
            )
            results['checks']['repository'] = {
                'success': repo_ok,
                'message': repo_msg,
                'details': repo_details
            }
            status = "✅" if repo_ok else "❌"
            print(f"{status} Repository Structure: {repo_msg}")
            if not repo_ok:
                results['issues'].append(f"Repository: {repo_msg}")
            
            # Check TensorRT-LLM build tools
            tools_ok, tools_msg, tools_details = check_tensorrt_llm_build_tools()
            results['checks']['build_tools'] = {
                'success': tools_ok,
                'message': tools_msg,
                'details': tools_details
            }
            status = "✅" if tools_ok else "⚠️"
            print(f"{status} Build Tools: {tools_msg}")
            if not tools_ok:
                results['issues'].append(f"Build Tools: {tools_msg}")
            
            # Check if model is already compiled
            compiled_ok, compiled_msg, compiled_details = check_model_files(
                model_name, self.args.repository_path
            )
            results['checks']['compiled'] = {
                'success': compiled_ok,
                'message': compiled_msg,
                'details': compiled_details
            }
            if compiled_ok:
                status = "✅"
                print(f"\n{status} Model Status: {compiled_msg}")
                print(f"\n📁 Model directory: {compiled_details['model_dir']}")
                print(f"📄 Files found: {', '.join(compiled_details['files_found'])}")
                print("\n✅ Model appears to be compiled! You can skip compilation and proceed to loading.")
            else:
                status = "❌"
                print(f"\n{status} Model Status: {compiled_msg}")
            
            # Overall readiness
            critical_checks = [gpu_ok, repo_ok]
            if all(critical_checks) and not compiled_ok:
                results['ready'] = True
                print("\n✅ Prerequisites check passed! Ready for compilation.")
            elif compiled_ok:
                print("\n✅ Model is already compiled! No compilation needed.")
            else:
                print("\n❌ Prerequisites check failed. Please fix issues before compilation.")
                print("\nIssues to fix:")
                for issue in results['issues']:
                    print(f"  - {issue}")
        
        # Generate template
        if self.args.generate_template:
            template = generate_compilation_template(
                model_name,
                self.args.model_hf_name
            )
            if not self.args.json:
                print("\n" + "="*70)
                print("COMPILATION COMMAND TEMPLATE")
                print("="*70)
                print(template)
            else:
                results['template'] = template
        
        # Output JSON if requested
        if self.args.json:
            print(json.dumps(results, indent=2))
            sys.exit(0)
        
        # Default: show summary
        if not self.args.check_prerequisites and not self.args.generate_template:
            print("Model compilation helper for TensorRT-LLM")
            print(f"\nModel: {model_name}")
            print("\nUse --check-prerequisites to validate setup")
            print("Use --generate-template to get compilation command template")
            print("\nExample:")
            print(f"  poetry run -m essence compile-model --model {model_name} --check-prerequisites --generate-template")
        
        sys.exit(0)
