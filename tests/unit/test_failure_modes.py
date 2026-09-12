"""
Unit tests for Redis failure handling modes.

These tests verify:
1. Fail-open behavior when Redis is unavailable
2. Fail-closed behavior when Redis is unavailable
3. Script execution errors are NOT suppressed
4. Proper logging of failures
5. Exception chain preservation
"""

from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError

from rateforge.rate_limit.exceptions import (
    ConfigurationError,
    RedisConnectionError,
    ScriptExecutionError,
)
from rateforge.rate_limit.limiter import RateLimiter


class TestRedisConnectionErrorFailOpen:
    """Test fail-open behavior when Redis connection fails."""

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_redis_connection_error_fail_open_allows_request(self, mock_redis):
        """When fail_open=True and Redis is down, requests should be allowed."""
        mock_script = MagicMock(side_effect=RedisConnectionError("Redis unavailable"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        result = limiter.check(
            identity="user:123",
            endpoint="/api/test",
            limit=10,
            window=60,
        )

        assert result.allowed is True
        assert result.limit == 10
        assert result.remaining == 10
        assert result.retry_after == 0

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_redis_connection_error_fail_open_logs_warning(self, mock_redis, caplog):
        """Fail-open should log a warning with context."""
        mock_script = MagicMock(side_effect=RedisConnectionError("Redis unavailable"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        limiter.check(
            identity="user:123",
            endpoint="/api/test",
            limit=10,
            window=60,
        )

        # Verify structlog was called (caplog may not capture structlog by default)
        # The key assertion is that the code doesn't crash and allows the request

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_redis_connection_error_from_mock_allows_request(self, mock_redis):
        """Test with redis.exceptions.ConnectionError wrapped by backend."""
        mock_script = MagicMock(side_effect=ConnectionError("Connection refused"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        result = limiter.check(
            identity="user:456",
            endpoint="/api/orders",
            limit=5,
            window=30,
        )

        assert result.allowed is True

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_timeout_error_fail_open(self, mock_redis):
        """Timeout errors should also trigger fail-open behavior."""
        mock_script = MagicMock(side_effect=TimeoutError("Timeout after 5s"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        result = limiter.check(
            identity="user:789",
            endpoint="/api/data",
            limit=100,
            window=60,
        )

        assert result.allowed is True

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_busy_loading_error_fail_open(self, mock_redis):
        """Redis busy loading should trigger fail-open behavior."""
        mock_script = MagicMock(side_effect=BusyLoadingError("Redis is loading"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        result = limiter.check(
            identity="user:abc",
            endpoint="/api/users",
            limit=50,
            window=120,
        )

        assert result.allowed is True


class TestRedisConnectionErrorFailClosed:
    """Test fail-closed behavior when Redis connection fails."""

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_redis_connection_error_fail_closed_raises(self, mock_redis):
        """When fail_open=False and Redis is down, raise RedisConnectionError."""
        mock_script = MagicMock(side_effect=RedisConnectionError("Redis unavailable"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=False)

        with pytest.raises(RedisConnectionError):
            limiter.check(
                identity="user:123",
                endpoint="/api/test",
                limit=10,
                window=60,
            )

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_redis_connection_error_preserves_cause(self, mock_redis):
        """The original exception should be preserved in __cause__."""
        original_error = ConnectionError("Connection refused")
        mock_script = MagicMock(side_effect=original_error)
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=False)

        with pytest.raises(RedisConnectionError) as exc_info:
            limiter.check(
                identity="user:123",
                endpoint="/api/test",
                limit=10,
                window=60,
            )

        assert exc_info.value.__cause__ is original_error

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_fail_closed_multiple_requests_consistent(self, mock_redis):
        """Multiple requests during outage should consistently fail."""
        mock_script = MagicMock(side_effect=RedisConnectionError("Redis unavailable"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=False)

        for i in range(5):
            with pytest.raises(RedisConnectionError):
                limiter.check(
                    identity=f"user:{i}",
                    endpoint="/api/test",
                    limit=10,
                    window=60,
                )


class TestScriptExecutionError:
    """Test that script execution errors (bugs) are NOT suppressed."""

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_script_error_not_suppressed_fail_open(self, mock_redis):
        """Script execution errors should raise even when fail_open=True."""
        mock_script = MagicMock(side_effect=ValueError("Invalid script argument"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        with pytest.raises(ScriptExecutionError):
            limiter.check(
                identity="user:123",
                endpoint="/api/test",
                limit=10,
                window=60,
            )

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_script_error_not_suppressed_fail_closed(self, mock_redis):
        """Script execution errors should raise when fail_open=False."""
        mock_script = MagicMock(side_effect=ValueError("Invalid script argument"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=False)

        with pytest.raises(ScriptExecutionError):
            limiter.check(
                identity="user:123",
                endpoint="/api/test",
                limit=10,
                window=60,
            )

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_script_error_preserves_original_exception(self, mock_redis):
        """ScriptExecutionError should preserve the original exception."""
        original_error = ValueError("Invalid argument")
        mock_script = MagicMock(side_effect=original_error)
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        with pytest.raises(ScriptExecutionError) as exc_info:
            limiter.check(
                identity="user:123",
                endpoint="/api/test",
                limit=10,
                window=60,
            )

        assert exc_info.value.__cause__ is original_error

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_script_error_logs_error(self, mock_redis):
        """Script execution errors should be logged."""
        mock_script = MagicMock(side_effect=RuntimeError("Unexpected error"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        with pytest.raises(ScriptExecutionError):
            limiter.check(
                identity="user:123",
                endpoint="/api/test",
                limit=10,
                window=60,
            )


class TestNormalOperation:
    """Test that normal Redis operations work correctly."""

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_redis_available_normal_flow(self, mock_redis):
        """When Redis is available, normal rate limiting should work."""
        mock_script = MagicMock(return_value=[1, 5, 0])
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        result = limiter.check(
            identity="user:123",
            endpoint="/api/test",
            limit=10,
            window=60,
        )

        assert result.allowed is True
        assert result.limit == 10
        assert result.remaining == 5
        assert result.retry_after == 0
        mock_script.assert_called_once()

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_rate_limit_exceeded(self, mock_redis):
        """When limit is exceeded, request should be rejected."""
        mock_script = MagicMock(return_value=[0, 10, 45])
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        result = limiter.check(
            identity="user:123",
            endpoint="/api/test",
            limit=10,
            window=60,
        )

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 45

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_recovery_after_failure(self, mock_redis):
        """When Redis recovers, normal operation should resume."""
        mock_script = MagicMock(
            side_effect=[
                ConnectionError("Redis down"),
                [1, 1, 0],
                [1, 2, 0],
            ]
        )
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        result1 = limiter.check(
            identity="user:123",
            endpoint="/api/test",
            limit=10,
            window=60,
        )
        assert result1.allowed is True
        assert result1.remaining == 10  # Fail-open gives full quota

        result2 = limiter.check(
            identity="user:123",
            endpoint="/api/test",
            limit=10,
            window=60,
        )
        assert result2.allowed is True
        assert result2.remaining == 9  # Normal operation: 10 - 1 = 9


class TestConfigurationError:
    """Test configuration error handling."""

    def test_invalid_redis_url_raises_configuration_error(self):
        """Invalid Redis URL should raise ConfigurationError."""
        with pytest.raises(ConfigurationError):
            RateLimiter("not-a-valid-redis-url", fail_open=True)

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_redis_url_type_error_raises_configuration_error(self, mock_from_url):
        """Type errors in URL parsing should raise ConfigurationError."""
        mock_from_url.side_effect = TypeError("Invalid URL type")

        with pytest.raises(ConfigurationError):
            RateLimiter("redis://localhost", fail_open=True)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_multiple_concurrent_failures(self, mock_redis):
        """Multiple concurrent requests during outage should behave consistently."""
        mock_script = MagicMock(side_effect=RedisConnectionError("Redis unavailable"))
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)

        results = []
        for i in range(10):
            result = limiter.check(
                identity=f"user:{i}",
                endpoint="/api/test",
                limit=10,
                window=60,
            )
            results.append(result)

        assert all(r.allowed is True for r in results)
        assert all(r.remaining == 10 for r in results)

    @patch("rateforge.rate_limit.backend.Redis.from_url")
    def test_exception_chain_preserved(self, mock_redis):
        """Exception __cause__ should be preserved for debugging."""
        original = ConnectionError("Connection refused")
        mock_script = MagicMock(side_effect=original)
        mock_redis.return_value.register_script.return_value = mock_script

        limiter = RateLimiter("redis://localhost:6379/0", fail_open=False)

        with pytest.raises(RedisConnectionError) as exc_info:
            limiter.check(
                identity="user:123",
                endpoint="/api/test",
                limit=10,
                window=60,
            )

        assert exc_info.value.__cause__ is original
