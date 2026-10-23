import random
from datetime import date, timedelta

import pytest

from bizdays import add_business_days, business_days_between, is_business_day

MON = date(2026, 3, 2)   # a Monday
D = timedelta(days=1)


def brute_between(start, end, include_start, include_end, holidays, weekend):
    n, d = 0, start
    while d <= end:
        if (d != start or include_start) and (d != end or include_end):
            if d.weekday() not in weekend and d not in holidays:
                n += 1
        d += D
    return n


def test_is_business_day_defaults():
    assert [is_business_day(MON + k * D) for k in range(7)] == [True] * 5 + [False] * 2


def test_is_business_day_holidays_and_weekend():
    assert not is_business_day(MON, holidays={MON})
    assert is_business_day(MON + 5 * D, weekend=[4])        # Saturday, Friday weekend
    assert not is_business_day(MON + 4 * D, weekend=[4])
    assert is_business_day(MON + 6 * D, weekend=())


def test_between_monday_to_monday():
    assert business_days_between(MON, MON + 7 * D) == 5


def test_between_flags():
    fri = MON + 4 * D
    assert business_days_between(MON, fri) == 4
    assert business_days_between(MON, fri, include_end=True) == 5
    assert business_days_between(MON, fri, include_start=False) == 3
    assert business_days_between(MON, fri, include_start=False, include_end=True) == 4


def test_between_same_day():
    assert business_days_between(MON, MON) == 0
    assert business_days_between(MON, MON, include_end=True) == 1
    assert business_days_between(MON, MON, include_start=False, include_end=True) == 0
    sat = MON + 5 * D
    assert business_days_between(sat, sat, include_end=True) == 0


def test_between_adjacent_days_exclusive():
    assert business_days_between(MON, MON + D, include_start=False) == 0


def test_between_start_after_end_raises():
    with pytest.raises(ValueError):
        business_days_between(MON + D, MON)


def test_between_holidays():
    holidays = [MON + 2 * D, MON + 5 * D, date(2030, 1, 1)]  # a Wednesday, a Saturday, far away
    assert business_days_between(MON, MON + 7 * D, holidays=holidays) == 4


def test_between_duplicate_holidays_count_once():
    holidays = [MON + D, MON + D]
    assert business_days_between(MON, MON + 7 * D, holidays=holidays) == 4


def test_between_custom_weekend():
    # Friday-Saturday weekend: Sunday to Thursday work.
    assert business_days_between(MON, MON + 7 * D, weekend=(4, 5)) == 5
    assert business_days_between(MON, MON + 14 * D, weekend=()) == 14
    assert business_days_between(MON, MON + 14 * D, weekend=[6]) == 12


def test_long_span():
    start, end = date(1900, 1, 1), date(2199, 12, 31)
    holidays = {date(y, 12, 25) for y in range(1900, 2200)}
    xmas_working = sum(1 for h in holidays if h.weekday() < 5)
    got = business_days_between(start, end, include_end=True, holidays=holidays)
    assert got == brute_between(start, end, True, True, holidays, {5, 6})
    assert got == business_days_between(start, end, include_end=True) - xmas_working


def test_between_matches_brute_force():
    rng = random.Random(12)
    for _ in range(300):
        start = date(2026, 1, 1) + rng.randrange(0, 400) * D
        end = start + rng.randrange(0, 40) * D
        weekend = set(rng.sample(range(7), rng.randrange(0, 4)))
        holidays = {start + rng.randrange(-5, 45) * D for _ in range(rng.randrange(0, 6))}
        flags = rng.random() < 0.5, rng.random() < 0.5
        assert business_days_between(start, end, include_start=flags[0], include_end=flags[1],
                                     holidays=holidays, weekend=weekend) == \
            brute_between(start, end, *flags, holidays, weekend)


def test_add_forward_skips_weekend():
    fri = MON + 4 * D
    assert add_business_days(fri, 1) == MON + 7 * D
    assert add_business_days(MON, 5) == MON + 7 * D
    assert add_business_days(MON + 5 * D, 1) == MON + 7 * D   # from Saturday


def test_add_backward():
    assert add_business_days(MON, -1) == MON - 3 * D
    assert add_business_days(MON + 6 * D, -1) == MON + 4 * D  # Sunday back to Friday
    assert add_business_days(MON, -10) == MON - 14 * D


def test_add_zero_rolls_forward():
    assert add_business_days(MON, 0) == MON
    assert add_business_days(MON + 5 * D, 0) == MON + 7 * D
    assert add_business_days(MON, 0, holidays={MON, MON + D}) == MON + 2 * D


def test_add_with_holidays_and_weekend():
    holidays = {MON + D, MON + 2 * D}
    assert add_business_days(MON, 1, holidays=holidays) == MON + 3 * D
    assert add_business_days(MON + 3 * D, -1, holidays=holidays) == MON
    assert add_business_days(MON + 4 * D, 1, weekend=(6,)) == MON + 5 * D


def test_add_matches_between():
    rng = random.Random(13)
    for _ in range(200):
        d = date(2026, 1, 1) + rng.randrange(0, 300) * D
        n = rng.randrange(1, 60)
        holidays = {d + rng.randrange(0, 90) * D for _ in range(5)}
        later = add_business_days(d, n, holidays=holidays)
        assert is_business_day(later, holidays=holidays)
        assert business_days_between(d, later, include_start=False, include_end=True,
                                     holidays=holidays) == n
        assert add_business_days(later, -n, holidays=holidays) <= d


def test_invalid_weekend_raises():
    for weekend in [range(7), (7,), (-1,), (5, 6, 0, 1, 2, 3, 4)]:
        for call in (lambda w: is_business_day(MON, weekend=w),
                     lambda w: business_days_between(MON, MON + D, weekend=w),
                     lambda w: add_business_days(MON, 1, weekend=w)):
            with pytest.raises(ValueError):
                call(weekend)
