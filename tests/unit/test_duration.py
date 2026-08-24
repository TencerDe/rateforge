import pytest

from rateforge.rate_limit.duration import parse_rate


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("100/minute", (100, 60)),
        ("10/min", (10, 60)),
        ("1000/hour", (1000, 3600)),
        ("5/second", (5, 1)),
        ("5/s", (5, 1)),
    ],
)
def test_parse_rate(value, expected):
    assert parse_rate(value) == expected


def test_invalid_rate():
    with pytest.raises(ValueError):
        parse_rate("invalid")


def test_invalid_unit():
    with pytest.raises(ValueError):
        parse_rate("100/day")


def test_zero_limit():
    with pytest.raises(ValueError):
        parse_rate("0/minute")