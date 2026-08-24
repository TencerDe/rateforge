from django.http import JsonResponse

from rateforge.rate_limit.exceptions import RateLimitExceeded
from rateforge.rate_limit.models import RateLimitContext


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limiter = getattr(request, "rateforge_limiter", None)

        if limiter is None:
            return self.get_response(request)

        policy = getattr(
            request,
            "rateforge_policy",
            None,
        )

        if policy is None:
            return self.get_response(request)

        context = self._build_context(request)

        try:
            result = limiter.check_context(
                context,
                policy,
            )

        except Exception:
            return self.get_response(request)

        if not result.allowed:
            return self._rate_limited_response(result)

        response = self.get_response(request)

        return self._add_headers(
            response,
            result,
        )

    @staticmethod
    def _build_context(request):
        user_id = None

        if (
            hasattr(request, "user")
            and request.user.is_authenticated
        ):
            user_id = str(request.user.pk)

        return RateLimitContext(
            endpoint=request.path,
            ip=RateLimitMiddleware._get_ip(request),
            user_id=user_id,
            api_key=request.headers.get(
                "X-API-Key"
            ),
        )

    @staticmethod
    def _get_ip(request):
        return request.META.get(
            "REMOTE_ADDR"
        )

    @staticmethod
    def _rate_limited_response(result):
        response = JsonResponse(
            {
                "error": "rate_limit_exceeded",
                "message": "Too many requests",
                "retry_after": result.retry_after,
            },
            status=429,
        )

        response["Retry-After"] = str(
            result.retry_after
        )

        return response

    @staticmethod
    def _add_headers(response, result):
        response["X-RateLimit-Limit"] = str(
            result.limit
        )

        response["X-RateLimit-Remaining"] = str(
            result.remaining
        )

        response["X-RateLimit-Reset"] = str(
            result.reset_at
        )

        return response