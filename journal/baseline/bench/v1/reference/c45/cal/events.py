"""One-off events and the calendar that holds them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Event:
    title: str
    start: datetime
    end: datetime
    attendees: frozenset = field(default=frozenset())

    def __post_init__(self):
        object.__setattr__(self, 'attendees', frozenset(self.attendees))
        if self.end <= self.start:
            raise ValueError(f'event {self.title!r} ends before it starts')

    @property
    def interval(self) -> tuple[datetime, datetime]:
        return (self.start, self.end)


def _sort_key(event: Event):
    return (event.start, event.end, event.title)


class Calendar:
    def __init__(self):
        self._events: list[Event] = []
        self._series: list = []

    def add(self, item) -> None:
        from .recurrence import Recurring
        if isinstance(item, Event):
            self._events.append(item)
        elif isinstance(item, Recurring):
            self._series.append(item)
        else:
            raise TypeError(f'cannot add {type(item).__name__} to a calendar')

    def events_between(self, start: datetime, end: datetime) -> list[Event]:
        found = [e for e in self._events if e.start < end and start < e.end]
        for series in self._series:
            found.extend(series.occurrences(start, end))
        return sorted(found, key=_sort_key)

    def events_for(self, person: str, start: datetime, end: datetime) -> list[Event]:
        return [e for e in self.events_between(start, end) if person in e.attendees]
