from rateforge import RateLimiter


def test_rate_limit():
    limiter = RateLimiter(
        "redis://localhost:6379/0"
    )

    identity = "test-user-123"

    for _ in range(5):
        result = limiter.check(
            identity=identity,
            endpoint="/api/test",
            limit=5,
            window=60,
        )

        assert result.allowed is True

    result = limiter.check(
        identity=identity,
        endpoint="/api/test",
        limit=5,
        window=60,
    )

    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after >= 0