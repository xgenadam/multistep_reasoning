from datetime import date, datetime, time, timedelta

import pytest

from cal import (Calendar, Event, Recurring, busy_intervals, find_conflicts, first_free,
                 free_slots, merge, overlaps)

# 2026-03-02 is a Monday.


def dt(day, hh, mm=0):
    return datetime(2026, 3, day, hh, mm)


def ev(title, day, h1, h2, *people, m1=0, m2=0):
    return Event(title, dt(day, h1, m1), dt(day, h2, m2), people)


# ---------------------------------------------------------------- events

def test_event_stores_attendees_as_frozenset():
    e = Event('standup', dt(2, 9), dt(2, 10), ['ann', 'bo', 'ann'])
    assert e.attendees == frozenset({'ann', 'bo'})
    assert isinstance(e.attendees, frozenset)
    assert e == Event('standup', dt(2, 9), dt(2, 10), {'bo', 'ann'})


def test_event_end_not_after_start_raises():
    with pytest.raises(ValueError):
        Event('x', dt(2, 9), dt(2, 9))
    with pytest.raises(ValueError):
        Event('x', dt(2, 9), dt(2, 8))


def test_calendar_add_rejects_other_types():
    with pytest.raises(TypeError):
        Calendar().add(('x', dt(2, 9), dt(2, 10)))


def test_events_between_overlap_and_sort_order():
    cal = Calendar()
    cal.add(ev('b', 2, 10, 11, 'ann'))
    cal.add(ev('a', 2, 10, 11, 'ann'))
    cal.add(ev('early', 2, 8, 9, 'ann'))        # ends exactly at window start
    cal.add(ev('long', 2, 9, 12, 'bo', m1=30))
    cal.add(ev('late', 2, 12, 13, 'bo'))        # starts exactly at window end
    got = cal.events_between(dt(2, 9), dt(2, 12))
    assert [e.title for e in got] == ['long', 'a', 'b']


def test_events_for_filters_by_person():
    cal = Calendar()
    cal.add(ev('a', 2, 9, 10, 'ann', 'bo'))
    cal.add(ev('b', 2, 11, 12, 'bo'))
    assert [e.title for e in cal.events_for('ann', dt(2, 0), dt(3, 0))] == ['a']
    assert [e.title for e in cal.events_for('bo', dt(2, 0), dt(3, 0))] == ['a', 'b']


# ---------------------------------------------------------------- recurrence

def starts(events):
    return [e.start for e in events]


def test_default_weekday_is_starts_weekday():
    r = Recurring('1:1', dt(4, 14), dt(4, 15), ['ann'])   # Wednesday
    got = r.occurrences(dt(1, 0), datetime(2026, 3, 26))
    assert starts(got) == [dt(4, 14), dt(11, 14), dt(18, 14), dt(25, 14)]
    assert all(e.title == '1:1' and e.attendees == {'ann'} for e in got)
    assert all(e.end - e.start == timedelta(hours=1) for e in got)


def test_weekdays_before_start_in_first_week_are_skipped():
    # Starts Wednesday; Monday of week 0 is earlier than start and is not an occurrence.
    r = Recurring('gym', dt(4, 7), dt(4, 8), weekdays=[0, 2, 4])
    got = r.occurrences(dt(1, 0), dt(10, 0))
    assert starts(got) == [dt(4, 7), dt(6, 7), dt(9, 7)]


def test_start_not_on_listed_weekday_is_not_an_occurrence():
    r = Recurring('x', dt(3, 9), dt(3, 10), weekdays=[0, 4])   # Tuesday start
    assert starts(r.occurrences(dt(1, 0), dt(10, 0))) == [dt(6, 9), dt(9, 9)]


def test_interval_counts_weeks_from_starts_week():
    r = Recurring('x', dt(5, 9), dt(5, 10), weekdays=[0, 3], interval=2)   # Thursday
    got = r.occurrences(dt(1, 0), dt(31, 0))
    # week 0 (Mar 2-8): Thu 5 only; week 2 (Mar 16-22): Mon 16, Thu 19; week 4: Mon 30.
    assert starts(got) == [dt(5, 9), dt(16, 9), dt(19, 9), dt(30, 9)]


def test_until_is_inclusive():
    r = Recurring('x', dt(2, 9), dt(2, 10), until=date(2026, 3, 16))
    got = r.occurrences(dt(1, 0), datetime(2026, 4, 30))
    assert starts(got) == [dt(2, 9), dt(9, 9), dt(16, 9)]


def test_exceptions_skip_but_use_up_count():
    r = Recurring('x', dt(2, 9), dt(2, 10), count=4, exceptions=[date(2026, 3, 9)])
    got = r.occurrences(dt(1, 0), datetime(2026, 5, 1))
    assert starts(got) == [dt(2, 9), dt(16, 9), dt(23, 9)]


