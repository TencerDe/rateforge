"""
Unit tests for health module.

Tests:
1. Health check result serialization
2. Redis health check (mocked)
3. Database health check (placeholder)
4. Filesystem health check
5. Memory health check (with/without psutil)
6. Config health check
7. Overall status calculation
8. All checks integration
"""

import os
from unittest.mock import MagicMock, patch

from rateforge.health import HealthChecker
from rateforge.health.checks import HealthCheckResult


class TestHealthCheckResult:
    """Test HealthCheckResult dataclass."""

    def test_create_healthy_result(self):
        """Create healthy result with latency."""
        result = HealthCheckResult(
            name="test",
            status="healthy",
            latency_ms=1.5,
        )

        assert result.name == "test"
        assert result.status == "healthy"
        assert result.latency_ms == 1.5
        assert result.error is None
        assert isinstance(result.timestamp, float)

    def test_create_unhealthy_result(self):
        """Create unhealthy result with error."""
        result = HealthCheckResult(
            name="test",
            status="unhealthy",
            error="Connection failed",
        )

        assert result.status == "unhealthy"
        assert result.error == "Connection failed"
        assert result.latency_ms is None

    def test_to_dict_healthy(self):
        """Convert healthy result to dict."""
        result = HealthCheckResult(
            name="redis",
            status="healthy",
            latency_ms=1.4,
            details={"message": "Success"},
        )

        data = result.to_dict()

        assert data["status"] == "healthy"
        assert data["latency_ms"] == 1.4
        assert data["details"]["message"] == "Success"
        assert "timestamp" in data
        assert "error" not in data

    def test_to_dict_unhealthy(self):
        """Convert unhealthy result to dict."""
        result = HealthCheckResult(
            name="redis",
            status="unhealthy",
            error="Connection refused",
        )

        data = result.to_dict()

        assert data["status"] == "unhealthy"
        assert data["error"] == "Connection refused"
        assert "latency_ms" not in data
        assert "details" not in data


class TestRedisCheck:
    """Test Redis health check."""

    @patch("rateforge.get_default_limiter")
    def test_redis_healthy(self, mock_get_limiter):
        """Redis check should return healthy when connected."""
        mock_limiter = MagicMock()
        mock_limiter.backend.ping.return_value = True
        mock_get_limiter.return_value = mock_limiter

        checker = HealthChecker()
        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == "healthy"
        assert result.latency_ms is not None
        assert result.latency_ms >= 0
        assert result.error is None

    @patch("rateforge.get_default_limiter")
    def test_redis_unhealthy(self, mock_get_limiter):
        """Redis check should return unhealthy when disconnected."""
        mock_limiter = MagicMock()
        mock_limiter.backend.ping.return_value = False
        mock_get_limiter.return_value = mock_limiter

        checker = HealthChecker()
        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == "unhealthy"
        assert result.error is not None

    @patch("rateforge.get_default_limiter")
    def test_redis_exception(self, mock_get_limiter):
        """Redis check should handle exceptions."""
        mock_limiter = MagicMock()
        mock_limiter.backend.ping.side_effect = Exception("Connection failed")
        mock_get_limiter.return_value = mock_limiter

        checker = HealthChecker()
        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == "unhealthy"
        assert "Connection failed" in result.error


class TestDatabaseCheck:
    """Test database health check (placeholder)."""

    def test_database_placeholder(self):
        """Database check should return healthy placeholder."""
        checker = HealthChecker()
        result = checker.check_database()

        assert result.name == "database"
        assert result.status == "healthy"
        assert "note" in result.details
        assert result.latency_ms is None
        assert result.error is None


class TestFilesystemCheck:
    """Test filesystem health check."""

    def test_filesystem_healthy(self):
        """Filesystem check should return healthy."""
        checker = HealthChecker()
        result = checker.check_filesystem()

        assert result.name == "filesystem"
        assert result.status == "healthy"
        assert result.error is None

    @patch("tempfile.NamedTemporaryFile")
    def test_filesystem_unhealthy(self, mock_tempfile):
        """Filesystem check should handle write failures."""
        mock_tempfile.side_effect = PermissionError("No write access")

        checker = HealthChecker()
        result = checker.check_filesystem()

        assert result.name == "filesystem"
        assert result.status == "unhealthy"
        assert "No write access" in result.error


class TestMemoryCheck:
    """Test memory health check."""

    @patch("psutil.virtual_memory")
    def test_memory_healthy(self, mock_virtual_memory):
        """Memory check should return healthy when usage < 70%."""
        mock_memory = MagicMock()
        mock_memory.percent = 50
        mock_memory.available = 8 * 1024 * 1024 * 1024  # 8GB
        mock_memory.total = 16 * 1024 * 1024 * 1024  # 16GB
        mock_virtual_memory.return_value = mock_memory

        checker = HealthChecker()
        result = checker.check_memory()

        assert result.name == "memory"
        assert result.status == "healthy"
        assert result.details["usage_percent"] == 50

    @patch("psutil.virtual_memory")
    def test_memory_degraded(self, mock_virtual_memory):
        """Memory check should return degraded when 70% <= usage < 90%."""
        mock_memory = MagicMock()
        mock_memory.percent = 85
        mock_memory.available = 2 * 1024 * 1024 * 1024  # 2GB
        mock_memory.total = 16 * 1024 * 1024 * 1024  # 16GB
        mock_virtual_memory.return_value = mock_memory

        checker = HealthChecker()
        result = checker.check_memory()

        assert result.name == "memory"
        assert result.status == "degraded"
        assert result.details["usage_percent"] == 85

    @patch("psutil.virtual_memory")
    def test_memory_unhealthy(self, mock_virtual_memory):
        """Memory check should return unhealthy when usage >= 90%."""
        mock_memory = MagicMock()
        mock_memory.percent = 95
        mock_memory.available = 1 * 1024 * 1024 * 1024  # 1GB
        mock_memory.total = 16 * 1024 * 1024 * 1024  # 16GB
        mock_virtual_memory.return_value = mock_memory

        checker = HealthChecker()
        result = checker.check_memory()

        assert result.name == "memory"
        assert result.status == "unhealthy"
        assert result.details["usage_percent"] == 95

    def test_memory_no_psutil(self):
        """Memory check should return degraded when psutil not installed."""
        # Temporarily hide psutil
        import sys

        psutil_backup = sys.modules.get("psutil")
        sys.modules["psutil"] = None

        try:
            # Reload the module to simulate missing psutil
            import importlib

            from rateforge.health import checks

            importlib.reload(checks)

            checker = checks.HealthChecker()
            result = checker.check_memory()

            assert result.name == "memory"
            assert result.status == "degraded"
            assert "psutil not installed" in result.details.get("note", "")

        finally:
            # Restore psutil
            if psutil_backup:
                sys.modules["psutil"] = psutil_backup

            # Reload back to normal
            importlib.reload(checks)


