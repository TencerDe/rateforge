from functools import wraps

from .exceptions import RateLimitExceeded
from .models import RateLimitContext, IdentityType
from .policy import create_policy


class IdentityResolver:
    """
    Resolves identity from RateLimitContext based on identity type.
    
    Supports:
    - IP address
    - User ID
    - API key
    - Plan
    """
    
    @staticmethod
    def resolve(context: RateLimitContext, identity_type: IdentityType) -> str:
        """
        Resolve identity string from context.
        
        Args:
            context: RateLimitContext with identity information
            identity_type: Type of identity to resolve
        
        Returns:
            Identity string (e.g., "ip:192.168.1.1", "user:123")
        
        Raises:
            ValueError: If required identity field is missing
        """
        if identity_type == IdentityType.IP:
            if not context.ip:
                raise ValueError("IP address required for IP-based rate limiting")
            return f"ip:{context.ip}"
        
        elif identity_type == IdentityType.USER:
            if not context.user_id:
                raise ValueError("User ID required for user-based rate limiting")
            return f"user:{context.user_id}"
        
        elif identity_type == IdentityType.API_KEY:
            if not context.api_key:
                raise ValueError("API key required for API key-based rate limiting")
            return f"api_key:{context.api_key}"
        
        elif identity_type == IdentityType.PLAN:
            if not context.plan:
                raise ValueError("Plan required for plan-based rate limiting")
            return f"plan:{context.plan}"
        
        else:
            raise ValueError(f"Unknown identity type: {identity_type}")


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
        def wrapper(
            context: RateLimitContext,
            *args,
            **kwargs,
        ):
            result = limiter.check_context(
                context,
                policy,
            )

            if not result.allowed:
                raise RateLimitExceeded(
                    result=result,
                )

            return func(
                context,
                *args,
                **kwargs,
            )

        return wrapper

    return decorator