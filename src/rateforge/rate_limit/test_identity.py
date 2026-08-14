import pytest

from rateforge.rate_limit.identity import IdentityResolver
from rateforge.rate_limit.models import (
    IdentityType,
    RateLimitContext,
)


def test_user_identity():
    context = RateLimitContext(
        endpoint="/api/orders",
        user_id="123",
    )

    result = IdentityResolver.resolve(
        context,
        IdentityType.USER,
    )

    assert result == "user:123"


def test_ip_identity():
    context = RateLimitContext(
        endpoint="/api/orders",
        ip="127.0.0.1",
    )

    result = IdentityResolver.resolve(
        context,
        IdentityType.IP,
    )

    assert result == "ip:127.0.0.1"


def test_missing_identity():
    context = RateLimitContext(
        endpoint="/api/orders",
    )

    with pytest.raises(ValueError):
        IdentityResolver.resolve(
            context,
            IdentityType.USER,
        )