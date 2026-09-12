class RateForgeException(Exception):
    """Base exception for all RateForge errors."""


class RateLimitError(RateForgeException):
    """
    Deprecated: Use RateForgeException instead.
    Kept for backward compatibility.
    """


class RedisConnectionError(RateForgeException):
    """
    Raised when Redis connection or timeout errors occur.

    This exception triggers fail-open or fail-closed behavior
    based on the RateLimiter configuration.

    Examples:
        - Redis server is down
        - Network connectivity issues
        - Redis timeout
        - Redis busy loading dataset
    """


class RateForgeInternalError(RateForgeException):
    """
    Base class for programming errors, bugs, or misconfigurations.

    These exceptions are NEVER suppressed — they always raise normally
    to ensure bugs are caught and fixed rather than hidden.
    """


class ScriptExecutionError(RateForgeInternalError):
    """
    Raised when Lua script execution fails due to a code error.

    This indicates a bug in the script logic or invalid arguments,
    not a Redis infrastructure issue.
    """


class ConfigurationError(RateForgeInternalError):
    """
    Raised when RateForge configuration is invalid.

    Examples:
        - Invalid Redis URL
        - Missing required configuration
        - Invalid rate limit values
    """


class RedisUnavailableError(RedisConnectionError):
    """
    Raised when Redis cannot be reached.

    Deprecated: Use RedisConnectionError for new code.
    This class is kept for backward compatibility.
    """


class RateLimitExceeded(RateForgeException):
    """
    Raised when a request exceeds the rate limit.

    This exception is typically used by framework integrations
    to return a 429 response to the client.
    """

    def __init__(self, result, message: str = "Rate limit exceeded"):
        super().__init__(message)
        self.result = result
        self.retry_after = result.retry_after
