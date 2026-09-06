from .django import (
    rate_limit as django_rate_limit,
    RateLimitMiddleware,
    rate_limit_exception_handler as django_rate_limit_handler,
)

from .fastapi import (
    rate_limit as fastapi_rate_limit,
    rate_limit_dependency,
    rate_limit_exception_handler as fastapi_rate_limit_handler,
    setup_rate_limiting,
)

__all__ = [
    "django_rate_limit",
    "RateLimitMiddleware",
    "django_rate_limit_handler",
    "fastapi_rate_limit",
    "rate_limit_dependency",
    "fastapi_rate_limit_handler",
    "setup_rate_limiting",
]
