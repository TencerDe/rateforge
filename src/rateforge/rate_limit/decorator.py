"""
Rate limit decorator for Python view functions.

Supports:
- Sync functions (async on Day 3)
- String identity types: "ip", "user", "api_key", "plan"
- Custom identity extractors (callable)
- Bypass for authenticated users
- Automatic rate limit headers
- RateLimitExceeded exception on limit breach
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

import structlog

from .exceptions import RateLimitExceeded
from .limiter import RateLimiter, get_default_limiter
from .policy import create_policy

logger = structlog.get_logger()


def rate_limit(
    rate: str,
    *,
    limiter: RateLimiter | None = None,
    identity: str | Callable[[Any], str] = "ip",
    key_builder: Callable[[str, str], str] | None = None,
    bypass_if_authenticated: bool = False,
) -> Callable:
    """
    Rate limit decorator for view functions.

    Args:
        rate: Human-readable rate (e.g., "100/minute", "1000/hour")
        limiter: RateLimiter instance (uses global default if None)
        identity: Identity type ("ip", "user", "api_key", "plan") or callable
        key_builder: Custom Redis key builder (optional)
        bypass_if_authenticated: Skip rate limiting for authenticated users

    Returns:
        Decorated function with rate limiting

    Raises:
        RateLimitExceeded: When rate limit is exceeded

    Example:
        >>> @rate_limit("100/minute")
        ... def my_view(request):
        ...     return HttpResponse("OK")

        >>> @rate_limit("10/minute", identity="user")
        ... def user_action(request):
        ...     ...

        >>> @rate_limit("100/hour", bypass_if_authenticated=True)
        ... def public_api(request):
        ...     # Anonymous: 100/hour, Authenticated: unlimited
        ...     ...
    """
    policy = create_policy(rate, identity=identity if isinstance(identity, str) else "ip")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            # Check bypass condition
            if bypass_if_authenticated and _is_user_authenticated(request):
                return func(request, *args, **kwargs)

            # Get limiter instance
            limiter_instance = limiter or get_default_limiter()

            # Extract identity
            if callable(identity):
                try:
                    identity_value = identity(request)
                except Exception as exc:
                    logger.error(
                        "identity_extraction_failed",
                        error=str(exc),
                        endpoint=getattr(request, "path", "unknown"),
                    )
                    if not limiter_instance.fail_open:
                        raise
                    identity_value = "unknown"
            else:
                identity_value = _extract_identity_from_request(request, identity)

            # Build endpoint path
            endpoint = _get_endpoint_path(request)

            # Check rate limit
            try:
                result = limiter_instance.check(
                    identity=identity_value,
                    endpoint=endpoint,
                    limit=policy.limit,
                    window=policy.window,
                )

                # Store result in request for middleware/decorator to use
                _store_rate_limit_result(request, result)

                if not result.allowed:
                    logger.warning(
                        "rate_limit_exceeded",
                        identity=identity_value,
                        endpoint=endpoint,
                        limit=policy.limit,
                        remaining=0,
                        retry_after=result.retry_after,
                    )
                    raise RateLimitExceeded(result)

                return func(request, *args, **kwargs)

            except RateLimitExceeded:
                raise

            except Exception as exc:
                logger.error(
                    "rate_limit_error",
                    identity=identity_value,
                    endpoint=endpoint,
                    error=str(exc),
                )
                if not limiter_instance.fail_open:
                    raise
                return func(request, *args, **kwargs)

        return wrapper

    return decorator


def _is_user_authenticated(request: Any) -> bool:
    """
    Check if user is authenticated (Django/FastAPI agnostic).

    Args:
        request: Django or FastAPI request object

    Returns:
        True if user is authenticated, False otherwise
    """
    # Django
    if hasattr(request, "user"):
        user = request.user
        if hasattr(user, "is_authenticated"):
            return user.is_authenticated

    # FastAPI (request.state.user)
    if hasattr(request, "state"):
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "is_authenticated"):
            return user.is_authenticated

    return False


def _extract_identity_from_request(request: Any, identity_type: str) -> str:
    """
    Extract identity from request based on type.

    Args:
        request: Django or FastAPI request object
        identity_type: Type of identity ("ip", "user", "api_key", "plan")

    Returns:
        Identity string (e.g., "ip:192.168.1.1")
    """
    if identity_type == "ip":
        # Django
        if hasattr(request, "META"):
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
                return f"ip:{ip}"

            ip = request.META.get("REMOTE_ADDR", "unknown")
            return f"ip:{ip}"

        # FastAPI
        if hasattr(request, "headers"):
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
                return f"ip:{ip}"

            if hasattr(request, "client") and request.client:
                return f"ip:{request.client.host}"

            return "ip:unknown"

        return "ip:unknown"

    elif identity_type == "user":
        # Django
        if hasattr(request, "user"):
            user = request.user
            if hasattr(user, "is_authenticated") and user.is_authenticated:
                user_id = getattr(user, "id", None) or getattr(user, "pk", None)
                if user_id:
                    return f"user:{user_id}"
                raise ValueError("User authenticated but no ID available")
            raise ValueError("User not authenticated")

        # FastAPI
        if hasattr(request, "state"):
            user = getattr(request.state, "user", None)
            if user and hasattr(user, "is_authenticated") and user.is_authenticated:
                user_id = getattr(user, "id", None)
                if user_id:
                    return f"user:{user_id}"
                raise ValueError("User authenticated but no ID available")
            raise ValueError("User not authenticated")

        raise ValueError("Cannot extract user identity from request")

    elif identity_type == "api_key":
        # Django
        if hasattr(request, "headers"):
            api_key = request.headers.get("X-API-Key", "")
            if api_key:
                return f"api_key:{api_key}"
            raise ValueError("API key not provided")

        # FastAPI
        if hasattr(request, "headers"):
            api_key = request.headers.get("X-API-Key", "")
            if api_key:
                return f"api_key:{api_key}"
            raise ValueError("API key not provided")

        raise ValueError("Cannot extract API key from request")

    elif identity_type == "plan":
        # Django/FastAPI - assume plan is stored in user object or request
        if hasattr(request, "user"):
            plan = getattr(request.user, "plan", None)
            if plan:
                return f"plan:{plan}"
            raise ValueError("User has no plan")

        if hasattr(request, "state"):
            plan = getattr(request.state, "plan", None)
            if plan:
                return f"plan:{plan}"
            raise ValueError("No plan in request state")

        raise ValueError("Cannot extract plan from request")

    else:
        raise ValueError(f"Unknown identity type: {identity_type}")


def _get_endpoint_path(request: Any) -> str:
    """
    Extract endpoint path from request.

    Args:
        request: Django or FastAPI request object

    Returns:
        Endpoint path string
    """
    # Django
    if hasattr(request, "path"):
        return request.path

    # Django (older versions)
    if hasattr(request, "get_full_path"):
        return request.get_full_path().split("?")[0]

    # FastAPI
    if hasattr(request, "url"):
        return request.url.path

    return "unknown"


def _store_rate_limit_result(request: Any, result: Any) -> None:
    """
    Store rate limit result in request for later use.

    Args:
        request: Django or FastAPI request object
        result: RateLimitResult instance
    """
    # Django - attach to request
    if hasattr(request, "__dict__"):
        request._rate_limit_result = result

    # FastAPI - attach to request.state
    if hasattr(request, "state"):
        request.state.rate_limit_result = result
