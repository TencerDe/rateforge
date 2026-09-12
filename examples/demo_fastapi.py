"""
RateForge Demo - FastAPI Example

A simple FastAPI application demonstrating RateForge rate limiting.

Endpoints:
- GET / - Rate limited home endpoint
- GET /health - Health check
- GET /healthz - Kubernetes health check

Run with:
    docker-compose --profile demo up
    
Or locally:
    uvicorn examples.demo_fastapi:app --reload
"""

from fastapi import FastAPI, Depends
from rateforge.fastapi import (
    create_health_endpoint,
    rate_limit,
    rate_limit_dependency,
)

# Create FastAPI app
app = FastAPI(
    title="RateForge Demo",
    description="Example FastAPI application with RateForge rate limiting",
    version="0.1.0",
)

# Add health check endpoints
create_health_endpoint(app)


# Home endpoint with rate limiting (100 requests per minute)
@app.get("/")
@rate_limit("100/minute")
async def home():
    """
    Rate limited home endpoint.
    
    Returns a welcome message.
    Rate limit: 100 requests per minute per IP
    """
    return {
        "message": "Welcome to RateForge Demo!",
        "docs": "/docs",
        "health": "/health",
    }


# Premium endpoint with higher limits (1000 requests per minute)
@app.get("/premium")
@rate_limit("1000/minute")
async def premium_endpoint():
    """
    Premium endpoint with higher rate limits.
    
    Rate limit: 1000 requests per minute per IP
    """
    return {
        "message": "Premium endpoint accessed!",
        "tier": "premium",
        "rate_limit": "1000/minute",
    }


# API endpoint with dependency injection
@app.get("/api/data", dependencies=[Depends(rate_limit_dependency("50/minute"))])
async def api_data():
    """
    API endpoint using Depends() for rate limiting.
    
    Rate limit: 50 requests per minute per IP
    """
    return {
        "data": ["item1", "item2", "item3"],
        "rate_limit": "50/minute",
    }


# User-specific endpoint (requires authentication in real app)
@app.get("/user/profile")
@rate_limit("10/minute", identity="user")
async def user_profile():
    """
    User-specific rate limiting.
    
    Rate limit: 10 requests per minute per user
    (would extract user ID from authentication in real app)
    """
    return {
        "user_id": "demo_user_123",
        "profile": {
            "name": "Demo User",
            "email": "demo@example.com",
        },
        "rate_limit": "10/minute per user",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
