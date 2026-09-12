from redis import Redis
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError

from .exceptions import ConfigurationError, RedisConnectionError


class RedisBackend:
    """
    Redis backend wrapper with specific exception handling.

    Distinguishes between:
    - Connection/timeout errors (infrastructure issues)
    - Configuration errors (invalid URL, auth failures)
    - Other Redis errors (bugs, script errors)
    """

    def __init__(self, redis_url: str):
        try:
            self.redis = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        except (ValueError, TypeError) as exc:
            raise ConfigurationError(f"Invalid Redis URL: {exc}") from exc

    def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            return bool(self.redis.ping())
        except (ConnectionError, TimeoutError) as exc:
            raise RedisConnectionError(f"Redis connection failed: {exc}") from exc
        except BusyLoadingError as exc:
            raise RedisConnectionError(f"Redis is loading dataset: {exc}") from exc
