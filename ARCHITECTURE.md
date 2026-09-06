# RateForge Architecture

## High-Level Flow

```text
                    HTTP Request
                         │
                         ▼
             ┌───────────────────────┐
             │ Django / FastAPI      │
             │ Integration           │
             └───────────┬───────────┘
                         │
                         ▼
             ┌───────────────────────┐
             │ RateLimitContext      │
             │                       │
             │ IP / User / API Key   │
             │ Plan / Endpoint       │
             └───────────┬───────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       Identity Resolver       Policy / Plan
              │                     │
              └──────────┬──────────┘
                         ▼
                ┌────────────────┐
                │  RateLimiter   │
                └───────┬────────┘
                        ▼
                ┌────────────────┐
                │ Redis Backend  │
                │                │
                │ ZSET + Lua     │
                └───────┬────────┘
                        ▼
                  RateLimitResult
                        │
               ┌────────┴────────┐
               ▼                 ▼
             Allow               429
```

## Data Model

```text
rateforge:{identity}:{endpoint}
```

Example:

```text
rateforge:user:123:/api/orders
```

The sorted set contains:

```text
timestamp → request_id
```

## Atomic Operation

```text
BEGIN
  ↓
ZREMRANGEBYSCORE
  ↓
ZCARD
  ↓
IF count >= limit
  ├── YES → calculate retry-after → reject
  └── NO  → ZADD → EXPIRE → allow
  ↓
END
```

The whole operation is executed atomically inside Redis.
