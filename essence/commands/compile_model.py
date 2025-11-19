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
        'files_found': [],
        'missing_files': [],
        'ready_for_loading': False
    }
    
    if not model_dir.exists():
        return False, f"Model directory does not exist: {model_dir}", details
    
    # Check for config.pbtxt
    config_file = model_dir / "config.pbtxt"
    if config_file.exists():
        details['has_config'] = True
        details['files_found'].append('config.pbtxt')
    else:
        details['missing_files'].append('config.pbtxt')
    
    # Check for engine files (typical TensorRT-LLM output)
    engine_files = list(model_dir.glob("*.engine"))
    if engine_files:
        details['has_engine_files'] = True
        details['files_found'].extend([f.name for f in engine_files])
    else:
        details['missing_files'].append('*.engine files')
    
    # Check for tokenizer files
    tokenizer_files = list(model_dir.glob("tokenizer*.json")) + list(model_dir.glob("vocab*.json"))
    if tokenizer_files:
        details['has_tokenizer'] = True
        details['files_found'].extend([f.name for f in tokenizer_files])
    else:
        details['missing_files'].append('tokenizer files (tokenizer*.json or vocab*.json)')
    
    # Model is ready for loading if all critical files are present
    details['ready_for_loading'] = details['has_config'] and details['has_engine_files'] and details['has_tokenizer']
    
    if details['ready_for_loading']:
        return True, f"Model is ready for loading (all required files present)", details
    elif details['has_config'] and details['has_engine_files']:
        return True, f"Model appears to be compiled (found config.pbtxt and engine files, but missing tokenizer files)", details
    elif details['has_config']:
        return False, "Model directory exists but missing engine files (compilation incomplete)", details
    else:
        return False, "Model directory exists but missing required files (needs compilation)", details


def check_model_readiness(model_name: str, repository_path: str = "/home/rlee/models/triton-repository") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Comprehensive check to verify if model is ready for loading into Triton.
    
    Checks for:
    - Model directory exists
    - config.pbtxt is present
    - Engine files are present
    - Tokenizer files are present
    - Config.pbtxt is valid (basic syntax check)
    
    Returns:
        Tuple of (ready, message, details_dict)
    """
    model_dir = Path(repository_path) / model_name / "1"
    details = {
        'model_name': model_name,
        'model_dir': str(model_dir),
        'checks': {},
        'ready': False,
        'issues': []
    }
    
    # Check 1: Directory exists
    if not model_dir.exists():
        details['checks']['directory'] = {'success': False, 'message': f"Model directory does not exist: {model_dir}"}
        details['issues'].append("Model directory does not exist")
        return False, "Model directory does not exist", details
    details['checks']['directory'] = {'success': True, 'message': f"Model directory exists: {model_dir}"}
    
    # Check 2: config.pbtxt exists and is readable
    config_file = model_dir / "config.pbtxt"
    if not config_file.exists():
        details['checks']['config'] = {'success': False, 'message': "config.pbtxt not found"}
        details['issues'].append("Missing config.pbtxt")
    else:
        # Basic validation: check if file is readable and not empty
        try:
            config_content = config_file.read_text()
            if len(config_content.strip()) == 0:
                details['checks']['config'] = {'success': False, 'message': "config.pbtxt is empty"}
                details['issues'].append("config.pbtxt is empty")
            elif 'name:' not in config_content or 'platform:' not in config_content:
                details['checks']['config'] = {'success': False, 'message': "config.pbtxt appears invalid (missing required fields)"}
                details['issues'].append("config.pbtxt appears invalid")
            else:
                details['checks']['config'] = {'success': True, 'message': "config.pbtxt exists and appears valid"}
        except Exception as e:
            details['checks']['config'] = {'success': False, 'message': f"Error reading config.pbtxt: {e}"}
            details['issues'].append(f"Cannot read config.pbtxt: {e}")
    
    # Check 3: Engine files exist
    engine_files = list(model_dir.glob("*.engine"))
    if not engine_files:
        details['checks']['engine_files'] = {'success': False, 'message': "No .engine files found"}
        details['issues'].append("Missing TensorRT-LLM engine files")
    else:
        details['checks']['engine_files'] = {'success': True, 'message': f"Found {len(engine_files)} engine file(s)"}
    
    # Check 4: Tokenizer files exist
    tokenizer_files = list(model_dir.glob("tokenizer*.json")) + list(model_dir.glob("vocab*.json"))
    if not tokenizer_files:
        details['checks']['tokenizer'] = {'success': False, 'message': "No tokenizer files found"}
        details['issues'].append("Missing tokenizer files")
    else:
        details['checks']['tokenizer'] = {'success': True, 'message': f"Found {len(tokenizer_files)} tokenizer file(s)"}
    
    # Overall readiness
    all_checks_passed = all(
        check.get('success', False) 
        for check in details['checks'].values()
    )
    details['ready'] = all_checks_passed
    
    if all_checks_passed:
        return True, "✅ Model is ready for loading! All required files are present and valid.", details
    else:
        return False, f"❌ Model is not ready for loading. {len(details['issues'])} issue(s) found.", details


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
    
    # Find the actual HuggingFace cache location
    model_cache_dir = "/home/rlee/models"
    hf_cache_pattern = f"models--{model_hf_name.replace('/', '--')}"
    hf_model_path = f"/models/{hf_cache_pattern}"
    
    template = f"""# Model Compilation Template for {model_name}

