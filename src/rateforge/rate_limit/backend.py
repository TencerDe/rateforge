from redis import Redis

from .exceptions import RedisUnavailableError
from .models import RateLimitResult


class RedisBackend:
    def __init__(self, redis_url: str):
        self.redis = Redis.from_url(
            redis_url,
            decode_responses=True,
        )

    def ping(self) -> bool:
        try:
            return bool(self.redis.ping())
        except Exception as exc:
            raise RedisUnavailableError from exc