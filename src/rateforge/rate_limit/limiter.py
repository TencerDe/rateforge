import time
import uuid

from .algorithms import SLIDING_WINDOW_SCRIPT
from .backend import RedisBackend
from .models import RateLimitResult
from .keys import RateLimitKeyBuilder


class RateLimiter:
    def __init__(
        self,
        redis_url: str,
        *,
        fail_open: bool = True,
    ):
        self.backend = RedisBackend(redis_url)
        self.fail_open = fail_open

        self._script = self.backend.redis.register_script(
            SLIDING_WINDOW_SCRIPT
        )

    def check(
    self,
    *,
    identity: str,
    endpoint: str,
    limit: int,
    window: int,
) -> RateLimitResult:

        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        if window <= 0:
            raise ValueError("window must be greater than 0")

        now = time.time()
        request_id = uuid.uuid4().hex

        key = RateLimitKeyBuilder.build(
              identity,
              endpoint,
)

        try:
            result = self._script(
                keys=[key],
                args=[
                    now,
                    window,
                    limit,
                    request_id,
                ],
            )

        except Exception:
            if self.fail_open:
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=limit,
                    retry_after=0,
                    reset_at=int(now + window),
                )

            raise

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