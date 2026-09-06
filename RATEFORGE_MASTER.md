# RateForge — Master Development Blueprint

> **Project:** RateForge  
> **Purpose:** Production-ready Redis-backed sliding-window rate limiter for Python applications.  
> **Target:** Django + FastAPI, health checks, Kubernetes readiness, CI/CD, 85%+ test coverage, PyPI publication.  
> **Sprint:** 4 days  
> **Current checkpoint:** End of Day 1 + approximately halfway through Day 2.

---

## 1. Project Status

| Day | Status | Completion |
|---|---|---:|
| Day 1 — Core Engine | Complete | 100% |
| Day 2 — Integrations | In progress | ~50% |
| Day 3 — Production Engineering | Pending | 0% |
| Day 4 — Open Source + Release | Pending | 0% |

**Overall project estimate: ~38% complete.**

### Completed

- [x] `src` package layout
- [x] `pyproject.toml`
- [x] Editable package installation
- [x] Redis backend
- [x] Redis Sorted Set sliding-window algorithm
- [x] Atomic Lua script
- [x] `RateLimitResult`
- [x] `RateLimiter.check()`
- [x] Redis Docker setup
- [x] Initial pytest integration
- [x] `RateLimitContext`
- [x] Identity types
- [x] Identity resolver
- [x] Plan registry
- [x] Rate parser
- [x] Policy model
- [x] Redis key builder
- [x] `RateLimitExceeded`
- [x] Django integration skeleton
- [x] FastAPI integration skeleton

### Remaining

- [ ] Correct Redis failure handling
- [ ] Fail-open / fail-closed tests
- [ ] Final decorator API
- [ ] Complete Django integration
- [ ] Complete FastAPI integration
- [ ] Plan-aware endpoint API
- [ ] Health endpoint and five checks
- [ ] Kubernetes probes
- [ ] Structured logging/configuration
- [ ] Full integration/concurrency tests
- [ ] 85%+ coverage
- [ ] CI/CD
- [ ] README + examples
- [ ] Dashboard GIF
- [ ] PyPI release

---

## 2. Final Architecture

```text
                         ┌─────────────────────┐
                         │   Django / FastAPI  │
                         │   Framework Layer   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   RateForge Core    │
                         │                     │
                         │ RateLimiter         │
                         │ Policy              │
                         │ Identity Resolver   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Redis Backend    │
                         │                     │
                         │ Sorted Sets + Lua   │
                         └─────────────────────┘
```

### Design rule

Framework integrations must translate framework-specific requests into `RateLimitContext`. The core engine must not depend on Django or FastAPI.

---

## 3. Target Repository

```text
rateforge/
├── src/
│   └── rateforge/
│       ├── __init__.py
│       │
│       ├── rate_limit/
│       │   ├── __init__.py
│       │   ├── limiter.py
│       │   ├── backend.py
│       │   ├── algorithms.py
│       │   ├── models.py
│       │   ├── policy.py
│       │   ├── identity.py
│       │   ├── plans.py
│       │   ├── keys.py
│       │   ├── duration.py
│       │   ├── decorator.py
│       │   ├── exceptions.py
│       │   └── responses.py
│       │
│       ├── integrations/
│       │   ├── __init__.py
│       │   ├── django.py
│       │   └── fastapi.py
│       │
│       └── health/
│           ├── __init__.py
│           └── checks.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── django/
│   └── fastapi/
│
├── examples/
│   ├── django/
│   └── fastapi/
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── docker-compose.yml
├── pyproject.toml
├── README.md
├── LICENSE
└── CHANGELOG.md
```

---

## 4. Core Features

### Rate limiting

- Per IP
- Per authenticated user
- Per API key
- Per plan tier
- Per endpoint
- Redis-backed storage
- Sliding-window algorithm
- Atomic Redis operations
- Custom 429 response bodies
- `Retry-After`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- Graceful Redis failure
- Configurable fail-open / fail-closed behavior

### Framework support

- Django middleware
- FastAPI `Depends()`
- Framework-independent core

### Production support

- `/health`
- Five service checks
- Kubernetes-ready health behavior
- Docker
- GitHub Actions
- pytest
- coverage
- Ruff
- MyPy
- PyPI packaging

---

## 5. Sliding Window Algorithm

RateForge uses a Redis Sorted Set (`ZSET`) where:

- score = request timestamp
- member = unique request ID

Example:

```text
rateforge:user:123:/api/orders

Score        Request
────────────────────────
1723456001   req-a
1723456004   req-b
1723456010   req-c
1723456017   req-d
```

For each request:

```text
                 Incoming Request
                         │
                         ▼
               Calculate window start
                         │
                         ▼
            Remove expired ZSET entries
                         │
                         ▼
                 Count active entries
                         │
                  ┌──────┴──────┐
                  │             │
             count >= limit     │
                  │             │
                 YES            NO
                  │             │
                  ▼             ▼
               Reject       Add request
                  │             │
                  ▼             ▼
                 429          Allow
```