## Prerequisites
- NVIDIA GPU with 20GB+ VRAM
- TensorRT-LLM build tools (in Docker container or installed)
- Model downloaded to {hf_model_path} (HuggingFace cache format)
- Model repository structure created at /models/triton-repository/{model_name}/1/
- HuggingFace cache environment variables set (HF_HOME=/models, TRANSFORMERS_CACHE=/models)

## Compilation Steps

### Option 1: Using TensorRT-LLM Docker Container (Recommended)

```bash
# Run TensorRT-LLM build container with HuggingFace cache mounted
docker run --rm --gpus all \\
  -v /home/rlee/models:/models \\
  -v /home/rlee/dev/june:/workspace \\
  -e HF_HOME=/models \\
  -e TRANSFORMERS_CACHE=/models \\
  -e HF_HUB_CACHE=/models \\
  nvcr.io/nvidia/tensorrt-llm:latest \\
  trtllm-build \\
    --checkpoint_dir /models/{hf_cache_pattern} \\
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
# Set HuggingFace cache environment variables
export HF_HOME=/models
export TRANSFORMERS_CACHE=/models
export HF_HUB_CACHE=/models

python3 -m tensorrt_llm.build \\
  --checkpoint_dir /models/{hf_cache_pattern} \\
  --output_dir /models/triton-repository/{model_name}/1/ \\
  --quantization int8 \\
  --max_batch_size 1 \\
  --max_input_len 131072 \\
  --max_output_len 2048
```

### Option 3: Using trtllm-build Command

```bash
# Set HuggingFace cache environment variables
export HF_HOME=/models
export TRANSFORMERS_CACHE=/models
export HF_HUB_CACHE=/models

trtllm-build \\
  --checkpoint_dir /models/{hf_cache_pattern} \\
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


def check_tokenizer_files(model_hf_name: str, model_cache_dir: str = "/home/rlee/models") -> Tuple[bool, str, List[str]]:
    """
    Check if tokenizer files exist in the HuggingFace model directory.
    
    Args:
        model_hf_name: HuggingFace model name (e.g., "Qwen/Qwen3-30B-A3B-Thinking-2507")
        model_cache_dir: Base model cache directory (default: /home/rlee/models)
    
    Returns:
        Tuple of (files_exist, message, list_of_tokenizer_files)
    """
    import glob
    
    # Common tokenizer file patterns
    tokenizer_patterns = [
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
        "merges.txt",
        "special_tokens_map.json",
        "added_tokens.json",
        "tokenizer.model",
        "vocab.txt"
    ]
    
    # Try to find the model directory
    # HuggingFace cache structure: models/huggingface/hub/models--{org}--{model}/
    model_cache_path = Path(model_cache_dir)
    model_dir_pattern = model_cache_path / "huggingface" / "hub" / f"models--{model_hf_name.replace('/', '--')}"
    
    # Check if directory exists
    if not model_dir_pattern.exists():
        # Try alternative: direct model name directory
        model_dir_pattern = model_cache_path / model_hf_name.replace("/", "--")
        if not model_dir_pattern.exists():
            return False, f"Model directory not found: {model_hf_name}", []
    
    # Search for tokenizer files
    found_files = []
    for pattern in tokenizer_patterns:
        # Search recursively
        matches = list(model_dir_pattern.rglob(pattern))
        if matches:
            found_files.extend([str(f.relative_to(model_dir_pattern)) for f in matches])
    
    if found_files:
        return True, f"Found {len(found_files)} tokenizer file(s)", found_files
    else:
        return False, "No tokenizer files found", []


def generate_tokenizer_copy_commands(
    model_name: str,
    model_hf_name: str,
    repository_path: str = "/home/rlee/models/triton-repository",
    model_cache_dir: str = "/home/rlee/models"
) -> str:
    """
    Generate commands to copy tokenizer files from HuggingFace model to Triton repository.
    
    Args:
        model_name: Local model name (e.g., "qwen3-30b")
        model_hf_name: HuggingFace model name (e.g., "Qwen/Qwen3-30B-A3B-Thinking-2507")
        repository_path: Path to Triton repository
        model_cache_dir: Base model cache directory
    
    Returns:
        String with copy commands
    """
    # Check if tokenizer files exist
    files_exist, msg, tokenizer_files = check_tokenizer_files(model_hf_name, model_cache_dir)
    
    # Find model directory
    model_dir_pattern = Path(model_cache_dir) / "huggingface" / "hub" / f"models--{model_hf_name.replace('/', '--')}"
    if not model_dir_pattern.exists():
        model_dir_pattern = Path(model_cache_dir) / model_hf_name.replace("/", "--")
    
    target_dir = Path(repository_path) / model_name / "1"
    
    if not files_exist:
        return f"""# Tokenizer Files Not Found

⚠️  Could not find tokenizer files for {model_hf_name} in {model_cache_dir}

**Manual Steps:**
1. Locate the HuggingFace model directory (usually in {model_cache_dir}/huggingface/hub/)
2. Find tokenizer files (tokenizer.json, tokenizer_config.json, vocab.json, etc.)
3. Copy them to: {target_dir}

**Example:**
```bash
# Find model directory
find {model_cache_dir}/huggingface -name "*{model_hf_name.split('/')[-1]}*" -type d

