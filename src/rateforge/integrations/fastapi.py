"""
FastAPI integration for RateForge.

Provides:
- @rate_limit decorator for FastAPI endpoints
- rate_limit_dependency for Depends() injection
- Exception handler for 429 responses
- Identity extraction from FastAPI requests
"""

from functools import wraps
from typing import Any, Callable, Optional

import structlog
from fastapi import Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from rateforge import (
    get_default_limiter,
    RateLimitExceeded,
    RateLimitResponseHandler,
)


logger = structlog.get_logger()


def rate_limit(
    rate: str = "100/minute",
    *,
    identity: str = "ip",
    bypass_if_authenticated: bool = False,
) -> Callable:
    """
    FastAPI rate limit decorator.
    
    Args:
        rate: Human-readable rate (e.g., "100/minute", "1000/hour")
        identity: Identity type ("ip", "user", "api_key", "plan")
        bypass_if_authenticated: Skip rate limiting for authenticated users
    
    Returns:
        Decorated FastAPI endpoint
    
    Example:
        >>> from rateforge.fastapi import rate_limit
        >>>
        >>> @app.get("/users")
        >>> @rate_limit("100/minute")
        >>> async def get_users():
        ...     return {"users": [...]}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get request from args or kwargs
            request = _get_request_from_args(args, kwargs)
            
            if request is None:
                return await func(*args, **kwargs)
            
            limiter = get_default_limiter()
            
            # Check bypass condition
            if bypass_if_authenticated and _is_user_authenticated(request):
                return await func(*args, **kwargs)
            
            # Extract identity
            try:
                identity_value = _extract_identity(request, identity)
            except ValueError as exc:
                logger.error(
                    "identity_extraction_failed",
                    error=str(exc),
                    endpoint=str(request.url),
                )
                if not limiter.fail_open:
                    raise
                identity_value = "unknown"
            
            # Check rate limit
            try:
                result = limiter.check(
                    identity=identity_value,
                    endpoint=request.url.path,
                    rate=rate,
                )
                
                # Store result in request state
                request.state.rate_limit_result = result
                
                if not result.allowed:
                    logger.warning(
                        "rate_limit_exceeded",
                        identity=identity_value,
                        endpoint=request.url.path,
                        limit=result.limit,
                        remaining=0,
                        retry_after=result.retry_after,
                    )
                    raise RateLimitExceeded(result)
                
                return await func(*args, **kwargs)
            
            except RateLimitExceeded:
                raise
            
            except Exception as exc:
                logger.error(
                    "rate_limit_error",
                    identity=identity_value,
                    endpoint=request.url.path,
                    error=str(exc),
                )
                if not limiter.fail_open:
                    raise
                return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def _get_request_from_args(args: tuple, kwargs: dict) -> Optional[Request]:
    """Extract Request object from function args/kwargs."""
    # Check kwargs first
    if "request" in kwargs:
        return kwargs["request"]
    
    # Check args
    for arg in args:
        if isinstance(arg, Request):
            return arg
    
    return None


def _is_user_authenticated(request: Request) -> bool:
    """Check if user is authenticated in FastAPI request."""
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "is_authenticated"):
        return user.is_authenticated
    return False


def _extract_identity(request: Request, identity_type: str) -> str:
    """
    Extract identity from FastAPI request.
    
    Args:
        request: FastAPI Request
        identity_type: Type of identity ("ip", "user", "api_key", "plan")
    
    Returns:
        Identity string (e.g., "ip:192.168.1.1")
    """
    if identity_type == "ip":
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
            return f"ip:{ip}"
        
        if request.client:
            return f"ip:{request.client.host}"
        
        return "ip:unknown"
    
    elif identity_type == "user":
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "is_authenticated") and user.is_authenticated:
            user_id = getattr(user, "id", None)
            if user_id:
                return f"user:{user_id}"
            raise ValueError("User authenticated but no ID available")
        raise ValueError("User not authenticated")
    
    elif identity_type == "api_key":
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"api_key:{api_key}"
        raise ValueError("API key not provided")
    
    elif identity_type == "plan":
        plan = getattr(request.state, "plan", None)
        if plan:
            return f"plan:{plan}"
        raise ValueError("No plan in request state")
    
    else:
        raise ValueError(f"Unknown identity type: {identity_type}")


def rate_limit_dependency(
    rate: str = "100/minute",
    identity: str = "ip",
) -> Callable:
    """
    FastAPI Depends() dependency for rate limiting.
    
    Args:
        rate: Human-readable rate (e.g., "100/minute")
        identity: Identity type ("ip", "user", "api_key", "plan")
    
    Returns:
        Dependency function for FastAPI Depends()
    
    Example:
        >>> from fastapi import FastAPI, Depends
        >>> from rateforge.fastapi import rate_limit_dependency
        >>>
        >>> app = FastAPI()
        >>>
        >>> @app.get("/users", dependencies=[Depends(rate_limit_dependency("100/minute"))])
        >>> async def get_users():
        ...     return {"users": [...]}
    """
    async def dependency(request: Request):
        limiter = get_default_limiter()
        
        # Extract identity
        try:
            identity_value = _extract_identity(request, identity)
        except ValueError as exc:
            logger.error(
                "identity_extraction_failed",
                error=str(exc),
                endpoint=request.url.path,
            )
            if not limiter.fail_open:
                raise HTTPException(status_code=503, detail="Service unavailable")
            return
        
        # Check rate limit
        try:
            result = limiter.check(
                identity=identity_value,
                endpoint=request.url.path,
                rate=rate,
            )
            
            # Store result in request state
            request.state.rate_limit_result = result
            
            if not result.allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    identity=identity_value,
                    endpoint=request.url.path,
                    limit=result.limit,
                    remaining=0,
                    retry_after=result.retry_after,
                )
                raise RateLimitExceeded(result)
        
        except RateLimitExceeded:
            raise
        
        except Exception as exc:
            logger.error(
                "rate_limit_error",
                identity=identity_value,
                endpoint=request.url.path,
                error=str(exc),
            )
            if not limiter.fail_open:
                raise HTTPException(status_code=503, detail="Service unavailable")
    
    return dependency


def rate_limit_exception_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """
    FastAPI exception handler for RateLimitExceeded.
    
    Register with app.add_exception_handler():
        app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
    """
    response = JSONResponse(
        status_code=429,
        content=RateLimitResponseHandler.build_429_body(exc.result),
    )
    
    RateLimitResponseHandler.add_rate_limit_headers(response, exc.result)
    
    return response


def setup_rate_limiting(app: Any) -> None:
    """
    Setup rate limiting for FastAPI app.
    
    Registers exception handler and adds default dependencies.
    
    Args:
        app: FastAPI application
    
    Example:
        >>> from fastapi import FastAPI
        >>> from rateforge.fastapi import setup_rate_limiting
        >>>
        >>> app = FastAPI()
        >>> setup_rate_limiting(app)
    """
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
