"""
Inference-core utilities (migrated from june/shared/utils.py)
"""
import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


def serialize_json(obj: Any) -> str:
    return json.dumps(obj, cls=JSONEncoder)


def deserialize_json(data: str) -> Any:
    return json.loads(data)


class Timer:
    def __init__(self, name: str = "operation"):
        self.name = name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        logger.info(f"{self.name} took {duration:.3f} seconds")

    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class RateLimiter:
    def __init__(self, max_requests: int, time_window: float = 60.0):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def is_allowed(self) -> bool:
        now = time.time()
        self.requests = [req_time for req_time in self.requests if now - req_time < self.time_window]
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False

    def wait_time(self) -> float:
        if not self.requests:
            return 0.0
        oldest_request = min(self.requests)
        wait_time = self.time_window - (time.time() - oldest_request)
        return max(0.0, wait_time)


class RetryConfig:
    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 60.0, exponential_base: float = 2.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base


async def retry_async(func, *args, config: Optional[RetryConfig] = None, **kwargs):
    if config is None:
        config = RetryConfig()
    last_exception = None
    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt == config.max_attempts - 1:
                break
            delay = min(config.base_delay * (config.exponential_base ** attempt), config.max_delay)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
    raise last_exception


def retry_sync(func, *args, config: Optional[RetryConfig] = None, **kwargs):
    if config is None:
        config = RetryConfig()
    last_exception = None
    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt == config.max_attempts - 1:
                break
            delay = min(config.base_delay * (config.exponential_base ** attempt), config.max_delay)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    raise last_exception


class HealthChecker:
    def __init__(self):
        self.checks = {}

    def add_check(self, name: str, check_func):
        self.checks[name] = check_func

    async def check_all(self) -> Dict[str, bool]:
        results = {}
        for name, check_func in self.checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    results[name] = await check_func()
                else:
                    results[name] = check_func()
            except Exception as e:
                logger.error(f"Health check {name} failed: {e}")
                results[name] = False
        return results

    def is_healthy(self) -> bool:
        results = asyncio.run(self.check_all())
        return all(results.values())


def setup_logging(level: str = "INFO", service_name: str = "june"):
    log_dir = f'{os.getenv("JUNE_DATA_DIR", "/tmp")}/logs'
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=f'%(asctime)s - {service_name} - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(), logging.FileHandler(f'{log_dir}/{service_name}.log')],
    )


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id() -> str:
    return str(uuid.uuid4())


class CircularBuffer:
    def __init__(self, max_size: int):
        self.max_size = max_size
        self.buffer = []
        self.lock = asyncio.Lock()

    async def append(self, item):
        async with self.lock:
            self.buffer.append(item)
            if len(self.buffer) > self.max_size:
                self.buffer.pop(0)

    async def get_all(self) -> List:
        async with self.lock:
            return self.buffer.copy()

    async def clear(self):
        async with self.lock:
            self.buffer.clear()

    def size(self) -> int:
        return len(self.buffer)




