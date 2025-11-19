"""
Service command implementations.

Each service is implemented as a command that can be run via:
    poetry run -m essence <service-name>
    
Commands are discovered via reflection - they must be:
1. Subclasses of essence.command.Command
2. Located in this package (essence.commands)
3. Have a get_name() class method that returns the command name
"""

# Import command modules so they're available for reflection
from . import telegram_service  # noqa: F401
from . import discord_service  # noqa: F401
from . import tts_service  # noqa: F401
from . import stt_service  # noqa: F401
from . import inference_api_service  # noqa: F401
from . import review_sandbox  # noqa: F401
from . import monitor_gpu  # noqa: F401
from . import verify_qwen3  # noqa: F401
from . import download_models  # noqa: F401
from . import benchmark_qwen3  # noqa: F401
from . import run_benchmarks  # noqa: F401
from . import generate_alice_dataset  # noqa: F401
from . import integration_test_service  # noqa: F401
from . import coding_agent  # noqa: F401
from . import check_environment  # noqa: F401
from . import get_message_history  # noqa: F401
from . import manage_tensorrt_llm  # noqa: F401
from . import setup_triton_repository  # noqa: F401
from . import verify_tensorrt_llm  # noqa: F401
from . import verify_nim  # noqa: F401
from . import compile_model  # noqa: F401

__all__ = [
    "telegram_service",
    "discord_service",
    "tts_service",
    "stt_service",
    "inference_api_service",
    "review_sandbox",
    "monitor_gpu",
    "verify_qwen3",
    "download_models",
    "benchmark_qwen3",
    "run_benchmarks",
    "generate_alice_dataset",
    "integration_test_service",
    "coding_agent",
    "check_environment",
    "get_message_history",
    "manage_tensorrt_llm",
    "setup_triton_repository",
    "verify_tensorrt_llm",
    "verify_nim",
    "compile_model",
]
