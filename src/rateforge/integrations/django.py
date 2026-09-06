"""
Django integration for RateForge.

Provides:
- @rate_limit decorator for Django views
- RateLimitMiddleware for automatic rate limiting
- Exception handler for 429 responses
- Identity extraction from Django requests
"""

from functools import wraps
from typing import Any, Callable, Optional

import structlog
from django.http import JsonResponse, HttpRequest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from rateforge import (
    get_default_limiter,
    RateLimitExceeded,
    RateLimitResponseHandler,
)


logger = structlog.get_logger()


def rate_limit(
    rate: str,
    *,
    identity: str = "ip",
    bypass_if_authenticated: bool = False,
) -> Callable:
    """
    Django rate limit decorator.
    
    Args:
        rate: Human-readable rate (e.g., "100/minute", "1000/hour")
        identity: Identity type ("ip", "user", "api_key", "plan")
        bypass_if_authenticated: Skip rate limiting for authenticated users
    
    Returns:
        Decorated Django view function
    
    Example:
        >>> from rateforge.django import rate_limit
        >>>
        >>> @rate_limit("100/minute")
        ... def home(request):
        ...     return HttpResponse("Hello!")
        >>>
        >>> @rate_limit("10/minute", identity="user")
        ... @login_required
        ... def create_order(request):
        ...     ...
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            limiter = get_default_limiter()
            
            # Check bypass condition
            if bypass_if_authenticated and request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            
            # Extract identity
            try:
                identity_value = _extract_identity(request, identity)
            except ValueError as exc:
                logger.error(
                    "identity_extraction_failed",
                    error=str(exc),
                    endpoint=request.path,
                )
                if not limiter.fail_open:
                    raise
                identity_value = "unknown"
            
            # Check rate limit
            try:
                result = limiter.check(
                    identity=identity_value,
                    endpoint=request.path,
                    rate=rate,
                )
                
                # Store result in request for middleware
                request._rate_limit_result = result
                
                if not result.allowed:
                    logger.warning(
                        "rate_limit_exceeded",
                        identity=identity_value,
                        endpoint=request.path,
                        limit=result.limit,
                        remaining=0,
                        retry_after=result.retry_after,
                    )
                    raise RateLimitExceeded(result)
                
                return view_func(request, *args, **kwargs)
            
            except RateLimitExceeded:
                raise
            
            except Exception as exc:
                logger.error(
                    "rate_limit_error",
                    identity=identity_value,
                    endpoint=request.path,
                    error=str(exc),
                )
                if not limiter.fail_open:
                    raise
                return view_func(request, *args, **kwargs)
        
        return wrapper
    
    return decorator


def _extract_identity(request: HttpRequest, identity_type: str) -> str:
    """
    Extract identity from Django request.
    
    Args:
        request: Django HttpRequest
        identity_type: Type of identity ("ip", "user", "api_key", "plan")
    
    Returns:
        Identity string (e.g., "ip:192.168.1.1")
    """
    if identity_type == "ip":
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
            return f"ip:{ip}"
        
        ip = request.META.get("REMOTE_ADDR", "unknown")
        return f"ip:{ip}"
    
    elif identity_type == "user":
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = getattr(request.user, "id", None) or getattr(request.user, "pk", None)
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
        if hasattr(request, "user"):
            plan = getattr(request.user, "plan", None)
            if plan:
                return f"plan:{plan}"
            raise ValueError("User has no plan")
        raise ValueError("Cannot extract plan from request")
    
    else:
        raise ValueError(f"Unknown identity type: {identity_type}")


def rate_limit_exception_handler(exc: RateLimitExceeded) -> JsonResponse:
    """
    Build 429 response for RateLimitExceeded exception.
    
    Args:
        exc: RateLimitExceeded exception
    
    Returns:
        JsonResponse with 429 status and rate limit headers
    """
    return RateLimitResponseHandler.build_429_response(exc.result)


class RateLimitMiddleware:
    """
    Django middleware for automatic rate limiting.
    
    Add to MIDDLEWARE in settings.py:
        MIDDLEWARE = [
            ...
            "rateforge.integrations.django.RateLimitMiddleware",
        ]
    
    Configuration in settings.py (optional):
        RATEFORGE_CONFIG = {
            "default_rate": "100/minute",
            "identity": "ip",
        }
    """
    
    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.limiter = get_default_limiter()
        
        # Optional configuration from settings
        config = getattr(settings, "RATEFORGE_CONFIG", {})
        self.default_rate = config.get("default_rate", "100/minute")
        self.default_identity = config.get("identity", "ip")
    
    def __call__(self, request: HttpRequest) -> Any:
        # Apply rate limiting before view
        try:
            identity_value = _extract_identity(request, self.default_identity)
            
            result = self.limiter.check(
                identity=identity_value,
                endpoint=request.path,
                rate=self.default_rate,
            )
            
            # Store result for later use
            request._rate_limit_result = result
            
            if not result.allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    identity=identity_value,
                    endpoint=request.path,
                    limit=result.limit,
                    remaining=0,
                    retry_after=result.retry_after,
                )
                return RateLimitResponseHandler.build_429_response(result)
        
        except ValueError as exc:
            logger.error(
                "identity_extraction_failed",
                error=str(exc),
                endpoint=request.path,
            )
            if not self.limiter.fail_open:
                raise
        
        except Exception as exc:
            logger.error(
                "rate_limit_error",
                endpoint=request.path,
                error=str(exc),
            )
            if not self.limiter.fail_open:
                raise
        
        # Get response from view
        response = self.get_response(request)
        
        # Add rate limit headers to response
        if hasattr(request, "_rate_limit_result"):
            RateLimitResponseHandler.add_rate_limit_headers(
                response,
                request._rate_limit_result,
            )
        
        return response


def handle_exception(get_response: Callable) -> Callable:
    """
    Decorator to handle RateLimitExceeded exceptions.
    
    Usage:
        @handle_exception
        def my_view(request):
            ...
    """
    @wraps(get_response)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        try:
            return get_response(request, *args, **kwargs)
        except RateLimitExceeded as exc:
            return rate_limit_exception_handler(exc)
    
    return wrapper
