"""Interval helpers shared by conflict detection and free-slot search."""

from __future__ import annotations

from datetime import datetime, time, timedelta


def overlaps(a, b) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def merge(intervals) -> list[tuple[datetime, datetime]]:
    out: list[list] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1][1] = e
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def busy_intervals(calendar, people, start, end) -> list[tuple[datetime, datetime]]:
    people = set(people)
    return merge((max(e.start, start), min(e.end, end))
                 for e in calendar.events_between(start, end) if e.attendees & people)


def find_conflicts(calendar, start, end):
    events = calendar.events_between(start, end)
    pairs = []
    for i, a in enumerate(events):
        for b in events[i + 1:]:
            if overlaps((a.start, a.end), (b.start, b.end)) and a.attendees & b.attendees:
                pairs.append((a, b))
    return pairs


def _working_windows(start, end, day_start, day_end):
    if day_start is None:
        return [(start, end)]
    windows = []
    day = start.date()
    while datetime.combine(day, time()) < end:
        lo = max(start, datetime.combine(day, day_start))
        hi = min(end, datetime.combine(day, day_end))
        if lo < hi:
            windows.append((lo, hi))
        day += timedelta(days=1)
    return windows


def _check(people, day_start, day_end):
    if not people:
        raise ValueError('no people given')
    if (day_start is None) != (day_end is None):
        raise ValueError('give both day_start and day_end, or neither')
    if day_start is not None and day_end <= day_start:
        raise ValueError('day_end must be after day_start')


def free_slots(calendar, people, start, end, *, min_length=timedelta(0),
               day_start=None, day_end=None):
    people = set(people)
    _check(people, day_start, day_end)
    busy = busy_intervals(calendar, people, start, end)
    slots = []
    for lo, hi in _working_windows(start, end, day_start, day_end):
        cursor = lo
        for b_start, b_end in busy:
            if b_end <= cursor:
                continue
            if b_start >= hi:
                break
            if b_start > cursor:
                slots.append((cursor, b_start))
            cursor = max(cursor, b_end)
            if cursor >= hi:
                break
        if cursor < hi:
            slots.append((cursor, hi))
    return [(s, e) for s, e in slots if e > s and e - s >= min_length]


def first_free(calendar, people, start, end, duration, *, day_start=None, day_end=None):
    if duration <= timedelta(0):
        raise ValueError('duration must be positive')
    for s, e in free_slots(calendar, people, start, end, min_length=duration,
                           day_start=day_start, day_end=day_end):
        return (s, s + duration)
    return None