class TestConfigCheck:
    """Test configuration health check."""

    def test_config_healthy(self):
        """Config check should return healthy when properly configured."""
        with patch.dict(
            os.environ,
            {
                "RATEFORGE_REDIS_URL": "redis://localhost:6379/0",
                "RATEFORGE_FAIL_OPEN": "true",
            },
            clear=False,
        ):
            checker = HealthChecker()
            result = checker.check_config()

            assert result.name == "config"
            assert result.status == "healthy"
            assert result.details.get("redis_url_configured") is True
            assert result.details.get("fail_open") is True

    def test_config_degraded_no_url(self):
        """Config check should return degraded when URL not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove RATEFORGE_REDIS_URL if it exists
            os.environ.pop("RATEFORGE_REDIS_URL", None)

            checker = HealthChecker()
            result = checker.check_config()

            assert result.name == "config"
            assert result.status == "degraded"
            assert "not set" in result.error

    def test_config_unhealthy_invalid_url(self):
        """Config check should return unhealthy when URL format invalid."""
        with patch.dict(
            os.environ,
            {
                "RATEFORGE_REDIS_URL": "invalid-url-format",
            },
            clear=False,
        ):
            checker = HealthChecker()
            result = checker.check_config()

            assert result.name == "config"
            assert result.status == "unhealthy"
            assert "Invalid Redis URL" in result.error

    def test_config_secure_redis(self):
        """Config check should accept rediss:// (secure Redis) URLs."""
        with patch.dict(
            os.environ,
            {
                "RATEFORGE_REDIS_URL": "rediss://secure-redis:6379/0",
            },
            clear=False,
        ):
            checker = HealthChecker()
            result = checker.check_config()

            assert result.name == "config"
            assert result.status == "healthy"


class TestOverallStatus:
    """Test overall status calculation."""

    def test_all_healthy(self):
        """Overall status should be healthy when all checks pass."""
        checker = HealthChecker()
        results = {
            "redis": HealthCheckResult(name="redis", status="healthy"),
            "database": HealthCheckResult(name="database", status="healthy"),
            "filesystem": HealthCheckResult(name="filesystem", status="healthy"),
            "memory": HealthCheckResult(name="memory", status="healthy"),
            "config": HealthCheckResult(name="config", status="healthy"),
        }

        overall = checker.get_overall_status(results)
        assert overall == "healthy"

    def test_one_degraded(self):
        """Overall status should be degraded when any check is degraded."""
        checker = HealthChecker()
        results = {
            "redis": HealthCheckResult(name="redis", status="healthy"),
            "database": HealthCheckResult(name="database", status="healthy"),
            "filesystem": HealthCheckResult(name="filesystem", status="degraded"),
            "memory": HealthCheckResult(name="memory", status="healthy"),
            "config": HealthCheckResult(name="config", status="healthy"),
        }

        overall = checker.get_overall_status(results)
        assert overall == "degraded"

    def test_one_unhealthy(self):
        """Overall status should be unhealthy when any check is unhealthy."""
        checker = HealthChecker()
        results = {
            "redis": HealthCheckResult(name="redis", status="unhealthy"),
            "database": HealthCheckResult(name="database", status="healthy"),
            "filesystem": HealthCheckResult(name="filesystem", status="healthy"),
            "memory": HealthCheckResult(name="memory", status="healthy"),
            "config": HealthCheckResult(name="config", status="healthy"),
        }

        overall = checker.get_overall_status(results)
        assert overall == "unhealthy"


class TestRunAllChecks:
    """Test running all health checks."""

    @patch("rateforge.get_default_limiter")
    @patch("psutil.virtual_memory")
    def test_run_all_checks(self, mock_virtual_memory, mock_get_limiter):
        """Run all checks should return results for all 5 checks."""
        # Mock Redis
        mock_limiter = MagicMock()
        mock_limiter.backend.ping.return_value = True
        mock_get_limiter.return_value = mock_limiter

        # Mock psutil
        mock_memory = MagicMock()
        mock_memory.percent = 50
        mock_virtual_memory.return_value = mock_memory

        checker = HealthChecker()
        results = checker.run_all_checks()

        assert len(results) == 5
        assert "redis" in results
        assert "database" in results
        assert "filesystem" in results
        assert "memory" in results
        assert "config" in results

        # Verify all results are HealthCheckResult instances
        for name, result in results.items():
            # Check type by name since imports can vary
            assert type(result).__name__ == "HealthCheckResult"
            assert result.name == name
