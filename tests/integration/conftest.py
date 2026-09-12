"""
Pytest configuration and shared fixtures.
"""

import pytest
from redis import Redis


@pytest.fixture(scope="session")
def redis_client():
    """
    Create a Redis client for integration tests.

    Scope: session (reused across all tests)
    """
    client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)

    # Clean up before tests
    client.flushdb()

    yield client

    # Clean up after tests
    client.flushdb()


@pytest.fixture
def redis_test_db(redis_client):
    """
    Create isolated Redis DB for each test.

    Automatically flushed after each test.
    """
    redis_client.flushdb()
    yield redis_client
    redis_client.flushdb()