### Why Lua?

A naive implementation could do:

```text
ZCARD
  ↓
compare
  ↓
ZADD
```

as separate operations. Concurrent requests can race between these commands.

RateForge executes cleanup, counting, checking, and insertion inside one Redis Lua script so the operation is atomic.

---

## 6. Redis Key Design

Current pattern:

```text
rateforge:{identity}:{endpoint}
```

Examples:

```text
rateforge:user:123:/api/orders
rateforge:ip:127.0.0.1:/api/orders
rateforge:api_key:abc123:/api/orders
rateforge:plan:free:/api/orders
```

Key generation belongs in `keys.py`, not inside the framework adapters.

---

## 7. Core Models

### `RateLimitContext`

```python
@dataclass(frozen=True)
class RateLimitContext:
    endpoint: str
    ip: str | None = None
    user_id: str | None = None
    api_key: str | None = None
    plan: str | None = None
```

### `RateLimitResult`

```python
@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_at: int
```

### `IdentityType`

```text
IP
USER
API_KEY
PLAN
```

---

## 8. Policy and Rate Syntax

RateForge accepts human-readable rates:

```text
100/minute
10/min
1000/hour
5/second
5/s
```

Parser output:

```text
"100/minute"
       ↓
limit = 100
window = 60 seconds
```

Policy example:

```python
RateLimitPolicy(
    limit=100,
    window=60,
    identity="user",
)
```

---

## 9. Plan Tiers

Target built-in example:

| Plan | Requests | Window |
|---|---:|---:|
| Free | 10 | 60s |
| Pro | 100 | 60s |
| Enterprise | 1000 | 60s |

The implementation uses a registry so custom plans can be added later.

---

## 10. HTTP Behavior

Successful requests should expose:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1723456789
```

When the limit is exceeded:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
```

Target JSON:

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after": 42
}
```

---

## 11. Redis Failure Policy

Two modes:

### Fail open

```text
Redis unavailable
       ↓
Allow request
       ↓
Log failure
```

Useful when API availability is more important than strict enforcement.

### Fail closed

```text
Redis unavailable
       ↓
Reject / service unavailable
```

Useful where strict rate limiting is a hard requirement.

### Critical implementation rule

Do not catch every `Exception` and treat it as a Redis outage.

Correct behavior:

```text
Redis connection failure → apply configured fallback

Programming bug → raise normally
```

This is the next development task.

---

# 12. Django Integration

Target:

```python
MIDDLEWARE = [
    ...
    "rateforge.integrations.django.RateLimitMiddleware",
]
```

Middleware responsibilities:

1. Extract endpoint.
2. Extract client IP.
3. Extract authenticated user.
4. Extract API key.
5. Resolve plan.
6. Build `RateLimitContext`.
7. Execute core limiter.
8. Return 429 when blocked.
9. Add rate-limit headers when allowed.
10. Apply Redis failure policy.

---

# 13. FastAPI Integration

Target:

```python
@app.get(
    "/orders",
    dependencies=[
        Depends(rate_limit_dependency)
    ],
)
async def orders():
    return {"orders": []}
```

Responsibilities mirror Django:

```text
Request
  ↓
Build RateLimitContext
  ↓
Resolve policy
  ↓
RateForge Core
  ↓
Allow / 429
```

---

# 14. Health Endpoint

Target:

```http
GET /health
```

Response:

```json
{
  "status": "healthy",
  "checks": {
    "redis": {
      "status": "healthy",
      "latency_ms": 1.4
    },
    "database": {
      "status": "healthy"
    },
    "filesystem": {
      "status": "healthy"
    },
    "memory": {
      "status": "healthy"
    },
    "config": {
      "status": "healthy"
    }
  }
}
```

Expected statuses:

```text
200 → healthy
503 → unhealthy
```

Five planned checks:

1. Redis
2. Database
3. Filesystem
4. Memory
5. Configuration

---

# 15. Kubernetes

The health endpoint must support:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000

readinessProbe:
  httpGet:
    path: /health
    port: 8000
```

The implementation should clearly distinguish application health from dependency-specific details where appropriate.

---

# 16. Testing Strategy

Target **85%+ coverage**, despite the original requirement being 70%.

### Unit tests

```text
tests/unit/
├── test_limiter.py
├── test_identity.py
├── test_duration.py
├── test_plans.py
├── test_policy.py
└── test_keys.py
```

### Integration tests

```text
tests/integration/
├── test_redis_backend.py
├── test_sliding_window.py
├── test_concurrency.py
└── test_failure_modes.py
```

### Django tests

```text
tests/django/
└── test_middleware.py
```

### FastAPI tests

```text
tests/fastapi/
└── test_dependency.py
```

Critical cases:

- first request allowed
- request at exact limit allowed
- request above limit rejected
- sliding-window expiration
- retry-after calculation
- separate users have separate buckets
- separate endpoints have separate buckets
- IP identity
- authenticated user identity
- API-key identity
- plan tiers
- Redis unavailable + fail-open
- Redis unavailable + fail-closed
- concurrent requests
- custom responses
- rate-limit headers

