"""
Inference-core configuration (migrated from june/shared/config.py)
"""
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    url: str
    host: str = "localhost"
    port: int = 5432
    database: str = "june"
    username: str = "june"
    password: str = "changeme"


@dataclass
class MinIOConfig:
    endpoint: str = "localhost:9000"
    access_key: str = "admin"
    secret_key: str = "changeme"
    bucket_name: str = "june-storage"
    secure: bool = False


@dataclass
class NATSConfig:
    url: str = "nats://localhost:4222"
    max_reconnect_attempts: int = 10
    reconnect_time_wait: int = 2


@dataclass
class ModelConfig:
    name: str = "Qwen/Qwen3-30B-A3B-Thinking-2507"
    device: str = "cuda:0"
    max_context_length: int = 131072
    use_yarn: bool = True
    huggingface_token: Optional[str] = None
    model_cache_dir: str = "/home/rlee/models"
    huggingface_cache_dir: str = "/home/rlee/models/huggingface"
    transformers_cache_dir: str = "/home/rlee/models/transformers"
    # Generation parameters (defaults, can be overridden per request)
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    top_k: Optional[int] = None
    repetition_penalty: Optional[float] = None


@dataclass
class STTConfig:
    model_name: str = "openai/whisper-large-v3"
    device: str = "cuda:0"
    sample_rate: int = 16000
    chunk_length: float = 30.0
    enable_vad: bool = True


@dataclass
class TTSConfig:
    model_name: str = "facebook/fastspeech2-en-ljspeech"
    device: str = "cuda:0"
    sample_rate: int = 22050
    voice_id: str = "default"


@dataclass
class TelegramConfig:
    bot_token: Optional[str] = None
    webhook_url: Optional[str] = None
    max_file_size: int = 20 * 1024 * 1024


@dataclass
class AuthConfig:
    jwt_secret: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    rate_limit_per_minute: int = 60


@dataclass
class MonitoringConfig:
    enable_tracing: bool = True
    enable_metrics: bool = True
    jaeger_endpoint: str = "http://jaeger:14268/api/traces"
    prometheus_port: int = 8000
    log_level: str = "INFO"


class Config:
    def __init__(self, env_file: Optional[str] = None):
        if env_file:
            self._load_env_file(env_file)

        self.database = DatabaseConfig(
            url=os.getenv("POSTGRES_URL", "postgresql://june:changeme@localhost:5432/june"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "june"),
            username=os.getenv("POSTGRES_USER", "june"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme")
        )

        self.minio = MinIOConfig(
            endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "changeme"),
            bucket_name=os.getenv("MINIO_BUCKET", "june-storage"),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true"
        )

        self.nats = NATSConfig(
            url=os.getenv("NATS_URL", "nats://localhost:4222"),
            max_reconnect_attempts=int(os.getenv("NATS_MAX_RECONNECT", "10")),
            reconnect_time_wait=int(os.getenv("NATS_RECONNECT_WAIT", "2"))
        )

        self.model = ModelConfig(
            name=os.getenv("MODEL_NAME", "Qwen/Qwen3-30B-A3B-Thinking-2507"),
            device=os.getenv("MODEL_DEVICE", "cuda:0"),
            max_context_length=int(os.getenv("MAX_CONTEXT_LENGTH", "131072")),
            use_yarn=os.getenv("USE_YARN", "true").lower() == "true",
            huggingface_token=os.getenv("HUGGINGFACE_TOKEN"),
            model_cache_dir=os.getenv("MODEL_CACHE_DIR", "/home/rlee/models"),
            huggingface_cache_dir=os.getenv("HUGGINGFACE_CACHE_DIR", "/home/rlee/models/huggingface"),
            transformers_cache_dir=os.getenv("TRANSFORMERS_CACHE_DIR", "/home/rlee/models/transformers"),
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("MODEL_MAX_TOKENS", "2048")),
            top_p=float(os.getenv("MODEL_TOP_P", "0.9")),
            top_k=int(os.getenv("MODEL_TOP_K")) if os.getenv("MODEL_TOP_K") else None,
            repetition_penalty=float(os.getenv("MODEL_REPETITION_PENALTY")) if os.getenv("MODEL_REPETITION_PENALTY") else None,
        )

        self.stt = STTConfig(
            model_name=os.getenv("STT_MODEL", "openai/whisper-large-v3"),
            device=os.getenv("STT_DEVICE", "cuda:0"),
            sample_rate=int(os.getenv("STT_SAMPLE_RATE", "16000")),
            chunk_length=float(os.getenv("STT_CHUNK_LENGTH", "30.0")),
            enable_vad=os.getenv("STT_ENABLE_VAD", "true").lower() == "true"
        )

        self.tts = TTSConfig(
            model_name=os.getenv("TTS_MODEL", "facebook/fastspeech2-en-ljspeech"),
            device=os.getenv("TTS_DEVICE", "cuda:0"),
            sample_rate=int(os.getenv("TTS_SAMPLE_RATE", "22050")),
            voice_id=os.getenv("TTS_VOICE_ID", "default")
        )

        self.telegram = TelegramConfig(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            max_file_size=int(os.getenv("TELEGRAM_MAX_FILE_SIZE", str(20 * 1024 * 1024)))
        )

        self.auth = AuthConfig(
            jwt_secret=os.getenv("JWT_SECRET", "change-this-secret"),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            jwt_expiration_hours=int(os.getenv("JWT_EXPIRATION_HOURS", "24")),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        )

        self.monitoring = MonitoringConfig(
            enable_tracing=os.getenv("ENABLE_TRACING", "true").lower() == "true",
            enable_metrics=os.getenv("ENABLE_METRICS", "true").lower() == "true",
            jaeger_endpoint=os.getenv("JAEGER_ENDPOINT", "http://jaeger:14268/api/traces"),
            prometheus_port=int(os.getenv("PROMETHEUS_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO")
        )

        self.cuda_visible_devices = os.getenv("CUDA_VISIBLE_DEVICES", "0")
        self.cuda_mps_enable = os.getenv("CUDA_MPS_ENABLE_PER_CTX_SM_PARTITIONING", "1")
        os.environ["CUDA_VISIBLE_DEVICES"] = self.cuda_visible_devices
        os.environ["CUDA_MPS_ENABLE_PER_CTX_SM_PARTITIONING"] = self.cuda_mps_enable

    def _load_env_file(self, env_file: str):
        env_path = Path(env_file)
        if not env_path.exists():
            logger.warning(f"Environment file {env_file} not found")
            return
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "database": self.database.__dict__,
            "minio": self.minio.__dict__,
            "nats": self.nats.__dict__,
            "model": self.model.__dict__,
            "stt": self.stt.__dict__,
            "tts": self.tts.__dict__,
            "telegram": self.telegram.__dict__,
            "auth": self.auth.__dict__,
            "monitoring": self.monitoring.__dict__,
            "cuda_visible_devices": self.cuda_visible_devices,
            "cuda_mps_enable": self.cuda_mps_enable
        }

    def validate(self) -> bool:
        errors = []
        if not self.telegram.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if not self.model.huggingface_token:
            errors.append("HUGGINGFACE_TOKEN is required for model downloads")
        if self.auth.jwt_secret == "change-this-secret":
            errors.append("JWT_SECRET should be changed from default value")
        if errors:
            logger.error(f"Configuration validation failed: {', '.join(errors)}")
            return False
        return True


config = Config()





