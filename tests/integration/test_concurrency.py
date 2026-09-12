"""
Integration tests for concurrency and real Redis scenarios.

Tests:
1. Concurrent requests (async)
2. Thread safety
3. Sliding window behavior
4. Rate limit recovery
5. Multiple identities
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from rateforge import RateLimiter


@pytest.mark.integration
class TestConcurrency:
    """Test rate limiting under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_async(self, redis_client):
        """Test rate limiting with async concurrent requests."""
        limiter = RateLimiter("redis://localhost:6379/0")

        async def make_request(user_id: str):
            result = limiter.check(
                identity=f"user:{user_id}",
                endpoint="/api/test",
                limit=10,
                window=60,
            )
            return result.allowed

        # Simulate 100 concurrent requests from same user
        tasks = [make_request("user_1") for _ in range(100)]
        results = await asyncio.gather(*tasks)

        # Exactly 10 should be allowed (limit=10)
        allowed_count = sum(1 for r in results if r)
        assert allowed_count == 10, f"Expected 10 allowed, got {allowed_count}"

        # 90 should be rejected
        rejected_count = sum(1 for r in results if not r)
        assert rejected_count == 90

    @pytest.mark.asyncio
    async def test_concurrent_requests_multiple_users(self, redis_client):
        """Test rate limiting with multiple users concurrently."""
        limiter = RateLimiter("redis://localhost:6379/0")

        async def make_request(user_id: str):
            result = limiter.check(
                identity=f"user:{user_id}",
                endpoint="/api/test",
                limit=5,
                window=60,
            )
            return result.allowed

        # 20 users, each making 10 requests
        tasks = []
        for user_num in range(20):
            for _ in range(10):
                tasks.append(make_request(f"user_{user_num}"))

        results = await asyncio.gather(*tasks)

        # Each user should have 5 allowed (limit=5)
        # Total: 20 users * 5 = 100 allowed
        allowed_count = sum(1 for r in results if r)
        assert allowed_count == 100

    def test_thread_safety(self, redis_client):
        """Test rate limiting with multiple threads."""
        limiter = RateLimiter("redis://localhost:6379/0")

        def make_request(thread_id: int):
            result = limiter.check(
                identity=f"thread:{thread_id}",
                endpoint="/api/test",
                limit=5,
                window=60,
            )
            return result.allowed

        # 20 threads, each making 10 requests
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for thread_id in range(20):
                for _ in range(10):
                    futures.append(executor.submit(make_request, thread_id))

            results = [f.result() for f in futures]

        # Each thread has separate bucket, all should be allowed
        assert all(results), "All requests should be allowed (separate buckets)"

    @pytest.mark.asyncio
    async def test_concurrent_same_endpoint_different_users(self, redis_client):
        """Test concurrent requests to same endpoint from different users."""
        limiter = RateLimiter("redis://localhost:6379/0")

        async def make_request(user_id: str):
            result = limiter.check(
                identity=f"user:{user_id}",
                endpoint="/api/orders",
                limit=3,
                window=60,
            )
            return result.allowed, result.remaining

        # 10 users, each making 5 requests concurrently
        tasks = []
        for user_num in range(10):
            for _ in range(5):
                tasks.append(make_request(f"user_{user_num}"))

        results = await asyncio.gather(*tasks)

        # Each user: 3 allowed, 2 rejected
        allowed = sum(1 for allowed, _ in results if allowed)
        assert allowed == 30  # 10 users * 3 allowed


