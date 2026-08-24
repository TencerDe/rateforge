from dataclasses import dataclass
from .duration import parse_rate


@dataclass(frozen=True)
class RateLimitPolicy:
    limit: int
    window: int
    identity: str = "ip"

    def __post_init__(self):
        if self.limit <= 0:
            raise ValueError("limit must be greater than 0")

        if self.window <= 0:
            raise ValueError("window must be greater than 0")


def create_policy(
    rate: str,
    *,
    identity: str = "ip",
) -> RateLimitPolicy:
    limit, window = parse_rate(rate)

    return RateLimitPolicy(
        limit=limit,
        window=window,
        identity=identity,
    )