import pytest

from rateforge.rate_limit.plans import (
    PlanLimit,
    PlanRegistry,
)


def test_plan_lookup():
    registry = PlanRegistry(
        {
            "free": PlanLimit(10, 60),
            "pro": PlanLimit(100, 60),
        }
    )

    plan = registry.get("pro")

    assert plan.limit == 100
    assert plan.window == 60


def test_unknown_plan():
    registry = PlanRegistry(
        {
            "free": PlanLimit(10, 60),
        }
    )

    with pytest.raises(ValueError):
        registry.get("enterprise")