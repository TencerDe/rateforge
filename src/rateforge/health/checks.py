"""
RateForge health module.

Provides:
- Five health checks (Redis, Database, Filesystem, Memory, Config)
- Health check results with status and latency
- Framework-agnostic health checker
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    status: str  # "healthy", "unhealthy", "degraded"
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "status": self.status,
            "timestamp": self.timestamp,
        }

        if self.latency_ms is not None:
            result["latency_ms"] = self.latency_ms

        if self.error:
            result["error"] = self.error

        if self.details:
            result["details"] = self.details

        return result


class HealthChecker:
    """
    Perform health checks for RateForge.

    Five checks:
    1. Redis connectivity and latency
    2. Database (placeholder for future)
    3. Filesystem write permissions
    4. Memory usage
    5. Configuration validity

    Example:
        >>> checker = HealthChecker()
        >>> results = checker.run_all_checks()
        >>> print(results["redis"].status)
        "healthy"
    """

    def check_redis(self) -> HealthCheckResult:
        """
        Check Redis connectivity and latency.

        Returns:
            HealthCheckResult with status and latency
        """
        start = time.time()

        try:
            from rateforge import get_default_limiter

            limiter = get_default_limiter()
            is_connected = limiter.backend.ping()
            latency = (time.time() - start) * 1000

            if is_connected:
                return HealthCheckResult(
                    name="redis",
                    status="healthy",
                    latency_ms=round(latency, 2),
                    details={"message": "Redis connection successful"},
                )
            else:
                return HealthCheckResult(
                    name="redis",
                    status="unhealthy",
                    latency_ms=round(latency, 2),
                    error="Redis ping failed",
                )

        except Exception as exc:
            latency = (time.time() - start) * 1000
            return HealthCheckResult(
                name="redis",
                status="unhealthy",
                latency_ms=round(latency, 2),
                error=str(exc),
            )

    def check_database(self) -> HealthCheckResult:
        """
        Check database connectivity (placeholder for future).

        RateForge currently doesn't use a database, but this check
        is included for future extensibility.

        Returns:
            HealthCheckResult with placeholder status
        """
        return HealthCheckResult(
            name="database",
            status="healthy",
            details={"note": "Database not configured in RateForge"},
        )

    def check_filesystem(self) -> HealthCheckResult:
        """
        Check filesystem write permissions.

        Tests ability to write to temporary directory.

        Returns:
            HealthCheckResult with status
        """
        import tempfile

        try:
            # Test write to temp directory
            with tempfile.NamedTemporaryFile(delete=True) as f:
                f.write(b"rateforge_health_check")
                f.flush()

            return HealthCheckResult(
                name="filesystem",
                status="healthy",
                details={"message": "Filesystem write test successful"},
            )

        except Exception as exc:
            return HealthCheckResult(
                name="filesystem",
                status="unhealthy",
                error=f"Filesystem write failed: {exc}",
            )

    def check_memory(self) -> HealthCheckResult:
        """
        Check memory usage.

        Uses psutil if available, otherwise returns degraded status.

        Returns:
            HealthCheckResult with memory usage details
        """
        try:
            import psutil

            memory = psutil.virtual_memory()
            usage_percent = memory.percent

            # Determine status based on usage
            if usage_percent < 70:
                status = "healthy"
            elif usage_percent < 90:
                status = "degraded"
            else:
                status = "unhealthy"

            return HealthCheckResult(
                name="memory",
                status=status,
                details={
                    "usage_percent": usage_percent,
                    "available_mb": round(memory.available / (1024 * 1024), 2),
                    "total_mb": round(memory.total / (1024 * 1024), 2),
                },
            )

        except ImportError:
            # psutil not installed
            return HealthCheckResult(
                name="memory",
                status="degraded",
                details={"note": "psutil not installed, cannot check memory"},
            )

        except Exception as exc:
            return HealthCheckResult(
                name="memory",
                status="unhealthy",
                error=str(exc),
            )

    def check_config(self) -> HealthCheckResult:
        """
        Check configuration validity.

        Validates environment variables and configuration.

        Returns:
            HealthCheckResult with configuration status
        """
        try:
            redis_url = os.getenv("RATEFORGE_REDIS_URL")
            fail_open_str = os.getenv("RATEFORGE_FAIL_OPEN", "true")
            fail_open = fail_open_str.lower() == "true"

            details = {
                "fail_open": fail_open,
            }

            if not redis_url:
                return HealthCheckResult(
                    name="config",
                    status="degraded",
                    error="RATEFORGE_REDIS_URL not set, using default",
                    details=details,
                )

            # Validate Redis URL format
            if not redis_url.startswith(("redis://", "rediss://")):
                return HealthCheckResult(
                    name="config",
                    status="unhealthy",
                    error="Invalid Redis URL format (must start with redis:// or rediss://)",
                    details=details,
                )

            details["redis_url_configured"] = True

            return HealthCheckResult(
                name="config",
                status="healthy",
                details=details,
            )

        except Exception as exc:
            return HealthCheckResult(
                name="config",
                status="unhealthy",
                error=str(exc),
            )

    def run_all_checks(self) -> dict[str, HealthCheckResult]:
        """
        Run all health checks and return results.

        Returns:
            Dictionary mapping check names to results

        Example:
            >>> checker = HealthChecker()
            >>> results = checker.run_all_checks()
            >>> results["redis"].status
            "healthy"
        """
        return {
            "redis": self.check_redis(),
            "database": self.check_database(),
            "filesystem": self.check_filesystem(),
            "memory": self.check_memory(),
            "config": self.check_config(),
        }

    def get_overall_status(self, results: dict[str, HealthCheckResult]) -> str:
        """
        Determine overall health status from individual checks.

        Args:
            results: Dictionary of health check results

        Returns:
            Overall status: "healthy", "degraded", or "unhealthy"
        """
        statuses = [r.status for r in results.values()]

        if "unhealthy" in statuses:
            return "unhealthy"
        elif "degraded" in statuses:
            return "degraded"
        else:
            return "healthy"
