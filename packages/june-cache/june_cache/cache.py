"""
Cache Manager - Redis-based caching implementation with TTL and invalidation.
"""
import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Optional, Dict, List
from datetime import timedelta
import redis.asyncio as aioredis
from redis.exceptions import RedisError, ConnectionError

logger = logging.getLogger(__name__)


class CacheType:
    """Cache type constants."""
    LLM_RESPONSE = "llm_response"
    STT_TRANSCRIPTION = "stt_transcription"
    TTS_SYNTHESIS = "tts_synthesis"
    USER_SESSION = "user_session"
    DB_QUERY = "db_query"


class CacheConfig:
    """Cache configuration."""
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: int = 3600,  # 1 hour default
        max_connections: int = 50,
        socket_connect_timeout: int = 5,
        socket_timeout: int = 5,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30,
    ):
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL", 
            "redis://redis:6379/0"
        )
        self.default_ttl = default_ttl
        self.max_connections = max_connections
        self.socket_connect_timeout = socket_connect_timeout
        self.socket_timeout = socket_timeout
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval
        
        # TTL per cache type (in seconds)
        self.ttl_config: Dict[str, int] = {
            CacheType.LLM_RESPONSE: int(os.getenv("CACHE_TTL_LLM", "7200")),  # 2 hours
            CacheType.STT_TRANSCRIPTION: int(os.getenv("CACHE_TTL_STT", "86400")),  # 24 hours
            CacheType.TTS_SYNTHESIS: int(os.getenv("CACHE_TTL_TTS", "86400")),  # 24 hours
            CacheType.USER_SESSION: int(os.getenv("CACHE_TTL_SESSION", "1800")),  # 30 minutes
            CacheType.DB_QUERY: int(os.getenv("CACHE_TTL_DB", "300")),  # 5 minutes
        }


class CacheManager:
    """Redis-based cache manager with TTL and invalidation."""
    
    def __init__(self, config: Optional[CacheConfig] = None, metrics=None):
        self.config = config or CacheConfig()
        self.metrics = metrics
        self.redis: Optional[aioredis.Redis] = None
        self._connection_pool: Optional[aioredis.ConnectionPool] = None
        self._is_connected = False
        
    async def connect(self) -> bool:
        """Connect to Redis."""
        try:
            self._connection_pool = aioredis.ConnectionPool.from_url(
                self.config.redis_url,
                max_connections=self.config.max_connections,
                socket_connect_timeout=self.config.socket_connect_timeout,
                socket_timeout=self.config.socket_timeout,
                retry_on_timeout=self.config.retry_on_timeout,
                health_check_interval=self.config.health_check_interval,
            )
            self.redis = aioredis.Redis(connection_pool=self._connection_pool)
            
            # Test connection
            await self.redis.ping()
            self._is_connected = True
            logger.info(f"Connected to Redis at {self.config.redis_url}")
            return True
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching will be disabled.")
            self._is_connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()
        self._is_connected = False
        logger.info("Disconnected from Redis")
    
    def _is_available(self) -> bool:
        """Check if cache is available."""
        return self._is_connected and self.redis is not None
    
    def _make_key(self, cache_type: str, key: str) -> str:
        """Create a namespaced cache key."""
        return f"june:{cache_type}:{key}"
    
    def _hash_key(self, data: Any) -> str:
        """Create a hash key from data for consistent caching."""
        if isinstance(data, (str, bytes)):
            data_str = data if isinstance(data, str) else data.decode('utf-8', errors='ignore')
        else:
            data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    async def get(
        self, 
        cache_type: str, 
        key: str,
        default: Any = None
    ) -> Optional[Any]:
        """Get value from cache."""
        if not self._is_available():
            if self.metrics:
                self.metrics.record_miss(cache_type)
            return default
        
        try:
            cache_key = self._make_key(cache_type, key)
            value = await self.redis.get(cache_key)
            
            if value is None:
                if self.metrics:
                    self.metrics.record_miss(cache_type)
                return default
            
            # Deserialize JSON
            try:
                result = json.loads(value)
                if self.metrics:
                    self.metrics.record_hit(cache_type)
                return result
            except json.JSONDecodeError:
                # Fallback: return as string
                if self.metrics:
                    self.metrics.record_hit(cache_type)
                return value.decode('utf-8') if isinstance(value, bytes) else value
                
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Cache get error: {e}")
            if self.metrics:
                self.metrics.record_miss(cache_type)
            return default
    
    async def set(
        self,
        cache_type: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in cache with TTL."""
        if not self._is_available():
            return False
        
        try:
            cache_key = self._make_key(cache_type, key)
            
            # Serialize value
            if isinstance(value, (str, bytes)):
                serialized = value if isinstance(value, bytes) else value.encode('utf-8')
            else:
                serialized = json.dumps(value).encode('utf-8')
            
            # Use type-specific TTL or default
            ttl = ttl or self.config.ttl_config.get(cache_type, self.config.default_ttl)
            
            await self.redis.setex(cache_key, ttl, serialized)
            return True
            
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Cache set error: {e}")
            return False
    
    async def delete(self, cache_type: str, key: str) -> bool:
        """Delete value from cache."""
        if not self._is_available():
            return False
        
        try:
            cache_key = self._make_key(cache_type, key)
            await self.redis.delete(cache_key)
            return True
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Cache delete error: {e}")
            return False
    
    async def invalidate_pattern(self, cache_type: str, pattern: str) -> int:
        """Invalidate all keys matching pattern for a cache type."""
        if not self._is_available():
            return 0
        
        try:
            cache_pattern = self._make_key(cache_type, pattern)
            keys = []
            async for key in self.redis.scan_iter(match=cache_pattern):
                keys.append(key)
            
            if keys:
                deleted = await self.redis.delete(*keys)
                return deleted
            return 0
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Cache invalidation error: {e}")
            return 0
    
    async def invalidate_type(self, cache_type: str) -> int:
        """Invalidate all keys of a specific cache type."""
        return await self.invalidate_pattern(cache_type, "*")
    
    async def get_or_set(
        self,
        cache_type: str,
        key: str,
        callable_fn,
        ttl: Optional[int] = None,
        *args,
        **kwargs
    ) -> Any:
        """Get from cache or compute and set if missing."""
        # Try to get from cache
        cached = await self.get(cache_type, key)
        if cached is not None:
            return cached
        
        # Compute value
        if asyncio.iscoroutinefunction(callable_fn):
            value = await callable_fn(*args, **kwargs)
        else:
            value = callable_fn(*args, **kwargs)
        
        # Store in cache
        await self.set(cache_type, key, value, ttl)
        return value
    
    async def warm_cache(
        self,
        cache_type: str,
        items: List[Dict[str, Any]],
        ttl: Optional[int] = None,
    ) -> int:
        """Warm cache with multiple items."""
        if not self._is_available():
            return 0
        
        count = 0
        for item in items:
            key = item.get('key')
            value = item.get('value')
            if key and value is not None:
                if await self.set(cache_type, key, value, ttl):
                    count += 1
        
        logger.info(f"Warmed cache with {count} items for {cache_type}")
        return count
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self._is_available():
            return {"connected": False}
        
        try:
            info = await self.redis.info()
            return {
                "connected": True,
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "connected_clients": info.get("connected_clients", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
        except (RedisError, ConnectionError) as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {"connected": False, "error": str(e)}