# Copy tokenizer files (adjust paths as needed)
cp <model_dir>/tokenizer*.json {target_dir}/
cp <model_dir>/vocab*.json {target_dir}/
```
"""
    
    # Generate copy commands
    commands = [f"# Copy Tokenizer Files for {model_name}"]
    commands.append("")
    commands.append(f"# Source: {model_dir_pattern}")
    commands.append(f"# Target: {target_dir}")
    commands.append("")
    commands.append("```bash")
    
    # Generate individual copy commands
    for file in tokenizer_files:
        source_file = model_dir_pattern / file
        target_file = target_dir / Path(file).name
        commands.append(f"cp '{source_file}' '{target_file}'")
    
    # Or use rsync for all files at once
    commands.append("")
    commands.append("# Or copy all tokenizer files at once:")
    commands.append(f"rsync -av '{model_dir_pattern}/'tokenizer* '{model_dir_pattern}/'vocab* '{target_dir}/'")
    
    commands.append("```")
    commands.append("")
    commands.append(f"**Found {len(tokenizer_files)} tokenizer file(s):**")
    for file in tokenizer_files:
        commands.append(f"- {file}")
    
    return "\n".join(commands)


def generate_config_pbtxt(model_name: str, max_batch_size: int = 0, max_input_len: int = 131072) -> str:
    """
    Generate a config.pbtxt template for Triton Inference Server.
    
    Args:
        model_name: Local model name (e.g., "qwen3-30b")
        max_batch_size: Maximum batch size (0 for dynamic batching)
        max_input_len: Maximum input sequence length
    
    Returns:
        config.pbtxt content as string
    """
    config = f"""name: "{model_name}"
platform: "tensorrt_llm"
max_batch_size: {max_batch_size}

input [
  {{
    name: "text_input"
    data_type: TYPE_STRING
    dims: [ -1 ]
  }}
]

output [
  {{
    name: "text_output"
    data_type: TYPE_STRING
    dims: [ -1 ]
  }}
]

instance_group [
  {{
    count: 1
    kind: KIND_GPU
  }}
]

parameters [
  {{
    key: "max_tokens"
    value: {{
      string_value: "2048"
    }}
  }},
  {{
    key: "temperature"
    value: {{
      string_value: "0.7"
    }}
  }},
  {{
    key: "top_p"
    value: {{
      string_value: "0.9"
    }}
  }},
  {{
    key: "top_k"
    value: {{
      string_value: "50"
    }}
  }},
  {{
    key: "max_input_len"
    value: {{
      string_value: "{max_input_len}"
    }}
  }}
]
"""
    return config


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
            '--generate-config',
            action='store_true',
            help='Generate config.pbtxt template file'
        )
        self.parser.add_argument(
            '--generate-tokenizer-commands',
            action='store_true',
            help='Generate commands to copy tokenizer files'
        )
        self.parser.add_argument(
            '--check-readiness',
            action='store_true',
            help='Check if model is ready for loading (validates all required files are present)'
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
        
        # Generate config.pbtxt
        if self.args.generate_config:
            config_content = generate_config_pbtxt(model_name)
            config_path = Path(self.args.repository_path) / model_name / "1" / "config.pbtxt"
            
            if not self.args.json:
                print("\n" + "="*70)
                print("CONFIG.PBTXT TEMPLATE")
                print("="*70)
                print(config_content)
                print("\n" + "="*70)
                
                # Ask if user wants to save it
                if config_path.parent.exists():
                    try:
                        config_path.write_text(config_content)
                        print(f"✅ Saved config.pbtxt to: {config_path}")
                        print(f"\n📝 Next steps:")
                        print(f"   1. Review and adjust config.pbtxt if needed")
                        print(f"   2. Compile the model using TensorRT-LLM build tools")
                        print(f"   3. Copy tokenizer files to the model directory")
                        print(f"   4. Load the model: poetry run -m essence manage-tensorrt-llm --action load --model {model_name}")
                    except Exception as e:
                        print(f"⚠️  Could not save config.pbtxt to {config_path}: {e}")
                        print("   Please save the config.pbtxt content manually to the model directory")
                else:
                    print(f"⚠️  Model directory does not exist: {config_path.parent}")
                    print("   Please create the repository structure first:")
                    print(f"   poetry run -m essence setup-triton-repository --action create --model {model_name}")
                    print("\n   Then save the config.pbtxt content above to:")
                    print(f"   {config_path}")
            else:
                results['config_pbtxt'] = config_content
                results['config_path'] = str(config_path)
        
        # Output JSON if requested
        if self.args.json:
            print(json.dumps(results, indent=2))
            sys.exit(0)
        
        # Generate tokenizer copy commands
        if self.args.generate_tokenizer_commands:
            tokenizer_commands = generate_tokenizer_copy_commands(
                model_name,
                self.args.model_hf_name or model_name,
                self.args.repository_path,
                os.getenv("MODEL_CACHE_DIR", "/home/rlee/models")
            )
            if not self.args.json:
                print("\n" + "="*70)
                print("TOKENIZER FILE COPY COMMANDS")
                print("="*70)
                print(tokenizer_commands)
            else:
                results['tokenizer_commands'] = tokenizer_commands
        
        # Check readiness (comprehensive check for loading)
        if self.args.check_readiness:
            print("\n🔍 Checking if model is ready for loading...\n")
            ready, msg, readiness_details = check_model_readiness(model_name, self.args.repository_path)
            results['readiness'] = {
                'ready': ready,
                'message': msg,
                'details': readiness_details
            }
            
            if not self.args.json:
                # Print individual checks
                for check_name, check_result in readiness_details['checks'].items():
                    status = "✅" if check_result.get('success', False) else "❌"
                    print(f"{status} {check_name.replace('_', ' ').title()}: {check_result.get('message', '')}")
                
                print(f"\n{msg}")
                
                if not ready and readiness_details.get('issues'):
                    print("\nIssues to fix:")
                    for issue in readiness_details['issues']:
                        print(f"  - {issue}")
                    
                    print("\n💡 Next steps:")
                    if not readiness_details['checks'].get('config', {}).get('success'):
                        print("  1. Generate config.pbtxt: --generate-config")
                    if not readiness_details['checks'].get('engine_files', {}).get('success'):
                        print("  2. Compile the model using TensorRT-LLM build tools: --generate-template")
                    if not readiness_details['checks'].get('tokenizer', {}).get('success'):
                        print("  3. Copy tokenizer files: --generate-tokenizer-commands")
                elif ready:
                    print("\n🚀 Ready to load! Use:")
                    print(f"   poetry run -m essence manage-tensorrt-llm --action load --model {model_name}")
            else:
                results['readiness'] = readiness_details
        
        # Default: show summary
        if not self.args.check_prerequisites and not self.args.generate_template and not self.args.generate_config and not self.args.generate_tokenizer_commands and not self.args.check_readiness:
            print("Model compilation helper for TensorRT-LLM")
            print(f"\nModel: {model_name}")
            print("\nUse --check-prerequisites to validate setup")
            print("Use --generate-template to get compilation command template")
            print("Use --generate-config to generate config.pbtxt template")
            print("Use --generate-tokenizer-commands to get tokenizer file copy commands")
            print("Use --check-readiness to verify model is ready for loading")
            print("\nExample:")
            print(f"  poetry run -m essence compile-model --model {model_name} --check-prerequisites --generate-template --generate-config --generate-tokenizer-commands")
            print(f"  poetry run -m essence compile-model --model {model_name} --check-readiness  # After compilation")
        
        sys.exit(0)
