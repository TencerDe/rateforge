"""
Structured logging configuration for RateForge.

Configure logging format (JSON for production, console for development).
"""

import logging
import sys

import structlog


def setup_logging(
    log_level: str = "INFO",
    log_format: str | None = None,
) -> None:
    """
    Configure structured logging for RateForge.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_format: Output format ("json", "console", or None for auto-detect)
                   If None, auto-detects based on environment
    
    Auto-detection:
        - JSON: If RATEFORGE_LOG_FORMAT=json or running in Kubernetes/Docker
        - Console: Otherwise (development)
    
    Example:
        >>> from rateforge import setup_logging
        >>> setup_logging(log_level="DEBUG", log_format="console")
    """
    import os
    
    # Auto-detect format if not specified
    if log_format is None:
        log_format = os.getenv("RATEFORGE_LOG_FORMAT", "auto")
    
    if log_format == "auto":
        # Auto-detect based on environment
        if os.getenv("KUBERNETES_SERVICE_HOST") or os.getenv("CONTAINERIZED"):
            log_format = "json"
        else:
            log_format = "console"
    
    # Select processors based on format
    if log_format == "json":
        # Production: JSON format for log aggregation (Datadog, Splunk, etc.)
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Console format with colors
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, log_level.upper()))
    
    # Log configuration
    logger = structlog.get_logger()
    logger.info(
        "logging_configured",
        level=log_level,
        format=log_format,
    )


__all__ = ["setup_logging"]
