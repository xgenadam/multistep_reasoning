"""Meeting scheduling: events, weekly series, conflicts and common free time."""

from .events import Calendar, Event
from .recurrence import Recurring
from .slots import busy_intervals, find_conflicts, first_free, free_slots, merge, overlaps

__all__ = ['Event', 'Calendar', 'Recurring', 'overlaps', 'merge', 'busy_intervals',
           'find_conflicts', 'free_slots', 'first_free']