---

# 17. Tooling

### `pyproject.toml`

Package metadata, dependencies, build system, pytest configuration, coverage configuration.

Core dependency:

```text
redis>=5.0
```

Optional integrations:

```text
django>=4.2
fastapi>=0.100
```

Development tooling:

```text
pytest
pytest-cov
ruff
mypy
```

---

# 18. CI/CD

Target pipeline:

```text
                    Git Push / PR
                          │
                          ▼
                    GitHub Actions
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
           Ruff         MyPy         Pytest
                                      │
                                      ▼
                                  Coverage
                                      │
                                      ▼
                                Build package
```

Release pipeline:

```text
Git tag
  ↓
Build wheel + sdist
  ↓
GitHub Actions
  ↓
PyPI Trusted Publishing
```

No long-lived PyPI token should be committed to the repository.

---

# 19. Four-Day Sprint

## Day 1 — Core Engine — COMPLETE

### Delivered

- project structure
- virtual environment
- package metadata
- Redis backend
- Sorted Set algorithm
- Lua script
- rate limiter
- result model
- initial integration test

### Definition of done

```text
Redis works
+
Sliding window works
+
Limit is enforced
+
Package imports correctly
```

---

## Day 2 — Framework Integrations — IN PROGRESS

### Complete

- identity model
- context model
- identity resolver
- plan registry
- duration parser
- policy model
- Redis key builder
- rate-limit exception
- decorator skeleton
- Django skeleton
- FastAPI skeleton

### Remaining

1. Redis failure handling
2. fail-open
3. fail-closed
4. proper decorator API
5. async decorator support
6. Django configuration
7. FastAPI configuration
8. Django tests
9. FastAPI tests
10. plan-aware integration
11. custom response handling
12. rate-limit header handling

---

## Day 3 — Production Engineering

### Build

- health module
- five health checks
- `/health`
- Docker Compose
- Kubernetes probes
- configuration management
- structured logging
- Redis failure tests
- concurrency tests
- coverage enforcement
- Ruff
- MyPy

### Definition of done

```text
pytest passes
+
coverage >= 85%
+
lint passes
+
type checks pass
+
health endpoint works
+
Kubernetes probes work
```

---

## Day 4 — Open Source + Release

### Build

- complete README
- architecture diagrams
- Django example
- FastAPI example
- dashboard
- dashboard GIF
- API reference
- configuration reference
- CHANGELOG
- MIT license
- contributing guidance
- CI/CD
- package build
- PyPI publication
- GitHub release

### Definition of done

```text
pip install rateforge
        ↓
working package
        ↓
working examples
        ↓
documented API
        ↓
automated CI
        ↓
published release
```

---

# 20. Final README Content

The final README should contain:

1. Project overview
2. Feature list
3. Architecture diagram
4. Installation
5. Quick start
6. Django integration
7. FastAPI integration
8. IP limiting
9. User limiting
10. API-key limiting
11. Plan tiers
12. Custom policies
13. HTTP headers
14. Redis configuration
15. Fail-open / fail-closed
16. Health checks
17. Docker
18. Kubernetes
19. Testing
20. Development setup
21. Contributing
22. License
23. Release process

---

# 21. Dashboard GIF

The README demo should visually demonstrate:

```text
Normal requests
      ↓
Rate limit approaches
      ↓
Limit reached
      ↓
HTTP 429
      ↓
Retry-After shown
      ↓
Window expires
      ↓
Requests accepted
```

Dashboard metrics should include:

- total requests
- allowed requests
- blocked requests
- current plan
- current limit
- Redis status
- remaining quota

---

# 22. Next Development Checkpoint

When continuing development, start here:

## NEXT TASK: Redis Failure Handling

Current problem:

```python
try:
    result = self._script(...)
except Exception:
    if self.fail_open:
        ...
```

This is too broad.

It must become:

```text
Redis connection/timeout error
        ↓
fail_open? ── yes → allow + log
        │
        no
        ↓
fail closed behavior

Other programming exceptions
        ↓
raise normally
```

Then immediately write tests for:

- Redis available
- Redis unavailable + fail-open
- Redis unavailable + fail-closed
- unexpected programming error

**Do not move to additional framework features until these tests pass.**

---

# 23. Progress Tracker

```text
DAY 1  ████████████████████ 100%
DAY 2  ██████████░░░░░░░░░░  50%
DAY 3  ░░░░░░░░░░░░░░░░░░░░   0%
DAY 4  ░░░░░░░░░░░░░░░░░░░░   0%

TOTAL  ████████░░░░░░░░░░░░ ~38%
```

### Current project state

**Working:** Core Redis-backed sliding-window limiter.

**Being built:** Framework abstraction and integrations.

**Not started:** Production health/observability, CI/CD, release, full documentation.

**Next exact coding task:** Harden Redis failure handling.
