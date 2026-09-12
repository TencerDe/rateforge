"""
Unit tests for rate limit decorator.

Tests:
1. Default IP identity
2. String identity types
3. Callable identity
4. Bypass for authenticated users
5. RateLimitExceeded raised correctly
6. Fail-open behavior
7. Fail-closed behavior
8. Response headers
9. Global limiter configuration
10. Environment variable loading
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from rateforge import (
    RateLimitExceeded,
    configure_limiter,
    get_default_limiter,
    rate_limit,
)
from rateforge.rate_limit.decorator import (
    _extract_identity_from_request,
    _is_user_authenticated,
)


class MockRequest:
    """Mock request object for testing."""

    def __init__(
        self,
        ip="192.168.1.1",
        user=None,
        path="/api/test",
        headers=None,
    ):
        self.META = {
            "REMOTE_ADDR": ip,
            "HTTP_X_FORWARDED_FOR": "",
        }
        self.path = path
        self.headers = headers or {}

        if user:
            self.user = user


class MockUser:
    """Mock user object."""

    def __init__(self, id=123, is_authenticated=True, plan=None):
        self.id = id
        self.is_authenticated = is_authenticated
        if plan:
            self.plan = plan


class TestDefaultIPIdentity:
    """Test default IP-based rate limiting."""

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_decorator_with_default_ip(self, mock_get_limiter):
        """Decorator should use IP identity by default."""
        mock_limiter = MagicMock()
        mock_limiter.check.return_value = MagicMock(
            allowed=True,
            limit=100,
            remaining=99,
            retry_after=0,
            reset_at=1234567890,
        )
        mock_limiter.fail_open = True
        mock_get_limiter.return_value = mock_limiter

        @rate_limit("100/minute")
        def test_view(request):
            return "OK"

        request = MockRequest()
        result = test_view(request)

        assert result == "OK"
        mock_limiter.check.assert_called_once()
        call_args = mock_limiter.check.call_args
        assert call_args[1]["identity"].startswith("ip:")


class TestStringIdentity:
    """Test string identity types."""

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_user_identity(self, mock_get_limiter):
        """Test user-based identity."""
        mock_limiter = MagicMock()
        mock_limiter.check.return_value = MagicMock(
            allowed=True,
            limit=10,
            remaining=9,
            retry_after=0,
            reset_at=1234567890,
        )
        mock_limiter.fail_open = True
        mock_get_limiter.return_value = mock_limiter

        user = MockUser(id=456)
        request = MockRequest(user=user)

        @rate_limit("10/minute", identity="user")
        def test_view(request):
            return "OK"

        result = test_view(request)
        assert result == "OK"

        call_args = mock_limiter.check.call_args
        assert call_args[1]["identity"] == "user:456"

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_api_key_identity(self, mock_get_limiter):
        """Test API key-based identity."""
        mock_limiter = MagicMock()
        mock_limiter.check.return_value = MagicMock(
            allowed=True,
            limit=1000,
            remaining=999,
            retry_after=0,
            reset_at=1234567890,
        )
        mock_limiter.fail_open = True
        mock_get_limiter.return_value = mock_limiter

        request = MockRequest(headers={"X-API-Key": "test-key-123"})

        @rate_limit("1000/hour", identity="api_key")
        def test_view(request):
            return "OK"

        result = test_view(request)
        assert result == "OK"

        call_args = mock_limiter.check.call_args
        assert call_args[1]["identity"] == "api_key:test-key-123"


class TestCallableIdentity:
    """Test callable identity extractor."""

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_custom_identity_extractor(self, mock_get_limiter):
        """Test custom identity via callable."""
        mock_limiter = MagicMock()
        mock_limiter.check.return_value = MagicMock(
            allowed=True,
            limit=100,
            remaining=99,
            retry_after=0,
            reset_at=1234567890,
        )
        mock_limiter.fail_open = True
        mock_get_limiter.return_value = mock_limiter

        request = MockRequest()

        # Custom identity that already has prefix
        @rate_limit(
            "100/minute",
            identity=lambda req: f"org:{req.META['REMOTE_ADDR']}",
        )
        def test_view(request):
            return "OK"

        result = test_view(request)
        assert result == "OK"

        call_args = mock_limiter.check.call_args
        assert call_args[1]["identity"] == "org:192.168.1.1"


class TestBypassAuthenticated:
    """Test bypass for authenticated users."""

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_bypass_when_authenticated(self, mock_get_limiter):
        """Bypass rate limiting for authenticated users."""
        mock_limiter = MagicMock()
        mock_get_limiter.return_value = mock_limiter

        user = MockUser(is_authenticated=True)
        request = MockRequest(user=user)

        @rate_limit("1/minute", bypass_if_authenticated=True)
        def test_view(request):
            return "OK"

        result = test_view(request)
        assert result == "OK"

        # Limiter should NOT be called
        mock_limiter.check.assert_not_called()

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_no_bypass_when_anonymous(self, mock_get_limiter):
        """Apply rate limiting for anonymous users."""
        mock_limiter = MagicMock()
        mock_limiter.check.return_value = MagicMock(
            allowed=True,
            limit=100,
            remaining=99,
            retry_after=0,
            reset_at=1234567890,
        )
        mock_limiter.fail_open = True
        mock_get_limiter.return_value = mock_limiter

        user = MockUser(is_authenticated=False)
        request = MockRequest(user=user)

        @rate_limit("100/minute", bypass_if_authenticated=True)
        def test_view(request):
            return "OK"

        result = test_view(request)
        assert result == "OK"

        # Limiter SHOULD be called
        mock_limiter.check.assert_called_once()


class TestRateLimitExceeded:
    """Test RateLimitExceeded exception."""

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_raises_when_limit_exceeded(self, mock_get_limiter):
        """Should raise RateLimitExceeded when limit exceeded."""
        mock_limiter = MagicMock()
        mock_result = MagicMock(
            allowed=False,
            limit=10,
            remaining=0,
            retry_after=45,
            reset_at=1234567890,
        )
        mock_limiter.check.return_value = mock_result
        mock_limiter.fail_open = False
        mock_get_limiter.return_value = mock_limiter

        request = MockRequest()

        @rate_limit("10/minute")
        def test_view(request):
            return "OK"

        with pytest.raises(RateLimitExceeded) as exc_info:
            test_view(request)

        assert exc_info.value.result.retry_after == 45


class TestFailOpenBehavior:
    """Test fail-open behavior."""

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_allows_request_when_redis_down(self, mock_get_limiter):
        """Fail-open should allow requests when Redis is down."""
        mock_limiter = MagicMock()
        mock_limiter.check.side_effect = Exception("Redis unavailable")
        mock_limiter.fail_open = True
        mock_get_limiter.return_value = mock_limiter

        request = MockRequest()

        @rate_limit("100/minute")
        def test_view(request):
            return "OK"

        result = test_view(request)
        assert result == "OK"


class TestFailClosedBehavior:
    """Test fail-closed behavior."""

    @patch("rateforge.rate_limit.decorator.get_default_limiter")
    def test_raises_when_redis_down(self, mock_get_limiter):
        """Fail-closed should raise when Redis is down."""
        mock_limiter = MagicMock()
        mock_limiter.check.side_effect = Exception("Redis unavailable")
        mock_limiter.fail_open = False
        mock_get_limiter.return_value = mock_limiter

        request = MockRequest()

        @rate_limit("100/minute")
        def test_view(request):
            return "OK"

        # Test that some exception is raised (fail-closed)
        with pytest.raises(Exception):  # noqa: B017
            test_view(request)


class TestGlobalLimiter:
    """Test global limiter configuration."""

    def test_get_default_limiter_creates_instance(self):
        """Should create limiter instance on first call."""
        # Clear any existing instance
        from rateforge.rate_limit import limiter as limiter_module

        limiter_module._default_limiter = None

        with patch.dict(
            os.environ,
            {
                "RATEFORGE_REDIS_URL": "redis://test:6379/0",
                "RATEFORGE_FAIL_OPEN": "true",
            },
            clear=False,
        ):
            limiter = get_default_limiter()
            assert limiter is not None
            assert limiter.fail_open is True

    def test_configure_limiter_overrides(self):
        """configure_limiter should override default."""
        from rateforge.rate_limit import limiter as limiter_module

        limiter_module._default_limiter = None

        configure_limiter("redis://custom:6379/0", fail_open=False)

        limiter = get_default_limiter()
        assert limiter.fail_open is False


class TestIdentityExtraction:
    """Test identity extraction helpers."""

    def test_is_user_authenticated_django(self):
        """Test authentication check for Django."""
        # Authenticated user
        request = MagicMock()
        request.user.is_authenticated = True
        assert _is_user_authenticated(request) is True

        # Anonymous user
        request = MagicMock()
        request.user.is_authenticated = False
        assert _is_user_authenticated(request) is False

        # No user attribute
        request = MagicMock(spec=[])
        assert _is_user_authenticated(request) is False

    def test_extract_identity_from_request_ip(self):
        """Test IP extraction from request."""
        request = MockRequest(ip="10.0.0.1")

        identity = _extract_identity_from_request(request, "ip")
        assert identity == "ip:10.0.0.1"

    def test_extract_identity_from_request_user(self):
        """Test user extraction from request."""
        user = MockUser(id=789)
        request = MockRequest(user=user)

        identity = _extract_identity_from_request(request, "user")
        assert identity == "user:789"

    def test_extract_identity_missing_raises(self):
        """Test missing identity raises ValueError."""
        request = MockRequest()

        with pytest.raises(ValueError, match="Cannot extract user identity"):
            _extract_identity_from_request(request, "user")
