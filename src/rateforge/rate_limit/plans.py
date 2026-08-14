from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimit:
    limit: int
    window: int


class PlanRegistry:
    def __init__(self, plans: dict[str, PlanLimit]):
        self.plans = plans

    def get(self, plan: str) -> PlanLimit:
        try:
            return self.plans[plan]
        except KeyError:
            raise ValueError(f"Unknown plan: {plan}")