# RateForge

**Production-ready Redis-backed sliding-window rate limiter for Python APIs.**

> Django + FastAPI • Redis • Lua • Sliding Window • Plan Tiers • Kubernetes-ready

## Status

RateForge is currently under active development as a four-day open-source build sprint.

### Planned features

- Redis-backed sliding-window rate limiting
- Per-IP, per-user and per-API-key limits
- Free / Pro / Enterprise plan tiers
- Per-endpoint policies
- Django middleware
- FastAPI `Depends()` integration
- Atomic Redis Lua implementation
- Custom 429 JSON responses
- `Retry-After` and `X-RateLimit-*` headers
- Graceful Redis failure handling
- `/health` endpoint with five checks
- Kubernetes readiness/liveness support
- 85%+ automated test coverage
- GitHub Actions CI/CD
- PyPI distribution

## Architecture

```text
Django / FastAPI
       │
       ▼
RateForge Core
       │
       ├── Identity Resolver
       ├── Policy Engine
       └── RateLimiter
              │
              ▼
        Redis + Lua
              │
              ▼
        Sorted Set
```

## Sliding Window

RateForge stores request timestamps in Redis Sorted Sets.

```text
old requests       active window                 now
     │                    │                       │
─────x────────────────────xxxxxxxxxxxxxxxxxxxx───X
                          ↑
                     counted requests
```

Each request is atomically processed by Lua:

1. Remove expired requests.
2. Count active requests.
3. Compare with limit.
4. Insert the new request if allowed.
5. Return the result.

This avoids race conditions caused by separate `ZCARD` and `ZADD` operations.

## Example API

```python
from rateforge import RateLimiter

limiter = RateLimiter(
    "redis://localhost:6379/0"
)

result = limiter.check(
    identity="user:123",
    endpoint="/api/orders",
    limit=100,
    window=60,
)

if not result.allowed:
    print(result.retry_after)
```

## Rate syntax

The policy layer supports human-readable values such as:

```text
100/minute
10/min
1000/hour
5/second
```

## Plans

Example configuration:

```text
free       → 10 requests / minute
pro        → 100 requests / minute
enterprise → 1000 requests / minute
```

## Development

Create the virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Install the package:

```powershell
pip install -e ".[dev]"
```

Run tests:

```powershell
pytest -v
```

## Redis

For local development:

```powershell
docker run --name rateforge-redis -p 6379:6379 -d redis:7
```

Verify:

```powershell
python -c "from redis import Redis; print(Redis.from_url('redis://localhost:6379').ping())"
```

Expected:

```text
True
```

## Project Roadmap

### Day 1 — Core Engine
- [x] Redis backend
- [x] Sliding window
- [x] Lua script
- [x] Rate limiter
- [x] Initial tests

### Day 2 — Integrations
- [x] Identity context
- [x] Policy
- [x] Plans
- [x] Rate parser
- [ ] Failure handling
- [ ] Django integration
- [ ] FastAPI integration
- [ ] Integration tests

### Day 3 — Production
- [ ] Health endpoint
- [ ] Five health checks
- [ ] Kubernetes probes
- [ ] Logging
- [ ] Configuration
- [ ] Concurrency tests
- [ ] 85%+ coverage
- [ ] CI checks

### Day 4 — Release
- [ ] Full README
- [ ] Examples
- [ ] Dashboard GIF
- [ ] GitHub Actions
- [ ] PyPI
- [ ] Release
