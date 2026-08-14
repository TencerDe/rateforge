from dataclasses import dataclass
from enum import Enum

class IdentityType(str, Enum):
    IP = "ip"
    USER = "user"
    API_KEY = "api_key"
    PLAN = "plan"

@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_at: int


@dataclass(frozen=True)
class RateLimitContext:
    endpoint: str
    ip: str | None = None
    user_id: str | None = None
    api_key: str | None = None
    plan: str | None = None