class RateLimitError(Exception):
    '''Base exception for RateForge'''

class RedisUnavailableError(RateLimitError):
    """Raised when Redis cannot be reached"""


