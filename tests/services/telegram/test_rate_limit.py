"""
Tests for rate limiting functionality in Telegram service.

Tests cover:
- Per-minute rate limiting
- Per-hour rate limiting
- Per-day rate limiting
- User statistics
- Clearing user rate limit history
- Concurrent access (thread safety)
"""
import pytest
import asyncio
import time
import sys
import os
from unittest.mock import patch, MagicMock

# Mock inference_core before importing rate_limit
sys.modules['inference_core'] = MagicMock()
sys.modules['inference_core.config'] = MagicMock()

# Add essence to path
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_essence_dir = os.path.join(_project_root, 'essence')
if _essence_dir not in sys.path:
    sys.path.insert(0, _essence_dir)

from essence.services.telegram.dependencies.rate_limit import (
    InMemoryRateLimiter,
    RateLimiter,
    get_rate_limiter
)


class TestInMemoryRateLimiter:
    """Tests for InMemoryRateLimiter class."""
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_allows_requests_within_limit(self):
        """Test that requests within rate limit are allowed."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_1"
        
        # Make 5 requests (within limit of 10/minute)
        for i in range(5):
            allowed, error = await limiter.check_rate_limit(user_id)
            assert allowed is True, f"Request {i+1} should be allowed"
            assert error is None
        
        # Verify stats
        stats = await limiter.get_user_stats(user_id)
        assert stats['requests_1m'] == 5
        assert stats['requests_24h'] == 5
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_blocks_requests_exceeding_minute_limit(self):
        """Test that requests exceeding per-minute limit are blocked."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=5,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_2"
        
        # Make 5 requests (at limit)
        for i in range(5):
            allowed, error = await limiter.check_rate_limit(user_id)
            assert allowed is True, f"Request {i+1} should be allowed"
        
        # 6th request should be blocked
        allowed, error = await limiter.check_rate_limit(user_id)
        assert allowed is False
        assert error is not None
        assert "minute" in error.lower()
        assert "5" in error
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_blocks_requests_exceeding_hour_limit(self):
        """Test that requests exceeding per-hour limit are blocked."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=100,  # High to avoid minute limit
            max_requests_per_hour=10,
            max_requests_per_day=500
        )
        
        user_id = "test_user_3"
        
        # Make 10 requests (at hour limit)
        for i in range(10):
            allowed, error = await limiter.check_rate_limit(user_id)
            assert allowed is True, f"Request {i+1} should be allowed"
        
        # 11th request should be blocked
        allowed, error = await limiter.check_rate_limit(user_id)
        assert allowed is False
        assert error is not None
        assert "hour" in error.lower()
        assert "10" in error
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_blocks_requests_exceeding_day_limit(self):
        """Test that requests exceeding per-day limit are blocked."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=100,  # High to avoid minute limit
            max_requests_per_hour=1000,  # High to avoid hour limit
            max_requests_per_day=5
        )
        
        user_id = "test_user_4"
        
        # Make 5 requests (at day limit)
        for i in range(5):
            allowed, error = await limiter.check_rate_limit(user_id)
            assert allowed is True, f"Request {i+1} should be allowed"
        
        # 6th request should be blocked
        allowed, error = await limiter.check_rate_limit(user_id)
        assert allowed is False
        assert error is not None
        assert "24 hours" in error.lower() or "day" in error.lower()
        assert "5" in error
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_expires_old_requests(self):
        """Test that old requests expire and don't count toward limits."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=5,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_5"
        
        # Use a fixed base time for testing
        base_time = 1000.0
        
        with patch('essence.services.telegram.dependencies.rate_limit.time.time', return_value=base_time):
            # Make 5 requests (at limit)
            for i in range(5):
                allowed, error = await limiter.check_rate_limit(user_id)
                assert allowed is True
            
            # 6th request should be blocked
            allowed, error = await limiter.check_rate_limit(user_id)
            assert allowed is False
        
        # Advance time by 61 seconds (requests expire after 60 seconds)
        with patch('essence.services.telegram.dependencies.rate_limit.time.time', return_value=base_time + 61):
            # Now request should be allowed again (old requests expired)
            allowed, error = await limiter.check_rate_limit(user_id)
            assert allowed is True
            assert error is None
    
    @pytest.mark.asyncio
    async def test_get_user_stats(self):
        """Test getting user statistics."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_6"
        
        # Make 3 requests
        for i in range(3):
            await limiter.check_rate_limit(user_id)
        
        stats = await limiter.get_user_stats(user_id)
        
        assert stats['requests_1m'] == 3
        assert stats['requests_1h'] == 3
        assert stats['requests_24h'] == 3
        assert stats['max_per_minute'] == 10
        assert stats['max_per_hour'] == 100
        assert stats['max_per_day'] == 500
    
    @pytest.mark.asyncio
    async def test_get_user_stats_for_nonexistent_user(self):
        """Test getting stats for user with no requests."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_7"
        
        stats = await limiter.get_user_stats(user_id)
        
        assert stats['requests_1m'] == 0
        assert stats['requests_1h'] == 0
        assert stats['requests_24h'] == 0
        assert stats['max_per_minute'] == 10
        assert stats['max_per_hour'] == 100
        assert stats['max_per_day'] == 500
    
    def test_clear_user(self):
        """Test clearing user rate limit history."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_8"
        
        # Add some requests (synchronously to test clear_user)
        # Note: clear_user is synchronous, so we need to add requests first
        async def add_requests():
            for i in range(5):
                await limiter.check_rate_limit(user_id)
        
        asyncio.run(add_requests())
        
        # Verify user has requests
        stats = asyncio.run(limiter.get_user_stats(user_id))
        assert stats['requests_24h'] == 5
        
        # Clear user
        limiter.clear_user(user_id)
        
        # Verify user has no requests
        stats = asyncio.run(limiter.get_user_stats(user_id))
        assert stats['requests_24h'] == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_same_user(self):
        """Test that concurrent requests from same user are handled correctly."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_9"
        
        # Make 5 concurrent requests
        tasks = [limiter.check_rate_limit(user_id) for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        # All should be allowed
        for allowed, error in results:
            assert allowed is True
            assert error is None
        
        # Verify total count
        stats = await limiter.get_user_stats(user_id)
        assert stats['requests_1m'] == 5
    
    @pytest.mark.asyncio
    async def test_different_users_independent_limits(self):
        """Test that different users have independent rate limits."""
        limiter = InMemoryRateLimiter(
            max_requests_per_minute=5,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user1 = "test_user_10"
        user2 = "test_user_11"
        
        # User 1 makes 5 requests (at limit)
        for i in range(5):
            allowed, error = await limiter.check_rate_limit(user1)
            assert allowed is True
        
        # User 1's 6th request should be blocked
        allowed, error = await limiter.check_rate_limit(user1)
        assert allowed is False
        
        # User 2 should still be able to make requests
        allowed, error = await limiter.check_rate_limit(user2)
        assert allowed is True
        
        # Verify independent stats
        stats1 = await limiter.get_user_stats(user1)
        stats2 = await limiter.get_user_stats(user2)
        
        assert stats1['requests_1m'] == 5
        assert stats2['requests_1m'] == 1


class TestRateLimiter:
    """Tests for RateLimiter wrapper class."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_wraps_in_memory_limiter(self):
        """Test that RateLimiter wraps InMemoryRateLimiter correctly."""
        limiter = RateLimiter(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_12"
        
        # Make a request
        allowed, error = await limiter.check_rate_limit(user_id)
        assert allowed is True
        assert error is None
        
        # Get stats
        stats = await limiter.get_user_stats(user_id)
        assert stats['requests_1m'] == 1
        assert stats['max_per_minute'] == 10
    
    @pytest.mark.asyncio
    async def test_rate_limiter_clear_user(self):
        """Test RateLimiter clear_user method."""
        limiter = RateLimiter(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            max_requests_per_day=500
        )
        
        user_id = "test_user_13"
        
        # Add some requests
        for i in range(3):
            await limiter.check_rate_limit(user_id)
        
        # Verify user has requests
        stats = await limiter.get_user_stats(user_id)
        assert stats['requests_24h'] == 3
        
        # Clear user
        limiter.clear_user(user_id)
        
        # Verify user has no requests
        stats = await limiter.get_user_stats(user_id)
        assert stats['requests_24h'] == 0


class TestGetRateLimiter:
    """Tests for get_rate_limiter function."""
    
    @pytest.mark.asyncio
    async def test_get_rate_limiter_returns_singleton(self):
        """Test that get_rate_limiter returns the same instance."""
        # Clear the global instance
        import essence.services.telegram.dependencies.rate_limit as rate_limit_module
        rate_limit_module._rate_limiter = None
        
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        
        assert limiter1 is limiter2
    
    @pytest.mark.asyncio
    async def test_get_rate_limiter_uses_environment_variables(self):
        """Test that get_rate_limiter uses environment variables for configuration."""
        # Clear the global instance
        import essence.services.telegram.dependencies.rate_limit as rate_limit_module
        rate_limit_module._rate_limiter = None
        
        with patch.dict('os.environ', {
            'TELEGRAM_RATE_LIMIT_PER_MINUTE': '20',
            'TELEGRAM_RATE_LIMIT_PER_HOUR': '200',
            'TELEGRAM_RATE_LIMIT_PER_DAY': '1000'
        }):
            limiter = get_rate_limiter()
            
            # Verify configuration
            stats = await limiter.get_user_stats("test_user_14")
            assert stats['max_per_minute'] == 20
            assert stats['max_per_hour'] == 200
            assert stats['max_per_day'] == 1000
    
    @pytest.mark.asyncio
    async def test_get_rate_limiter_uses_defaults_when_env_not_set(self):
        """Test that get_rate_limiter uses defaults when environment variables are not set."""
        # Clear the global instance
        import essence.services.telegram.dependencies.rate_limit as rate_limit_module
        rate_limit_module._rate_limiter = None
        
        with patch.dict('os.environ', {}, clear=True):
            limiter = get_rate_limiter()
            
            # Verify default configuration
            stats = await limiter.get_user_stats("test_user_15")
            assert stats['max_per_minute'] == 10  # Default
            assert stats['max_per_hour'] == 100  # Default
            assert stats['max_per_day'] == 500  # Default
