# Testing Strategy — RateForge

**Target:** 85%+ Code Coverage  
**Testing Pyramid:** Unit → Integration → E2E  
**Framework:** pytest + pytest-cov  
**Date:** 2026-09-06

---

## Table of Contents

1. [Testing Philosophy](#testing-philosophy)
2. [Test Categories](#test-categories)
3. [Mocking Strategy](#mocking-strategy)
4. [Test Examples](#test-examples)
5. [Coverage Goals](#coverage-goals)
6. [CI/CD Integration](#cicd-integration)

---

## Testing Philosophy

### The Testing Pyramid

```
        /\
       /  \      E2E Tests (Few, slow, high confidence)
      /----\
     /      \    Integration Tests (Some, medium speed)
    /--------\
   /          \  Unit Tests (Many, fast, isolated)
  /------------\
```

**Why This Structure?**

| Layer | Count | Speed | Confidence | Cost |
|-------|-------|-------|------------|------|
| **Unit** | 50+ | <1s each | Medium | Low |
| **Integration** | 20+ | 1-5s each | High | Medium |
| **E2E** | 5-10 | 10-30s each | Very High | High |

**Key Principle:** "More unit tests, fewer E2E tests. Test at the lowest possible level."

---

## Test Categories

### 1. Unit Tests

**Purpose:** Test individual components in isolation  
**Location:** `tests/unit/`  
**Speed:** <1 second per test  
**Mocking:** Heavy use of mocks

#### Files:

```
tests/unit/
├── test_duration.py       # Duration parser tests
├── test_plans.py          # Plan registry tests
├── test_identity.py       # Identity resolver tests
├── test_policy.py         # Policy model tests
├── test_keys.py           # Key builder tests
├── test_limiter.py        # RateLimiter basic tests
├── test_failure_modes.py  # Redis failure handling (NEW)
└── test_exceptions.py     # Exception hierarchy tests
```

#### Example:

```python
# tests/unit/test_failure_modes.py
@patch("rateforge.rate_limit.limiter.RateLimiter._script")
def test_redis_connection_error_fail_open(mock_script):
    """When fail_open=True and Redis is down, requests should be allowed."""
    # Arrange
    mock_script.side_effect = RedisConnectionError("Redis unavailable")
    limiter = RateLimiter("redis://localhost", fail_open=True)
    
    # Act
    result = limiter.check(
        identity="user:123",
        endpoint="/api/test",
        limit=10,
        window=60,
    )
    
    # Assert
    assert result.allowed is True
    assert result.remaining == 10  # Full quota restored
```

---

### 2. Integration Tests

**Purpose:** Test component interactions  
**Location:** `tests/integration/`  
**Speed:** 1-5 seconds per test  
**Mocking:** Minimal (real Redis, real components)

#### Files:

```
tests/integration/
├── test_redis_backend.py     # Redis connection tests
├── test_sliding_window.py    # Sliding window algorithm tests
├── test_concurrency.py       # Concurrent request tests
└── test_failure_modes.py     # Real Redis failure tests
```

#### Example:

```python
# tests/integration/test_sliding_window.py
@pytest.mark.integration
def test_sliding_window_expiration(redis_client):
    """Requests should expire after window passes."""
    limiter = RateLimiter("redis://localhost:6379/0")
    
    # Make 5 requests
    for _ in range(5):
        result = limiter.check(
            identity="test:user",
            endpoint="/api/test",
            limit=5,
            window=2,  # 2-second window
        )
        assert result.allowed is True
    
    # 6th request should be rejected
    result = limiter.check(...)
    assert result.allowed is False
    
    # Wait for window to expire
    time.sleep(2.5)
    
    # Request should be allowed again
    result = limiter.check(...)
    assert result.allowed is True
```

**Pytest Markers:**

```python
# Run only integration tests
pytest -m integration

# Skip integration tests
pytest -m "not integration"
```

---

### 3. Framework Integration Tests

**Purpose:** Test Django/FastAPI integration  
**Location:** `tests/django/`, `tests/fastapi/`  
**Speed:** 5-10 seconds per test  
**Mocking:** Real framework, mocked Redis (optional)

#### Django Example:

```python
# tests/django/test_middleware.py
@pytest.mark.django
def test_rate_limit_middleware_rejects_exceeded_requests(client):
    """Middleware should return 429 when limit exceeded."""
    url = "/api/test-endpoint"
    
    # Make requests until limit exceeded
    for i in range(10):
        response = client.get(url)
        
        if i < 5:
            assert response.status_code == 200
        else:
            assert response.status_code == 429
            assert response.json()["error"] == "rate_limit_exceeded"
```

#### FastAPI Example:

```python
# tests/fastapi/test_dependency.py
@pytest.mark.fastapi
def test_rate_limit_dependency_injection(test_client):
    """FastAPI Depends() should inject rate limit check."""
    response = test_client.get("/api/orders")
    
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
```

---

## Mocking Strategy

### When to Mock

| Scenario | Mock? | Reason |
|----------|-------|--------|
| Redis connection | ✅ Yes | Avoid network dependency |
| Lua script execution | ✅ Yes | Test error handling |
| Time-based logic | ✅ Yes | Make tests deterministic |
| External APIs | ✅ Yes | Avoid flakiness |
| Your own code | ❌ No | Test real behavior |

### Mock Patterns

#### 1. Patching Methods

```python
from unittest.mock import patch

@patch("rateforge.rate_limit.limiter.RateLimiter._script")
def test_mock_script(mock_script):
    mock_script.return_value = [1, 5, 0]  # allowed, count, retry_after
    
    limiter = RateLimiter("redis://localhost")
    result = limiter.check(...)
    
    assert result.allowed is True
    mock_script.assert_called_once()
```

#### 2. Mocking Exceptions

```python
@patch("rateforge.rate_limit.limiter.RateLimiter._script")
def test_redis_failure(mock_script):
    mock_script.side_effect = RedisConnectionError("Redis down")
    
    limiter = RateLimiter("redis://localhost", fail_open=True)
    result = limiter.check(...)
    
    assert result.allowed is True  # Fail-open
```

#### 3. Mocking Time

```python
from unittest.mock import patch
import time

@patch("time.time")
def test_sliding_window_with_mocked_time(mock_time):
    # Set initial time
    mock_time.return_value = 1000.0
    
    limiter = RateLimiter("redis://localhost")
    result1 = limiter.check(...)
    
    # Advance time by 30 seconds
    mock_time.return_value = 1030.0
    
    result2 = limiter.check(...)
    
    # Verify behavior based on time difference
```

#### 4. pytest-mock (Cleaner Syntax)

```python
# Install: pip install pytest-mock
def test_with_pytest_mock(mocker):
    # Arrange
    mock_script = mocker.patch("rateforge.rate_limit.limiter.RateLimiter._script")
    mock_script.return_value = [1, 5, 0]
    
    # Act
    limiter = RateLimiter("redis://localhost")
    result = limiter.check(...)
    
    # Assert
    assert result.allowed is True
    mock_script.assert_called_once()
```

---

## Test Examples

### Testing Exception Hierarchy

```python
# tests/unit/test_exceptions.py
class TestExceptionHierarchy:
    """Test that exceptions are properly categorized."""
    
    def test_redis_connection_error_is_rateforge_exception(self):
        """RedisConnectionError should be a RateForgeException."""
        exc = RedisConnectionError("Redis down")
        assert isinstance(exc, RateForgeException)
    
    def test_script_error_is_internal_error(self):
        """ScriptExecutionError should be a RateForgeInternalError."""
        exc = ScriptExecutionError("Script failed")
        assert isinstance(exc, RateForgeInternalError)
        assert isinstance(exc, RateForgeException)
    
    def test_configuration_error_is_internal_error(self):
        """ConfigurationError should be a RateForgeInternalError."""
        exc = ConfigurationError("Invalid config")
        assert isinstance(exc, RateForgeInternalError)
```

### Testing Fail-Open/Fail-Closed

```python
# tests/unit/test_failure_modes.py
class TestFailOpenVsFailClosed:
    """Compare fail-open and fail-closed behaviors."""
    
    def test_same_error_different_behavior(self):
        """Same Redis error, different outcomes based on mode."""
        # Fail-open
        limiter_open = RateLimiter("redis://localhost", fail_open=True)
        with patch.object(limiter_open, "_script", side_effect=RedisConnectionError()):
            result = limiter_open.check(...)
            assert result.allowed is True
        
        # Fail-closed
        limiter_closed = RateLimiter("redis://localhost", fail_open=False)
        with patch.object(limiter_closed, "_script", side_effect=RedisConnectionError()):
            with pytest.raises(RedisConnectionError):
                limiter_closed.check(...)
```

### Testing Edge Cases

```python
# tests/unit/test_edge_cases.py
class TestEdgeCases:
    """Test boundary conditions and edge cases."""
    
    def test_zero_limit_raises_error(self):
        """Limit of zero should raise ValueError."""
        limiter = RateLimiter("redis://localhost")
        
        with pytest.raises(ValueError, match="limit must be greater than 0"):
            limiter.check(..., limit=0, ...)
    
    def test_negative_window_raises_error(self):
        """Negative window should raise ValueError."""
        limiter = RateLimiter("redis://localhost")
        
        with pytest.raises(ValueError, match="window must be greater than 0"):
            limiter.check(..., window=-1)
    
    def test_exact_limit_allows_request(self):
        """Request at exact limit should be allowed."""
        limiter = RateLimiter("redis://localhost")
        
        with patch.object(limiter, "_script", return_value=[1, 10, 0]):
            result = limiter.check(..., limit=10, ...)
            assert result.allowed is True
    
    def test_one_over_limit_rejects_request(self):
        """Request over limit should be rejected."""
        limiter = RateLimiter("redis://localhost")
        
        with patch.object(limiter, "_script", return_value=[0, 11, 30]):
            result = limiter.check(..., limit=10, ...)
            assert result.allowed is False
            assert result.retry_after == 30
```

---

## Coverage Goals

### Target: 85%+ Overall

```
Name                          Stmts   Miss  Cover
-------------------------------------------------
rateforge/rate_limit/
  __init__.py                     5      0   100%
  algorithms.py                   3      0   100%
  backend.py                     15      1    93%
  decorator.py                   25      2    92%
  duration.py                    18      0   100%
  exceptions.py                  15      0   100%
  identity.py                    22      1    95%
  keys.py                         8      0   100%
  limiter.py                     35      2    94%
  models.py                      12      0   100%
  plans.py                       20      1    95%
  policy.py                      18      1    94%
-------------------------------------------------
TOTAL                           196      8    96%
```

### Per-Module Coverage Requirements

| Module | Min Coverage | Critical Tests |
|--------|--------------|----------------|
| **limiter.py** | 95% | Fail-open, fail-closed, script errors |
| **backend.py** | 90% | Connection errors, timeout handling |
| **exceptions.py** | 100% | All exception types |
| **algorithms.py** | 100% | Lua script logic |
| **identity.py** | 90% | All identity types |
| **policy.py** | 90% | Rate parsing, validation |

### Running Coverage

```bash
# Run tests with coverage
pytest --cov=rateforge --cov-report=term-missing

# Generate HTML report
pytest --cov=rateforge --cov-report=html

# Open HTML report
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

### Coverage Configuration (pyproject.toml)

```toml
[tool.coverage.run]
source = ["rateforge"]
branch = true
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/.venv/*",
]

[tool.coverage.report]
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]

[tool.coverage.html]
directory = "htmlcov"
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install pytest-cov
      
      - name: Run unit tests
        run: |
          pytest tests/unit/ --cov=rateforge --cov-report=xml
      
      - name: Run integration tests
        run: |
          pytest tests/integration/ --cov=rateforge --cov-report=xml --cov-append
      
      - name: Check coverage
        run: |
          coverage report --fail-under=85
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest tests/unit/
        language: system
        pass_filenames: false
        always_run: true
      
      - id: coverage
        name: coverage check
        entry: coverage report --fail-under=85
        language: system
        pass_filenames: false
        always_run: true
```

### Blocking PRs on Coverage

```yaml
# In GitHub branch protection rules:
- Require status checks to pass:
  - "test (ubuntu-latest)"
  - "coverage (85%)"

# In codecov config:
codecov:
  require_ci_to_pass: yes
  coverage:
    status:
      project:
        default:
          target: 85%
          threshold: 2%
```

---

## Test Data Management

### Fixtures

```python
# tests/conftest.py
import pytest
from rateforge import RateLimiter

@pytest.fixture
def limiter():
    """Create a RateLimiter instance."""
    return RateLimiter("redis://localhost:6379/0")

@pytest.fixture
def sample_context():
    """Create a sample RateLimitContext."""
    return RateLimitContext(
        endpoint="/api/test",
        ip="192.168.1.1",
        user_id="user:123",
    )

@pytest.fixture
def sample_policy():
    """Create a sample RateLimitPolicy."""
    return RateLimitPolicy(
        limit=100,
        window=60,
        identity="user",
    )

@pytest.fixture(scope="session")
def redis_client():
    """Create a Redis client for integration tests."""
    client = Redis.from_url("redis://localhost:6379/0")
    yield client
    client.flushdb()  # Cleanup
```

### Test Data Factories

```python
# tests/factories.py
from factory import Factory, Faker, Sequence
from rateforge.models import RateLimitContext, RateLimitPolicy

class RateLimitContextFactory(Factory):
    class Meta:
        model = RateLimitContext
    
    endpoint = Faker("uri")
    ip = Faker("ipv4")
    user_id = Sequence(lambda n: f"user:{n}")

class RateLimitPolicyFactory(Factory):
    class Meta:
        model = RateLimitPolicy
    
    limit = Faker("random_int", min=10, max=1000)
    window = 60
    identity = "user"
```

---

## Common Testing Pitfalls

### 1. Testing Implementation Instead of Behavior

```python
# ❌ BAD - Tests implementation
def test_script_called_with_correct_args():
    with patch.object(limiter, "_script") as mock_script:
        limiter.check(...)
        mock_script.assert_called_with(
            keys=["rateforge:user:123:/api/test"],
            args=[..., ..., ..., ...]
        )

# ✅ GOOD - Tests behavior
def test_request_allowed_under_limit():
    result = limiter.check(...)
    assert result.allowed is True
```

### 2. Over-Mocking

```python
# ❌ BAD - Mocking everything
@patch("rateforge.rate_limit.limiter.RateLimiter")
@patch("rateforge.rate_limit.backend.RedisBackend")
@patch("rateforge.rate_limit.models.RateLimitResult")
def test_too_many_mocks(mock_result, mock_backend, mock_limiter):
    ...

# ✅ GOOD - Mock only external dependencies
@patch("rateforge.rate_limit.limiter.RateLimiter._script")
def test_minimal_mocking(mock_script):
    ...
```

### 3. Flaky Time-Based Tests

```python
# ❌ BAD - Real time.sleep
def test_expiration():
    result1 = limiter.check(...)
    time.sleep(61)  # Slow and flaky!
    result2 = limiter.check(...)
    assert result2.allowed is True

# ✅ GOOD - Mock time
@patch("time.time")
def test_expiration_with_mocked_time(mock_time):
    mock_time.return_value = 1000.0
    result1 = limiter.check(...)
    
    mock_time.return_value = 1061.0  # Advance 61 seconds
    result2 = limiter.check(...)
    assert result2.allowed is True
```

---

## Related Documentation

- [Redis Failure Handling](./01-redis-failure-handling.md)
- [Interview Talking Points](./02-interview-talking-points.md)
- [Project Status](../PROJECT_STATUS.md)