@pytest.mark.integration
class TestSlidingWindow:
    """Test sliding window algorithm behavior."""

    def test_window_expiration(self, redis_client):
        """Test that requests expire after window passes."""
        limiter = RateLimiter("redis://localhost:6379/0")

        # Make 5 requests (hit the limit)
        for i in range(5):
            result = limiter.check(
                identity="test:user",
                endpoint="/api/test",
                limit=5,
                window=2,  # 2 second window
            )
            assert result.allowed, f"Request {i + 1} should be allowed"

        # 6th request should be rejected
        result = limiter.check(
            identity="test:user",
            endpoint="/api/test",
            limit=5,
            window=2,
        )
        assert not result.allowed, "6th request should be rejected"

        # Wait for window to expire
        time.sleep(2.5)

        # Request should be allowed again
        result = limiter.check(
            identity="test:user",
            endpoint="/api/test",
            limit=5,
            window=2,
        )
        assert result.allowed, "Request after window should be allowed"

    def test_sliding_window_boundary(self, redis_client):
        """Test sliding window at boundary."""
        limiter = RateLimiter("redis://localhost:6379/0")

        # Make 3 requests
        for _ in range(3):
            limiter.check(
                identity="boundary:user",
                endpoint="/api/test",
                limit=5,
                window=3,
            )

        # Wait 1.5 seconds (half window)
        time.sleep(1.5)

        # Make 2 more requests
        for _ in range(2):
            result = limiter.check(
                identity="boundary:user",
                endpoint="/api/test",
                limit=5,
                window=3,
            )
            assert result.allowed

        # 6th request should be rejected
        result = limiter.check(
            identity="boundary:user",
            endpoint="/api/test",
            limit=5,
            window=3,
        )
        assert not result.allowed

        # Wait for first 3 requests to expire
        time.sleep(1.6)

        # Should be allowed now (only 2 requests in current window)
        result = limiter.check(
            identity="boundary:user",
            endpoint="/api/test",
            limit=5,
            window=3,
        )
        assert result.allowed


@pytest.mark.integration
class TestRateLimitRecovery:
    """Test rate limit recovery behavior."""

    def test_recovery_after_limit_reached(self, redis_client):
        """Test that rate limiting recovers after window expires."""
        limiter = RateLimiter("redis://localhost:6379/0")

        # Exhaust limit
        for _ in range(10):
            limiter.check(
                identity="recovery:user",
                endpoint="/api/test",
                limit=10,
                window=2,
            )

        # Verify limit reached
        result = limiter.check(
            identity="recovery:user",
            endpoint="/api/test",
            limit=10,
            window=2,
        )
        assert not result.allowed
        assert result.remaining == 0

        # Wait for recovery
        time.sleep(2.5)

        # Should be fully recovered
        result = limiter.check(
            identity="recovery:user",
            endpoint="/api/test",
            limit=10,
            window=2,
        )
        assert result.allowed
        assert result.remaining == 9  # 10 - 1 = 9

    def test_retry_after_accuracy(self, redis_client):
        """Test retry_after value accuracy."""
        limiter = RateLimiter("redis://localhost:6379/0")

        # Exhaust limit
        for _ in range(5):
            limiter.check(
                identity="retry:user",
                endpoint="/api/test",
                limit=5,
                window=10,
            )

        # Get rejected request
        result = limiter.check(
            identity="retry:user",
            endpoint="/api/test",
            limit=5,
            window=10,
        )

        assert not result.allowed
        assert result.retry_after > 0
        assert result.retry_after <= 10  # Should be <= window


@pytest.mark.integration
class TestMultipleIdentities:
    """Test multiple identity types concurrently."""

    @pytest.mark.asyncio
    async def test_mixed_identity_types(self, redis_client):
        """Test rate limiting with mixed identity types."""
        limiter = RateLimiter("redis://localhost:6379/0")

        async def make_request(identity: str):
            result = limiter.check(
                identity=identity,
                endpoint="/api/test",
                limit=5,
                window=60,
            )
            return result.allowed

        # Mix of IP, user, and API key identities
        identities = [
            "ip:192.168.1.1",
            "ip:192.168.1.2",
            "user:123",
            "user:456",
            "api_key:key1",
            "api_key:key2",
        ]

        # Each identity makes 10 requests
        tasks = []
        for identity in identities:
            for _ in range(10):
                tasks.append(make_request(identity))

        results = await asyncio.gather(*tasks)

        # Each identity should have 5 allowed
        allowed_count = sum(1 for r in results if r)
        assert allowed_count == 30  # 6 identities * 5 allowed

    def test_separate_buckets_per_identity(self, redis_client):
        """Test that each identity has separate bucket."""
        limiter = RateLimiter("redis://localhost:6379/0")

        identities = [
            "ip:10.0.0.1",
            "ip:10.0.0.2",
            "user:1",
            "user:2",
        ]

        # Each identity makes 10 requests with limit=5
        for identity in identities:
            allowed_count = 0
            for _ in range(10):
                result = limiter.check(
                    identity=identity,
                    endpoint="/api/test",
                    limit=5,
                    window=60,
                )
                if result.allowed:
                    allowed_count += 1

            # Each identity should have exactly 5 allowed
            assert allowed_count == 5, f"Identity {identity} should have 5 allowed"
