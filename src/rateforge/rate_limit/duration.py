from __future__ import annotations

import re


_UNITS = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "s": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "m": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "h": 3600,
}


def parse_rate(rate: str) -> tuple[int, int]:
    """
    Parse a rate string such as:

        100/minute
        10/min
        1000/hour
        5/s

    Returns:
        (limit, window_seconds)
    """

    if not isinstance(rate, str):
        raise TypeError("rate must be a string")

    match = re.fullmatch(
        r"\s*(\d+)\s*/\s*([a-zA-Z]+)\s*",
        rate,
    )

    if not match:
        raise ValueError(
            f"Invalid rate format: {rate!r}. "
            "Expected '<number>/<unit>', e.g. '100/minute'."
        )

    limit = int(match.group(1))
    unit = match.group(2).lower()

    if limit <= 0:
        raise ValueError("rate limit must be greater than 0")

    try:
        window = _UNITS[unit]
    except KeyError:
        raise ValueError(
            f"Unsupported rate unit: {unit!r}"
        ) from None

    return limit, window