def test_count_and_until_whichever_first():
    r = Recurring('x', dt(2, 9), dt(2, 10), weekdays=[0, 1, 2, 3, 4], count=3,
                  until=date(2026, 3, 30))
    assert starts(r.occurrences(dt(1, 0), dt(31, 0))) == [dt(2, 9), dt(3, 9), dt(4, 9)]


def test_occurrences_overlapping_window_edges():
    r = Recurring('x', dt(2, 9), dt(2, 11), weekdays=[0, 1, 2])
    got = r.occurrences(dt(3, 10), dt(4, 9))   # inside Tue's, ends when Wed's begins
    assert starts(got) == [dt(3, 9)]


def test_infinite_series_far_window_terminates():
    r = Recurring('x', datetime(2020, 1, 6, 9), datetime(2020, 1, 6, 10))
    got = r.occurrences(datetime(2030, 1, 1), datetime(2030, 1, 15))
    assert starts(got) == [datetime(2030, 1, 7, 9), datetime(2030, 1, 14, 9)]


def test_move_replaces_one_occurrence():
    r = Recurring('x', dt(2, 9), dt(2, 10),
                  moves={date(2026, 3, 9): (dt(10, 15), dt(10, 16, 30))})
    got = r.occurrences(dt(1, 0), dt(17, 0))
    assert [(e.start, e.end) for e in got] == [(dt(2, 9), dt(2, 10)),
                                                (dt(10, 15), dt(10, 16, 30)),
                                                (dt(16, 9), dt(16, 10))]


def test_move_out_of_and_into_window():
    r = Recurring('x', dt(2, 9), dt(2, 10),
                  moves={date(2026, 3, 16): (dt(3, 13), dt(3, 14)),
                         date(2026, 3, 9): (dt(20, 9), dt(20, 10))})
    got = r.occurrences(dt(2, 0), dt(9, 0))
    assert starts(got) == [dt(2, 9), dt(3, 13)]
    later = r.occurrences(dt(9, 0), dt(21, 0))
    assert starts(later) == [dt(20, 9)]


def test_move_uses_up_count():
    r = Recurring('x', dt(2, 9), dt(2, 10), count=2,
                  moves={date(2026, 3, 2): (dt(4, 9), dt(4, 10))})
    assert starts(r.occurrences(dt(1, 0), dt(31, 0))) == [dt(4, 9), dt(9, 9)]


@pytest.mark.parametrize('kwargs', [
    {'weekdays': []}, {'weekdays': [7]}, {'interval': 0},
    {'count': 0}, {'moves': {date(2026, 3, 9): (dt(9, 10), dt(9, 9))}},
    {'exceptions': [date(2026, 3, 9)], 'moves': {date(2026, 3, 9): (dt(9, 10), dt(9, 11))}},
])
def test_recurring_validation(kwargs):
    with pytest.raises(ValueError):
        Recurring('x', dt(2, 9), dt(2, 10), **kwargs)


def test_calendar_expands_series():
    cal = Calendar()
    cal.add(Recurring('standup', dt(2, 9), dt(2, 9, 15), ['ann'], weekdays=[0, 1, 2, 3, 4]))
    cal.add(ev('review', 3, 9, 10, 'bo'))
    got = cal.events_between(dt(3, 0), dt(4, 0))
    assert [(e.title, e.start) for e in got] == [('standup', dt(3, 9)), ('review', dt(3, 9))]


# ---------------------------------------------------------------- intervals

def test_overlaps_half_open_and_merge():
    assert overlaps((dt(2, 9), dt(2, 10)), (dt(2, 9, 30), dt(2, 11)))
    assert not overlaps((dt(2, 9), dt(2, 10)), (dt(2, 10), dt(2, 11)))
    assert overlaps((dt(2, 9), dt(2, 12)), (dt(2, 10), dt(2, 11)))
    got = merge([(dt(2, 13), dt(2, 14)), (dt(2, 9), dt(2, 10)), (dt(2, 10), dt(2, 11)),
                 (dt(2, 9, 30), dt(2, 10, 30)), (dt(2, 15), dt(2, 16))])
    assert got == [(dt(2, 9), dt(2, 11)), (dt(2, 13), dt(2, 14)), (dt(2, 15), dt(2, 16))]
    assert merge([]) == []


def test_busy_intervals_clip_and_merge():
    cal = Calendar()
    cal.add(ev('a', 2, 8, 10, 'ann'))
    cal.add(ev('b', 2, 10, 11, 'bo'))
    cal.add(ev('c', 2, 15, 18, 'ann'))
    cal.add(ev('d', 2, 12, 13, 'cy'))
    assert busy_intervals(cal, ['ann', 'bo'], dt(2, 9), dt(2, 17)) == [
        (dt(2, 9), dt(2, 11)), (dt(2, 15), dt(2, 17))]


# ---------------------------------------------------------------- conflicts

