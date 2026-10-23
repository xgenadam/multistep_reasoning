"""Business-day arithmetic with configurable weekends and holidays."""
from datetime import date, timedelta

_ONE = timedelta(days=1)


def _weekend(weekend) -> frozenset[int]:
    days = frozenset(weekend)
    for day in days:
        if isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6:
            raise ValueError(f'invalid weekday: {day!r}')
    if len(days) == 7:
        raise ValueError('every weekday is a weekend day')
    return days


def is_business_day(d: date, *, holidays=(), weekend=(5, 6)) -> bool:
    return d.weekday() not in _weekend(weekend) and d not in set(holidays)


def _count_from(start: date, days: int, weekend: frozenset[int]) -> int:
    """Working (non-weekend) days among the `days` dates starting at `start`."""
    full_weeks, rest = divmod(days, 7)
    count = full_weeks * (7 - len(weekend))
    first = start.weekday()
    count += sum(1 for k in range(rest) if (first + k) % 7 not in weekend)
    return count


def business_days_between(start: date, end: date, *, include_start=True, include_end=False,
                          holidays=(), weekend=(5, 6)) -> int:
    weekend = _weekend(weekend)
    holidays = set(holidays)
    if start > end:
        raise ValueError('start is after end')
    if start == end:
        return int(include_start and include_end and start.weekday() not in weekend
                   and start not in holidays)
    lo = start if include_start else start + _ONE
    hi = end if include_end else end - _ONE      # inclusive upper bound
    if lo > hi:
        return 0
    count = _count_from(lo, (hi - lo).days + 1, weekend)
    count -= sum(1 for h in holidays if lo <= h <= hi and h.weekday() not in weekend)
    return count


def add_business_days(d: date, n: int, *, holidays=(), weekend=(5, 6)) -> date:
    weekend = _weekend(weekend)
    holidays = set(holidays)

    def ok(x: date) -> bool:
        return x.weekday() not in weekend and x not in holidays

    if n == 0:
        while not ok(d):
            d += _ONE
        return d
    step = _ONE if n > 0 else -_ONE
    remaining = abs(n)
    while remaining:
        d += step
        if ok(d):
            remaining -= 1
    return d
