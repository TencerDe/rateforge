from fastapi import HTTPException, Request

from rateforge.rate_limit.models import RateLimitContext


def rate_limit_dependency(
    limiter,
    policy,
):
    async def dependency(
        request: Request,
    ):
        user_id = None

        if hasattr(request.state, "user_id"):
            user_id = str(
                request.state.user_id
            )

        context = RateLimitContext(
            endpoint=request.url.path,
            ip=request.client.host
            if request.client
            else None,
            user_id=user_id,
            api_key=request.headers.get(
                "X-API-Key"
            ),
        )

        result = limiter.check_context(
            context,
            policy,
        )

        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests",
                    "retry_after": result.retry_after,
                },
                headers={
                    "Retry-After": str(
                        result.retry_after
                    ),
                    "X-RateLimit-Limit": str(
                        result.limit
                    ),
                    "X-RateLimit-Remaining": str(
                        result.remaining
                    ),
                    "X-RateLimit-Reset": str(
                        result.reset_at
                    ),
                },
            )

        return result

    return dependency