def test_conflicts_need_overlap_and_shared_attendee():
    cal = Calendar()
    cal.add(ev('a', 2, 9, 10, 'ann', 'bo'))
    cal.add(ev('b', 2, 9, 11, 'bo', m1=30))     # overlaps a, shares bo
    cal.add(ev('c', 2, 10, 11, 'ann'))          # touches a only; overlaps b, nobody shared
    cal.add(ev('d', 2, 9, 10, 'cy'))            # overlaps a, nobody shared
    pairs = find_conflicts(cal, dt(2, 0), dt(3, 0))
    assert [(a.title, b.title) for a, b in pairs] == [('a', 'b')]


def test_conflict_pairs_order():
    cal = Calendar()
    cal.add(ev('z', 2, 9, 12, 'ann'))
    cal.add(ev('y', 2, 11, 12, 'ann'))
    cal.add(ev('x', 2, 10, 11, 'ann', m2=30))
    pairs = find_conflicts(cal, dt(2, 0), dt(3, 0))
    assert [(a.title, b.title) for a, b in pairs] == [('z', 'x'), ('z', 'y'), ('x', 'y')]


def test_conflicts_include_series_occurrences():
    cal = Calendar()
    cal.add(Recurring('standup', dt(2, 9), dt(2, 9, 30), ['ann'], weekdays=[0, 2]))
    cal.add(ev('dentist', 4, 9, 10, 'ann', m1=15))
    pairs = find_conflicts(cal, dt(2, 0), dt(9, 0))
    assert [(a.title, a.start, b.title) for a, b in pairs] == [('standup', dt(4, 9), 'dentist')]


# ---------------------------------------------------------------- free slots

@pytest.fixture
def team():
    cal = Calendar()
    cal.add(ev('a1', 2, 9, 10, 'ann'))
    cal.add(ev('b1', 2, 10, 10, 'bo', m2=30))
    cal.add(ev('a2', 2, 13, 14, 'ann'))
    cal.add(ev('c1', 2, 11, 12, 'cy'))        # cy is not asked about
    cal.add(ev('b2', 3, 8, 9, 'bo', m1=30, m2=30))
    return cal


def test_free_slots_common_gaps(team):
    got = free_slots(team, ['ann', 'bo'], dt(2, 8), dt(2, 18))
    assert got == [(dt(2, 8), dt(2, 9)), (dt(2, 10, 30), dt(2, 13)), (dt(2, 14), dt(2, 18))]


def test_free_slots_min_length(team):
    got = free_slots(team, ['ann', 'bo'], dt(2, 8), dt(2, 18), min_length=timedelta(hours=2))
    assert got == [(dt(2, 10, 30), dt(2, 13)), (dt(2, 14), dt(2, 18))]
    exact = free_slots(team, ['ann', 'bo'], dt(2, 8), dt(2, 18), min_length=timedelta(hours=1))
    assert (dt(2, 8), dt(2, 9)) in exact


def test_free_slots_working_hours_split_days(team):
    got = free_slots(team, ['ann', 'bo'], dt(2, 12), dt(3, 12),
                     day_start=time(9), day_end=time(17))
    assert got == [(dt(2, 12), dt(2, 13)), (dt(2, 14), dt(2, 17)), (dt(3, 9, 30), dt(3, 12))]


def test_free_slots_without_hours_cross_midnight(team):
    got = free_slots(team, ['bo'], dt(2, 18), dt(3, 10))
    assert got == [(dt(2, 18), dt(3, 8, 30)), (dt(3, 9, 30), dt(3, 10))]


def test_free_slots_nobody_busy_whole_window(team):
    assert free_slots(team, ['zed'], dt(2, 9), dt(2, 10)) == [(dt(2, 9), dt(2, 10))]


def test_free_slots_busy_covers_window(team):
    assert free_slots(team, ['ann'], dt(2, 9, 15), dt(2, 9, 45)) == []


@pytest.mark.parametrize('kwargs', [
    {'people': []},
    {'day_end': time(17)},
    {'day_start': time(17), 'day_end': time(9)},
])
def test_free_slots_validation(team, kwargs):
    people = kwargs.pop('people', ['ann'])
    with pytest.raises(ValueError):
        free_slots(team, people, dt(2, 8), dt(2, 18), **kwargs)


def test_first_free_earliest_fit(team):
    assert first_free(team, ['ann', 'bo'], dt(2, 8), dt(2, 18), timedelta(hours=2)) == (
        dt(2, 10, 30), dt(2, 12, 30))
    assert first_free(team, ['ann', 'bo'], dt(2, 8), dt(2, 18), timedelta(hours=1)) == (
        dt(2, 8), dt(2, 9))
    assert first_free(team, ['ann', 'bo'], dt(2, 8), dt(2, 18), timedelta(hours=5)) is None


def test_first_free_respects_hours_and_validation(team):
    got = first_free(team, ['ann', 'bo'], dt(2, 15), dt(3, 17), timedelta(hours=3),
                     day_start=time(9), day_end=time(17))
    assert got == (dt(3, 9, 30), dt(3, 12, 30))
    with pytest.raises(ValueError):
        first_free(team, ['ann'], dt(2, 8), dt(2, 18), timedelta(0))
