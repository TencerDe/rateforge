"""
Rate limit response handler.

Provides:
- Standard 429 response builder
- Rate limit header injector
- Framework-agnostic response handling
"""

from typing import Any


class RateLimitResponseHandler:
    """Build rate limit responses and headers."""
    
    @staticmethod
    def build_429_body(result: Any) -> dict[str, Any]:
        """
        Build standard 429 response body.
        
        Args:
            result: RateLimitResult instance
        
        Returns:
            JSON response body dict
        """
        return {
            "error": "rate_limit_exceeded",
            "message": "Too many requests",
            "retry_after": result.retry_after,
        }
    
    @staticmethod
    def add_rate_limit_headers(
        response: Any,
        result: Any,
    ) -> Any:
        """
        Add X-RateLimit-* headers to response.
        
        Args:
            response: Django HttpResponse or FastAPI Response
            result: RateLimitResult instance
        
        Returns:
            Response with headers added
        """
        response["X-RateLimit-Limit"] = str(result.limit)
        response["X-RateLimit-Remaining"] = str(result.remaining)
        response["X-RateLimit-Reset"] = str(result.reset_at)
        
        if not result.allowed:
            response["Retry-After"] = str(result.retry_after)
        
        return response
    
    @staticmethod
    def build_429_response(result: Any, response_class: type = None) -> Any:
        """
        Build complete 429 Too Many Requests response.
        
        Args:
            result: RateLimitResult instance
            response_class: Response class to use (default: JsonResponse for Django)
        
        Returns:
            HTTP 429 response with headers
        """
        from django.http import JsonResponse
        
        body = RateLimitResponseHandler.build_429_body(result)
        response = JsonResponse(body, status=429)
        
        RateLimitResponseHandler.add_rate_limit_headers(response, result)
        
        return response
