from functools import wraps

from .models import RateLimitContext
from .policy import create_policy


def limit(
    limiter,
    rate: str,
    *,
    identity: str = "ip",
):
    policy = create_policy(
        rate,
        identity=identity,
    )

    def decorator(func):
        @wraps(func)
        def wrapper(context: RateLimitContext, *args, **kwargs):
            result = limiter.check_context(
                context,
                policy,
            )

            if not result.allowed:
                raise RuntimeError(
                    "Rate limit exceeded"
                )

            return func(
                context,
                *args,
                **kwargs,
            )

        return wrapper

    return decorator