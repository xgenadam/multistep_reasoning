"""Weekly recurring series with skipped dates."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .events import Event


class Recurring:
    def __init__(self, title, start: datetime, end: datetime, attendees=(), *,
                 weekdays=None, interval: int = 1, until: date | None = None,
                 count: int | None = None, exceptions=(), moves=None):
        if end <= start:
            raise ValueError('series ends before it starts')
        days = sorted(set([start.weekday()] if weekdays is None else weekdays))
        if not days or any(not isinstance(d, int) or d < 0 or d > 6 for d in days):
            raise ValueError(f'bad weekdays: {weekdays!r}')
        if interval < 1:
            raise ValueError('interval must be at least 1')
        if count is not None and count < 1:
            raise ValueError('count must be at least 1')
        self.title = title
        self.start = start
        self.duration = end - start
        self.attendees = frozenset(attendees)
        self.weekdays = tuple(days)
        self.interval = interval
        self.until = until
        self.count = count
        self.exceptions = frozenset(exceptions)
        self.moves = dict(moves or {})
        for day, (m_start, m_end) in self.moves.items():
            if m_end <= m_start:
                raise ValueError(f'move for {day} ends before it starts')
            if day in self.exceptions:
                raise ValueError(f'{day} is both skipped and moved')

    def _candidates(self):
        """Every candidate start in order (exceptions not yet removed)."""
        monday = (self.start - timedelta(days=self.start.weekday())).date()
        tod = self.start.time()
        produced = 0
        week = 0
        while True:
            week_monday = monday + timedelta(weeks=week)
            for wd in self.weekdays:
                day = week_monday + timedelta(days=wd)
                when = datetime.combine(day, tod)
                if when < self.start:
                    continue
                if self.until is not None and day > self.until:
                    return
                if self.count is not None and produced >= self.count:
                    return
                produced += 1
                yield when
            week += self.interval

    def occurrences(self, window_start: datetime, window_end: datetime) -> list[Event]:
        # A candidate after the window can still be moved into it, so keep
        # scanning until past both the window and the last moved date.
        last_move = max(self.moves, default=None)
        out = []
        for when in self._candidates():
            day = when.date()
            if when >= window_end and (last_move is None or day > last_move):
                break
            if day in self.exceptions:
                continue
            if day in self.moves:
                start, end = self.moves[day]
            else:
                start, end = when, when + self.duration
            if start < window_end and end > window_start:
                out.append(Event(self.title, start, end, self.attendees))
        out.sort(key=lambda e: (e.start, e.end))
        return out
