import os
import time
import uuid

import structlog
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError

from .algorithms import SLIDING_WINDOW_SCRIPT
from .backend import RedisBackend
from .exceptions import RedisConnectionError, ScriptExecutionError
from .identity import IdentityResolver
from .keys import RateLimitKeyBuilder
from .models import IdentityType, RateLimitContext, RateLimitResult
from .policy import RateLimitPolicy

logger = structlog.get_logger()

_default_limiter: "RateLimiter | None" = None


def get_default_limiter() -> "RateLimiter":
    """
    Get or create global RateLimiter instance.

    Configuration via environment variables:
    - RATEFORGE_REDIS_URL: Redis connection URL (default: redis://localhost:6379/0)
    - RATEFORGE_FAIL_OPEN: Allow requests when Redis is down (default: true)

    Returns:
        Global RateLimiter instance
    """
    global _default_limiter

    if _default_limiter is None:
        redis_url = os.getenv("RATEFORGE_REDIS_URL", "redis://localhost:6379/0")
        fail_open_str = os.getenv("RATEFORGE_FAIL_OPEN", "true").lower()
        fail_open = fail_open_str == "true"

        _default_limiter = RateLimiter(redis_url, fail_open=fail_open)

    return _default_limiter


def configure_limiter(
    redis_url: str,
    *,
    fail_open: bool = True,
) -> None:
    """
    Configure global RateLimiter instance.

    Args:
        redis_url: Redis connection URL
        fail_open: Allow requests when Redis is unavailable
    """
    global _default_limiter
    _default_limiter = RateLimiter(redis_url, fail_open=fail_open)


class RateLimiter:
    """
    Redis-backed sliding window rate limiter.

    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
        fail_open: If True, allow requests when Redis is unavailable.
                  If False, reject requests when Redis is unavailable.

    Example:
        >>> limiter = RateLimiter("redis://localhost:6379/0", fail_open=True)
        >>> result = limiter.check(
        ...     identity="user:123",
        ...     endpoint="/api/orders",
        ...     limit=100,
        ...     window=60,
        ... )
        >>> if not result.allowed:
        ...     print(f"Retry after {result.retry_after} seconds")
    """

    def __init__(
        self,
        redis_url: str,
        *,
        fail_open: bool = True,
    ):
        self.backend = RedisBackend(redis_url)
        self.fail_open = fail_open

        self._script = self.backend.redis.register_script(SLIDING_WINDOW_SCRIPT)

    def check(
        self,
        *,
        identity: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """
        Check if a request should be allowed based on rate limits.

        Args:
            identity: Unique identifier (e.g., "user:123", "ip:192.168.1.1")
            endpoint: API endpoint path (e.g., "/api/orders")
            limit: Maximum number of requests allowed in the window
            window: Time window in seconds

        Returns:
            RateLimitResult with allowed status and metadata

        Raises:
            RedisConnectionError: If Redis is unavailable and fail_open=False
            ScriptExecutionError: If Lua script execution fails
            ValueError: If limit or window are invalid
        """
        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        if window <= 0:
            raise ValueError("window must be greater than 0")

        now = time.time()
        request_id = uuid.uuid4().hex

        key = RateLimitKeyBuilder.build(identity, endpoint)

        try:
            result = self._script(
                keys=[key],
                args=[now, window, limit, request_id],
            )
        except (ConnectionError, TimeoutError, BusyLoadingError) as exc:
            logger.warning(
                "redis_connection_failed",
                identity=identity,
                endpoint=endpoint,
                fail_open=self.fail_open,
            )
            if self.fail_open:
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=limit,
                    retry_after=0,
                    reset_at=int(now + window),
                )
            raise RedisConnectionError(f"Redis connection failed: {exc}") from exc
        except RedisConnectionError:
            logger.warning(
                "redis_connection_failed",
                identity=identity,
                endpoint=endpoint,
                fail_open=self.fail_open,
            )
            if self.fail_open:
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=limit,
                    retry_after=0,
                    reset_at=int(now + window),
                )
            raise
        except Exception as exc:
            logger.error(
                "script_execution_failed",
                identity=identity,
                endpoint=endpoint,
                error=str(exc),
            )
            raise ScriptExecutionError(f"Lua script failed: {exc}") from exc

        allowed = bool(int(result[0]))
        count = int(result[1])
        retry_after = max(0, int(float(result[2])))

        remaining = max(0, limit - count)

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            retry_after=retry_after,
            reset_at=int(now + window),
        )

    def check_context(
        self,
        context: RateLimitContext,
        policy: RateLimitPolicy,
    ) -> RateLimitResult:
        """
        Check rate limit using context and policy objects.

        Args:
            context: RateLimitContext with identity and endpoint information
            policy: RateLimitPolicy with limit and window configuration

        Returns:
            RateLimitResult with allowed status and metadata
        """
        identity_type = IdentityType(policy.identity)

        identity = IdentityResolver.resolve(context, identity_type)

        return self.check(
            identity=identity,
            endpoint=context.endpoint,
            limit=policy.limit,
            window=policy.window,
        )
