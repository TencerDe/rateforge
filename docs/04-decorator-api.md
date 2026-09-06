# RateForge Decorator API

**Feature:** Production-ready decorator API for Django and FastAPI  
**Status:** ✅ Implemented  
**Date:** 2026-09-06

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Decorator API Reference](#decorator-api-reference)
3. [Django Integration](#django-integration)
4. [FastAPI Integration](#fastapi-integration)
5. [Identity Types](#identity-types)
6. [Configuration](#configuration)
7. [Response Format](#response-format)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Installation

```bash
pip install rateforge
```

### Environment Setup

```bash
# .env
RATEFORGE_REDIS_URL="redis://localhost:6379/0"
RATEFORGE_FAIL_OPEN="true"
```

### Django Example

```python
# views.py
from rateforge.django import rate_limit

@rate_limit("100/minute")
def home(request):
    return HttpResponse("Hello!")

@login_required
@rate_limit("10/minute", identity="user")
def create_order(request):
    ...
```

### FastAPI Example

```python
# main.py
from fastapi import FastAPI, Depends
from rateforge.fastapi import rate_limit, rate_limit_dependency

app = FastAPI()

# Approach 1: Decorator
@app.get("/users")
@rate_limit("100/minute")
async def get_users():
    return {"users": [...]}

# Approach 2: Dependency
@app.get("/orders", dependencies=[Depends(rate_limit_dependency("50/minute"))])
async def get_orders():
    return {"orders": [...]}
```

---

## Decorator API Reference

### `rate_limit(rate, *, identity="ip", bypass_if_authenticated=False)`

**Args:**
- `rate` (str): Human-readable rate limit
  - Format: `<count>/<duration>`
  - Examples: `"100/minute"`, `"1000/hour"`, `"5/second"`
- `identity` (str | callable): Identity type or extractor
  - Options: `"ip"`, `"user"`, `"api_key"`, `"plan"`
  - Callable: `lambda request: f"custom:{request.user.id}"`
- `bypass_if_authenticated` (bool): Skip rate limiting for authenticated users

**Raises:**
- `RateLimitExceeded`: When rate limit is exceeded

**Returns:**
- Decorated function with rate limiting

---

## Django Integration

### Decorator Usage

```python
from django.http import HttpResponse
from rateforge.django import rate_limit

# IP-based limiting (default)
@rate_limit("100/minute")
def home(request):
    return HttpResponse("Hello!")

# User-based limiting
@login_required
@rate_limit("10/minute", identity="user")
def create_order(request):
    ...

# Bypass for authenticated users
@rate_limit("50/hour", bypass_if_authenticated=True)
def public_api(request):
    # Anonymous: 50/hour
    # Authenticated: unlimited
    ...
```

### Middleware Usage

```python
# settings.py
MIDDLEWARE = [
    ...
    "rateforge.integrations.django.RateLimitMiddleware",
]

# Optional configuration
RATEFORGE_CONFIG = {
    "default_rate": "100/minute",
    "identity": "ip",
}
```

### Exception Handler

```python
# views.py
from rateforge.django import handle_exception, rate_limit

@handle_exception
@rate_limit("100/minute")
def my_view(request):
    ...
```

---

## FastAPI Integration

### Decorator Usage

```python
from fastapi import FastAPI
from rateforge.fastapi import rate_limit

app = FastAPI()

@app.get("/users")
@rate_limit("100/minute")
async def get_users():
    return {"users": [...]}

@app.post("/orders")
@rate_limit("10/minute", identity="user")
async def create_order():
    ...
```

### Dependency Injection

```python
from fastapi import FastAPI, Depends
from rateforge.fastapi import rate_limit_dependency

app = FastAPI()

# Global dependency for all routes
app.add_dependency(rate_limit_dependency("100/minute"))

# Per-endpoint dependency
@app.get("/premium", dependencies=[Depends(rate_limit_dependency("1000/hour"))])
async def premium_endpoint():
    ...

# Multiple dependencies
@app.get(
    "/special",
    dependencies=[
        Depends(rate_limit_dependency("50/minute")),
        Depends(other_dependency),
    ]
)
async def special_endpoint():
    ...
```

### Setup Function

```python
from fastapi import FastAPI
from rateforge.fastapi import setup_rate_limiting

app = FastAPI()
setup_rate_limiting(app)  # Registers exception handler

@app.get("/users")
async def get_users():
    ...
```

---

## Identity Types

### IP-Based (Default)

```python
@rate_limit("100/minute")
def view(request):
    # Limits by client IP address
    ...
```

**Extracts IP from:**
- `X-Forwarded-For` header (if present)
- `REMOTE_ADDR` (Django) or `request.client` (FastAPI)

### User-Based

```python
@login_required
@rate_limit("10/minute", identity="user")
def user_action(request):
    # Limits by authenticated user ID
    ...
```

**Requirements:**
- User must be authenticated
- User object must have `id` or `pk` attribute

### API Key-Based

```python
@rate_limit("1000/hour", identity="api_key")
def api_endpoint(request):
    # Limits by X-API-Key header
    ...
```

**Requirements:**
- Client must send `X-API-Key` header

### Plan-Based

```python
@rate_limit("100/minute", identity="plan")
def tiered_endpoint(request):
    # Limits by user's plan (free/pro/enterprise)
    ...
```

**Requirements:**
- User object or request.state must have `plan` attribute

### Custom Identity Extractor

```python
# Extract by organization ID
@rate_limit(
    "1000/hour",
    identity=lambda request: f"org:{request.organization.id}",
)
def org_endpoint(request):
    ...

# Extract by custom header
@rate_limit(
    "100/minute",
    identity=lambda request: f"device:{request.headers.get('X-Device-ID')}",
)
def device_endpoint(request):
    ...
```

---

## Configuration

### Environment Variables

```bash
# Required
RATEFORGE_REDIS_URL="redis://localhost:6379/0"

# Optional
RATEFORGE_FAIL_OPEN="true"  # true/false
RATEFORGE_DEFAULT_RATE="100/minute"
```

### Django Settings

```python
# settings.py
RATEFORGE_CONFIG = {
    "default_rate": "100/minute",
    "identity": "ip",
}
```

### Programmatic Configuration

```python
from rateforge import configure_limiter

configure_limiter(
    "redis://my-redis:6379/0",
    fail_open=False,
)
```

---

## Response Format

### 429 Too Many Requests

**Headers:**
```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1723456789
Retry-After: 45
```

**Body:**
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after": 45
}
```

### Rate Limit Headers (on all responses)

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1723456789
```

---

## Troubleshooting

### Issue: "Redis connection failed"

**Solution:**
1. Check Redis is running: `redis-cli ping`
2. Verify `RATEFORGE_REDIS_URL` environment variable
3. Check network connectivity to Redis

### Issue: "User not authenticated"

**Solution:**
- Ensure `@login_required` decorator is applied (Django)
- Ensure authentication middleware is configured (FastAPI)
- Verify user object has `is_authenticated` property

### Issue: "API key not provided"

**Solution:**
- Client must send `X-API-Key` header
- Check header name is correct (case-sensitive)

### Issue: Rate limiting not working

**Solution:**
1. Verify decorator is applied correctly
2. Check Redis connection (see first issue)
3. Enable logging to see rate limit events:
   ```python
   import logging
   logging.basicConfig(level=logging.WARNING)
   ```

### Issue: Too many false positives

**Solution:**
- Increase rate limit window
- Use user-based instead of IP-based (if behind NAT)
- Adjust `X-Forwarded-For` header parsing

---

## Examples

### Django: Blog API

```python
from django.http import JsonResponse
from rateforge.django import rate_limit

@rate_limit("100/minute")
def get_posts(request):
    return JsonResponse({"posts": [...]})

@login_required
@rate_limit("10/minute", identity="user")
def create_post(request):
    ...

@rate_limit("5/minute", bypass_if_authenticated=True)
def subscribe_newsletter(request):
    # Anonymous: 5/minute
    # Authenticated: unlimited
    ...
```

### FastAPI: E-commerce API

```python
from fastapi import FastAPI, Depends, HTTPException
from rateforge.fastapi import rate_limit, rate_limit_dependency

app = FastAPI()

# Public endpoints
@app.get("/products")
@rate_limit("100/minute")
async def get_products():
    return {"products": [...]}

# User endpoints
@app.post("/orders")
@rate_limit("10/minute", identity="user")
async def create_order():
    ...

# Premium endpoints
@app.get("/analytics")
@rate_limit("1000/hour", identity="plan")
async def get_analytics():
    ...

# API key endpoints
@app.get("/external/data")
@rate_limit("500/hour", identity="api_key")
async def get_external_data():
    ...
```

---

## Related Documentation

- [Redis Failure Handling](./01-redis-failure-handling.md)
- [Interview Talking Points](./02-interview-talking-points.md)
- [Testing Strategy](./03-testing-strategy.md)
- [Project Status](../PROJECT_STATUS.md)
