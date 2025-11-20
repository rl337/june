import importlib.util

# Import from utils.py (file) - need to import the file directly, not the utils/ directory
# Use importlib to import the utils.py file as a module
import sys
from pathlib import Path

from .cli import Command
from .cli import main as cli_main
from .config import Config, config
from .runtime import InferenceApp
from .strategies import (
    InferenceRequest,
    InferenceResponse,
    InferenceStrategy,
    LlmStrategy,
    SttStrategy,
    TtsStrategy,
)

# Get the path to utils.py
utils_py_path = Path(__file__).parent / "utils.py"
spec = importlib.util.spec_from_file_location(
    "inference_core._utils", str(utils_py_path)
)
_utils = importlib.util.module_from_spec(spec)
sys.modules["inference_core._utils"] = _utils
spec.loader.exec_module(_utils)

# Import the needed items from utils.py
JSONEncoder = _utils.JSONEncoder
serialize_json = _utils.serialize_json
deserialize_json = _utils.deserialize_json
Timer = _utils.Timer
RateLimiter = _utils.RateLimiter
RetryConfig = _utils.RetryConfig
retry_async = _utils.retry_async
retry_sync = _utils.retry_sync
HealthChecker = _utils.HealthChecker
setup_logging = _utils.setup_logging
get_timestamp = _utils.get_timestamp
generate_id = _utils.generate_id
CircularBuffer = _utils.CircularBuffer
# Import server classes optionally - they require grpc which may not be available
# Also catch AttributeError for scipy/numpy compatibility issues (e.g., _ARRAY_API not found)
try:
    from .servers.llm_server import LlmGrpcApp
    from .servers.stt_server import SttGrpcApp
    from .servers.tts_server import TtsGrpcApp
except (ImportError, AttributeError) as e:
    # grpc not available or scipy/numpy compatibility issue - these classes won't be available
    # Log the error for debugging but don't fail - services can still work without these
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not import gRPC server classes: {e}. Services may not be available.")
    SttGrpcApp = None
    TtsGrpcApp = None
    LlmGrpcApp = None

__all__ = [
    "InferenceStrategy",
    "SttStrategy",
    "TtsStrategy",
    "LlmStrategy",
    "InferenceRequest",
    "InferenceResponse",
    "InferenceApp",
    "SttGrpcApp",
    "TtsGrpcApp",
    "LlmGrpcApp",
]
