from dataclasses import dataclass


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