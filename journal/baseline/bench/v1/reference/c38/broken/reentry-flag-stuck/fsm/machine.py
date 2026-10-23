"""A small declarative finite-state machine."""
from dataclasses import dataclass, field
from typing import Any, Callable


class MachineError(Exception):
    """Base class for machine errors."""


class InvalidTransition(MachineError):
    def __init__(self, state: str, event: str):
        super().__init__(f'no transition for {event!r} from {state!r}')
        self.state = state
        self.event = event


class GuardRejected(MachineError):
    def __init__(self, state: str, event: str):
        super().__init__(f'every guard rejected {event!r} from {state!r}')
        self.state = state
        self.event = event


@dataclass
class State:
    name: str
    on_enter: Callable | None = None
    on_exit: Callable | None = None


@dataclass
class Transition:
    event: str
    source: Any
    target: str | None
    guard: Callable | None = None
    action: Callable | None = None

    def sources(self) -> tuple[str, ...] | None:
        """The source names, or None for '*' (every state)."""
        if self.source == '*':
            return None
        if isinstance(self.source, (list, tuple)):
            return tuple(self.source)
        return (self.source,)

    def leaves(self, state: str) -> bool:
        names = self.sources()
        return names is None or state in names


@dataclass
class Event:
    name: str
    source: str
    target: str
    data: dict = field(default_factory=dict)


class Machine:
    def __init__(self, states, transitions, initial: str, context=None):
        states = list(states)
        if not states:
            raise ValueError('a machine needs at least one state')
        self._states: dict[str, State] = {}
        for s in states:
            st = s if isinstance(s, State) else State(s)
            if st.name in self._states:
                raise ValueError(f'duplicate state {st.name!r}')
            self._states[st.name] = st
        if initial not in self._states:
            raise ValueError(f'unknown initial state {initial!r}')
        self._transitions = list(transitions)
        for t in self._transitions:
            for name in t.sources() or ():
                if name not in self._states:
                    raise ValueError(f'unknown source state {name!r}')
            if t.target is not None and t.target not in self._states:
                raise ValueError(f'unknown target state {t.target!r}')
        self.initial = initial
        self.state = initial
        self.context = context
        self.history: list[tuple[str, str, str]] = []
        self._listeners: list[Callable] = []
        self._firing = False

    # ------------------------------------------------------------ queries
    def _candidates(self, event: str) -> list[Transition]:
        return [t for t in self._transitions if t.event == event and t.leaves(self.state)]

    def _choose(self, event: str, data: dict) -> tuple[Transition | None, Event | None, bool]:
        """(transition, event, had_candidates)."""
        candidates = self._candidates(event)
        for t in candidates:
            target = self.state if t.target is None else t.target
            ev = Event(event, self.state, target, data)
            if t.guard is None or t.guard(self, ev):
                return t, ev, True
        return None, None, bool(candidates)

    def can_fire(self, event: str, **data) -> bool:
        """Whether fire(event, **data) would take a transition now (guards only)."""
        t, _, _ = self._choose(event, data)
        return t is not None

    def available_events(self) -> list[str]:
        """Sorted event names with a transition from the current state, ignoring guards."""
        return sorted({t.event for t in self._transitions if t.leaves(self.state)})

    def on_transition(self, listener: Callable) -> None:
        """Add a listener called as listener(source, event, target)."""
        self._listeners.append(listener)

    def reset(self) -> None:
        """Back to the initial state with an empty history; no hooks run."""
        self.state = self.initial
        self.history.clear()

    # ------------------------------------------------------------ firing
    def fire(self, event: str, **data) -> str:
        """Take one transition for `event` and return the new state.

        Raises InvalidTransition, GuardRejected, MachineError (re-entry) or
        whatever a hook raised.
        """
        if self._firing:
            raise MachineError('fire called while another fire is running')
        self._firing = True
        result = self._fire(event, data)
        self._firing = False
        return result

    def _fire(self, event: str, data: dict) -> str:
        t, ev, had = self._choose(event, data)
        if t is None:
            if had:
                raise GuardRejected(self.state, event)
            raise InvalidTransition(self.state, event)
        source = self.state
        if t.target is None:
            if t.action is not None:
                t.action(self, ev)
            self.history.append((source, event, source))
        else:
            old = self._states[source]
            if old.on_exit is not None:
                old.on_exit(self, ev)
            if t.action is not None:
                t.action(self, ev)
            self.state = t.target
            self.history.append((source, event, t.target))
            new = self._states[t.target]
            if new.on_enter is not None:
                new.on_enter(self, ev)
        for listener in list(self._listeners):
            listener(source, event, ev.target)
        return self.state
