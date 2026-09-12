# RateForge Dockerfile
# Multi-stage build for production-ready container

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .[dev]

# Stage 2: Production
FROM python:3.11-slim as production

WORKDIR /app

# Create non-root user for security
RUN groupadd --gid 1000 rateforge \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home rateforge

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY tests/ ./tests/

# Set ownership to non-root user
RUN chown -R rateforge:rateforge /app

# Switch to non-root user
USER rateforge

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    RATEFORGE_REDIS_URL=redis://redis:6379/0 \
    RATEFORGE_FAIL_OPEN=true

# Expose port for FastAPI/Django dev server
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from rateforge.health import HealthChecker; \
        c = HealthChecker(); \
        r = c.check_redis(); \
        exit(0 if r.status == 'healthy' else 1)"

# Default command (can be overridden)
CMD ["python", "-m", "pytest", "tests/", "-v"]
