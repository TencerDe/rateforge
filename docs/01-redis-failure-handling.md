# Redis Failure Handling

**Feature:** Production-ready Redis failure handling with fail-open/fail-closed modes  
**Status:** ✅ Implemented  
**Date:** 2026-09-06  
**Author:** Tanuj Sharma

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Design Decisions](#design-decisions)
3. [Exception Hierarchy](#exception-hierarchy)
4. [Fail-Open vs Fail-Closed](#fail-open-vs-fail-closed)
5. [Code Walkthrough](#code-walkthrough)
6. [Testing Strategy](#testing-strategy)
7. [Production Considerations](#production-considerations)

---

## Problem Statement

### The Anti-Pattern

Initial implementation used overly broad exception handling:

```python
# ❌ BEFORE - Too broad
try:
    result = self._script(...)
except Exception:
    if self.fail_open:
        return RateLimitResult(allowed=True, ...)
    raise
```

### Why This Is Dangerous

1. **Hides Bugs**: Catches ALL exceptions including programming errors (typos, logic bugs, invalid arguments)
2. **Debugging Nightmare**: No visibility into what actually failed
3. **Security Risk**: Could suppress authentication/authorization errors
4. **No Observability**: Cannot distinguish between "Redis is down" vs "Code is broken"

### Real-World Incident Example

```python
# Bug in rate limit calculation
limit = config["rate_limit"]  # KeyError if config missing

# With broad exception handling:
# - KeyError is caught
# - Request is allowed (fail-open)
# - Bug goes unnoticed for days
# - API is abused without rate limiting

# With specific exception handling:
# - KeyError raises normally
# - Developer is alerted immediately
# - Bug is fixed quickly
```

---

## Design Decisions

### 1. Exception Separation

**Principle:** Infrastructure failures ≠ Code bugs

| Category | Examples | Handling |
|----------|----------|----------|
| **Infrastructure** | Redis down, network timeout, busy loading | Apply fail-open/closed |
| **Code Bugs** | Invalid arguments, script errors, misconfigurations | Raise normally |

### 2. Specific Exception Catching

Only catch exceptions that represent **transient infrastructure issues**:

- `redis.exceptions.ConnectionError`
- `redis.exceptions.TimeoutError`
- `redis.exceptions.BusyLoadingError`

Let all other exceptions bubble up normally.

### 3. Structured Logging

Use `structlog` for contextual, machine-parseable logs:

```python
logger.warning(
    "redis_connection_failed",
    identity="user:123",
    endpoint="/api/orders",
    fail_open=True,
)
```

Benefits:
- Easy to query in log aggregation tools (Datadog, Splunk)
- Context preserved for debugging
- Alert rules can be specific

### 4. Exception Chain Preservation

Always preserve the original exception:

```python
try:
    ...
except redis.exceptions.ConnectionError as exc:
    raise RedisConnectionError("Redis unavailable") from exc
```

This allows:
- Full stack trace for debugging
- `exc.__cause__` inspection
- Better error messages

---

## Exception Hierarchy

```
RateForgeException (base)
│
├── RedisConnectionError
│   ├── ConnectionError (from redis-py)
│   ├── TimeoutError (from redis-py)
│   └── BusyLoadingError (from redis-py)
│
├── RateForgeInternalError (never suppressed)
│   ├── ScriptExecutionError
│   └── ConfigurationError
│
└── RedisUnavailableError (deprecated, kept for backward compatibility)
```

### Exception Usage Matrix

| Exception | When Raised | Suppressed? |
|-----------|-------------|-------------|
| `RedisConnectionError` | Redis unreachable, timeout | ✅ (if fail_open=True) |
| `ScriptExecutionError` | Lua script bug, invalid args | ❌ Never |
| `ConfigurationError` | Invalid Redis URL, missing config | ❌ Never |

---

## Fail-Open vs Fail-Closed

### Fail-Open Mode

```python
limiter = RateLimiter(
    "redis://localhost:6379/0",
    fail_open=True,  # Allow requests when Redis is down
)
```

**Behavior:**
```
Redis unavailable
       ↓
Log warning
       ↓
Allow request (no rate limiting)
       ↓
Add rate limit headers (limit, remaining = limit)
```

**When to Use:**
- API availability > strict rate limiting
- Redis is a soft dependency
- Temporary degradation acceptable

**Trade-offs:**
- ✅ API stays available during Redis outage
- ❌ Rate limiting temporarily disabled
- ❌ Risk of API abuse during outage

### Fail-Closed Mode

```python
limiter = RateLimiter(
    "redis://localhost:6379/0",
    fail_open=False,  # Reject requests when Redis is down
)
```

**Behavior:**
```
Redis unavailable
       ↓
Log warning
       ↓
Raise RedisConnectionError
       ↓
Return 503 Service Unavailable
```

**When to Use:**
- Rate limiting is a hard requirement
- Security/compliance needs strict enforcement
- Prefer downtime over abuse

**Trade-offs:**
- ✅ Strict rate limiting always enforced
- ❌ API unavailable during Redis outage
- ❌ May impact user experience

### Decision Framework

```
Is rate limiting a security requirement?
    │
    ├── YES → Fail-closed
    │         (e.g., payment APIs, auth endpoints)
    │
    └── NO  → Fail-open
              (e.g., public content APIs, read-only endpoints)
```

---

## Code Walkthrough

### Before vs After Comparison

#### RateLimiter.check() Method

**BEFORE (❌ Broad Exception):**

```python
try:
    result = self._script(
        keys=[key],
        args=[now, window, limit, request_id],
    )
except Exception:
    if self.fail_open:
        return RateLimitResult(allowed=True, ...)
    raise
```

**AFTER (✅ Specific Exceptions):**

```python
try:
    result = self._script(
        keys=[key],
        args=[now, window, limit, request_id],
    )
except RedisConnectionError:
    logger.warning(
        "redis_connection_failed",
        identity=identity,
        endpoint=endpoint,
        fail_open=self.fail_open,
    )
    if self.fail_open:
        return RateLimitResult(allowed=True, ...)
    raise
except Exception as exc:
    logger.error(
        "script_execution_failed",
        identity=identity,
        endpoint=endpoint,
        error=str(exc),
    )
    raise ScriptExecutionError(f"Lua script failed: {exc}") from exc
```

**Key Changes:**

1. **Specific Exception Catching**: Only `RedisConnectionError` triggers fail-open/closed
2. **Structured Logging**: Context-rich logs for debugging
3. **Exception Wrapping**: All other exceptions wrapped in `ScriptExecutionError`
4. **Exception Chain**: `from exc` preserves original error

### RedisBackend Enhancement

**BEFORE:**

```python
def ping(self) -> bool:
    try:
        return bool(self.redis.ping())
    except Exception as exc:
        raise RedisUnavailableError from exc
```

**AFTER:**

```python
def ping(self) -> bool:
    """Check Redis connectivity."""
    try:
        return bool(self.redis.ping())
    except (ConnectionError, TimeoutError) as exc:
        raise RedisConnectionError(f"Redis connection failed: {exc}") from exc
    except BusyLoadingError as exc:
        raise RedisConnectionError(f"Redis is loading dataset: {exc}") from exc
```

**Key Changes:**

1. **Specific Redis Exceptions**: Only connection-related exceptions caught
2. **Descriptive Messages**: Error messages include context
3. **Exception Chain**: Original exception preserved

---

## Testing Strategy

### Test Categories

| Category | Tests | Purpose |
|----------|-------|---------|
| Fail-Open | 5 | Verify requests allowed when Redis down |
| Fail-Closed | 3 | Verify errors raised when Redis down |
| Script Errors | 4 | Verify bugs NOT suppressed |
| Normal Operation | 3 | Verify rate limiting works |
| Configuration | 2 | Verify invalid config handling |
| Edge Cases | 3 | Verify concurrent failures, recovery |

### Mocking Strategy

**Why Mocks Over Integration Tests:**

1. **Speed**: Unit tests run in milliseconds vs seconds for integration
2. **Isolation**: Test failure handling without actual Redis outage
3. **Determinism**: No flaky tests due to network issues
4. **Coverage**: Can test edge cases hard to reproduce (e.g., concurrent failures)

**Mock Pattern:**

```python
from unittest.mock import patch

@patch("rateforge.rate_limit.limiter.RateLimiter._script")
def test_fail_open_allows_request(mock_script):
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
    assert result.remaining == 10
```

### Test Coverage Matrix

| Scenario | Fail-Open | Fail-Closed | Script Error |
|----------|-----------|-------------|--------------|
| Redis ConnectionError | ✅ Allow | ❌ Raise | N/A |
| Redis TimeoutError | ✅ Allow | ❌ Raise | N/A |
| Redis BusyLoadingError | ✅ Allow | ❌ Raise | N/A |
| Script ValueError | ❌ Raise | ❌ Raise | ✅ Raise |
| Script RuntimeError | ❌ Raise | ❌ Raise | ✅ Raise |
| Invalid Config | ❌ Raise | ❌ Raise | ❌ Raise |

---

## Production Considerations

### Monitoring & Alerting

#### Metrics to Track

```python
# Example Prometheus metrics
rateforge_redis_failures_total{mode="fail_open"}
rateforge_redis_failures_total{mode="fail_closed"}
rateforge_script_errors_total
rateforge_rate_limit_exceeded_total
```

#### Alert Rules

```yaml
# Alert: High Redis failure rate
- alert: RateForgeRedisFailuresHigh
  expr: rate(rateforge_redis_failures_total[5m]) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "RateForge Redis failures detected"
    description: "{{ $value }} failures per second"

# Alert: Script execution errors (bug indicator)
- alert: RateForgeScriptErrors
  expr: rate(rateforge_script_errors_total[1m]) > 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "RateForge script execution errors"
    description: "Possible bug in rate limiting logic"
```

### Kubernetes Health Checks

#### Liveness Probe

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3
```

#### Readiness Probe

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 3
```

**Health Check Behavior:**

| Mode | Redis Down | Health Status |
|------|------------|---------------|
| Fail-Open | Degraded (warning) | 200 OK |
| Fail-Closed | Unhealthy | 503 Service Unavailable |

### Runbook for On-Call Engineers

#### Scenario: Redis Outage Detected

**Step 1: Check Logs**

```bash
# Search for Redis connection failures
kubectl logs -l app=rateforge | grep "redis_connection_failed"
```

**Step 2: Assess Impact**

- **Fail-Open**: Rate limiting disabled, monitor for abuse
- **Fail-Closed**: API returning 503, consider failover

**Step 3: Redis Recovery**

```bash
# Check Redis status
kubectl get pods -l app=redis

# Restart Redis if needed
kubectl rollout restart deployment/redis
```

**Step 4: Post-Incident**

- Review failure rate metrics
- Check if fail-open/closed mode was appropriate
- Update runbook if new failure modes discovered

### Scalability Considerations

#### Redis Cluster

For high-traffic scenarios, use Redis Cluster:

```python
limiter = RateLimiter(
    "redis://node1:6379,redis://node2:6379,redis://node3:6379",
    fail_open=True,
)
```

**Benefits:**
- Horizontal scaling
- Automatic failover
- No single point of failure

#### Connection Pooling

RedisBackend uses connection pooling by default:

```python
self.redis = Redis.from_url(
    redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    max_connections=50,  # Configurable
)
```

---

## Interview Talking Points

### Backend Depth

1. **Atomic Operations**: "We use Lua scripts to ensure rate limit checks are atomic in Redis"
2. **Graceful Degradation**: "Fail-open mode allows API to stay available during Redis outages"
3. **Observability**: "Structured logging with structlog makes debugging production issues easier"

### System Design

1. **Trade-off Analysis**: "Fail-open vs fail-closed depends on whether rate limiting is a security requirement"
2. **Exception Design**: "Separating infrastructure failures from code bugs improves debugging"
3. **Scalability**: "Redis Sorted Sets + Lua scripts scale horizontally with Redis Cluster"

### Production Readiness

1. **Monitoring**: "We track Redis failure rates and script errors as key metrics"
2. **Health Checks**: "Different health statuses for fail-open vs fail-closed modes"
3. **Runbooks**: "Clear escalation paths for on-call engineers during outages"

---

## Related Documentation

- [Interview Talking Points](./02-interview-talking-points.md)
- [Testing Strategy](./03-testing-strategy.md)
- [Architecture Overview](../ARCHITECTURE.md)
- [Project Status](../PROJECT_STATUS.md)
