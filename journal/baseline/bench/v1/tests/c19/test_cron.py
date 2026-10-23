from datetime import datetime as dt

import pytest

from cron import next_run


def test_every_minute_is_strictly_after():
    assert next_run('* * * * *', dt(2026, 5, 1, 10, 15)) == dt(2026, 5, 1, 10, 16)


def test_seconds_are_dropped():
    assert next_run('* * * * *', dt(2026, 5, 1, 10, 15, 30, 5)) == dt(2026, 5, 1, 10, 16)
    assert next_run('*/15 * * * *', dt(2026, 5, 1, 10, 14, 59)) == dt(2026, 5, 1, 10, 15)


def test_minute_step():
    assert next_run('*/15 * * * *', dt(2026, 5, 1, 10, 15)) == dt(2026, 5, 1, 10, 30)
    assert next_run('*/15 * * * *', dt(2026, 5, 1, 10, 50)) == dt(2026, 5, 1, 11, 0)


def test_fixed_time_rolls_to_next_day():
    assert next_run('30 9 * * *', dt(2026, 5, 1, 9, 30)) == dt(2026, 5, 2, 9, 30)
    assert next_run('30 9 * * *', dt(2026, 5, 1, 9, 29)) == dt(2026, 5, 1, 9, 30)


def test_lists_ranges_and_range_steps():
    expr = '0,30 8-17/3 * * *'  # hours 8, 11, 14, 17
    assert next_run(expr, dt(2026, 5, 1, 8, 30)) == dt(2026, 5, 1, 11, 0)
    assert next_run(expr, dt(2026, 5, 1, 17, 30)) == dt(2026, 5, 2, 8, 0)


def test_year_rollover():
    assert next_run('0 0 1 1 *', dt(2026, 6, 1)) == dt(2027, 1, 1)


def test_day_of_week_only():
    # 2026-05-01 is a Friday; next Monday is 2026-05-04
    assert next_run('0 12 * * 1', dt(2026, 5, 1)) == dt(2026, 5, 4, 12, 0)


@pytest.mark.parametrize('sunday', ['0', '7'])
def test_sunday_is_0_and_7(sunday):
    assert next_run(f'0 0 * * {sunday}', dt(2026, 5, 1)) == dt(2026, 5, 3)


def test_weekday_range():
    # Mon-Fri at 06:00, after Friday 07:00 -> Monday
    assert next_run('0 6 * * 1-5', dt(2026, 5, 1, 7, 0)) == dt(2026, 5, 4, 6, 0)


def test_both_restricted_is_or():
    # the 15th, or any Monday: from Fri 2026-05-01 the first is Mon 05-04
    assert next_run('0 0 15 * 1', dt(2026, 5, 1)) == dt(2026, 5, 4)
    # from Tue 2026-05-12 the 15th (a Friday) comes before Monday the 18th
    assert next_run('0 0 15 * 1', dt(2026, 5, 12)) == dt(2026, 5, 15)


def test_star_step_counts_as_unrestricted():
    # day-of-month '*/2' starts with '*', so the fields are ANDed:
    # odd days that are Mondays. 2026-05-04 is even; Mon 05-11 is odd.
    assert next_run('0 0 */2 * 1', dt(2026, 5, 1)) == dt(2026, 5, 11)


def test_dom_step_starts_at_one():
    assert next_run('0 0 */10 * *', dt(2026, 5, 1)) == dt(2026, 5, 11)
    assert next_run('0 0 */10 * *', dt(2026, 5, 21)) == dt(2026, 5, 31)


def test_day_31_skips_short_months():
    assert next_run('0 0 31 * *', dt(2026, 4, 1)) == dt(2026, 5, 31)
    assert next_run('0 0 31 * *', dt(2026, 5, 31)) == dt(2026, 7, 31)


def test_leap_day():
    assert next_run('0 0 29 2 *', dt(2026, 3, 1)) == dt(2028, 2, 29)


def test_whitespace_between_fields():
    assert next_run('  0   0\t1  1 * ', dt(2026, 6, 1)) == dt(2027, 1, 1)


@pytest.mark.parametrize('exprs', [
    # field count and syntax
    ['* * * *', '* * * * * *', '', '1,,2 * * * *', 'a * * * *', '* * * JAN *', '-1 * * * *',
     '5/2 * * * *'],
    # ranges and steps
    ['60 * * * *', '* 24 * * *', '* * 0 * *', '* * * 13 *', '* * * * 8', '5-1 * * * *',
     '*/0 * * * *'],
])
def test_invalid_expressions(exprs):
    for expr in exprs:
        with pytest.raises(ValueError):
            next_run(expr, dt(2026, 5, 1))


def test_impossible_day_raises():
    with pytest.raises(ValueError):
        next_run('0 0 30 2 *', dt(2026, 5, 1))
    with pytest.raises(ValueError):
        next_run('0 0 31 4,6,9,11 *', dt(2026, 5, 1))


def test_impossible_dom_with_restricted_dow_still_runs():
    # both restricted: Feb 30 never exists, but Sundays in February do
    assert next_run('0 0 30 2 0', dt(2026, 5, 1)) == dt(2027, 2, 7)
