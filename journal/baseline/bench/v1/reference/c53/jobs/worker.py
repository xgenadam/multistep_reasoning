"""Simulated workers on a manual clock."""

from __future__ import annotations

from typing import NamedTuple

from .retry import PermanentError


class ManualClock:
    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, dt: float) -> None:
        if dt < 0:
            raise ValueError('cannot go back in time')
        self._now += dt

    def set(self, t: float) -> None:
        if t < self._now:
            raise ValueError('cannot go back in time')
        self._now = t


class Event(NamedTuple):
    time: float
    worker: str
    job_id: object
    attempt: int
    outcome: str
    delay: float | None = None


class Worker:
    def __init__(self, name, queue, handler, policy, rng, clock):
        self.name = name
        self.queue = queue
        self.handler = handler
        self.policy = policy
        self.rng = rng
        self.clock = clock

    def step(self) -> Event | None:
        job = self.queue.claim()
        if job is None:
            return None
        now = self.clock()
        try:
            self.handler(job.payload)
        except PermanentError as exc:
            self.queue.bury(job.id, _describe(exc))
            return Event(now, self.name, job.id, job.attempts, 'dead')
        except Exception as exc:
            if self.policy.should_retry(job.attempts):
                delay = self.policy.delay(job.attempts, self.rng)
                self.queue.retry(job.id, _describe(exc), self.clock() + delay)
                return Event(now, self.name, job.id, job.attempts, 'retry', delay)
            self.queue.bury(job.id, _describe(exc))
            return Event(now, self.name, job.id, job.attempts, 'dead')
        self.queue.complete(job.id)
        return Event(now, self.name, job.id, job.attempts, 'done')


def _describe(exc: BaseException) -> str:
    return f'{type(exc).__name__}: {exc}'


def run_until_idle(queue, workers, clock, max_steps: int = 10000) -> list[Event]:
    events: list[Event] = []
    while True:
        progressed = False
        for worker in workers:
            event = worker.step()
            if event is not None:
                events.append(event)
                progressed = True
                if len(events) > max_steps:
                    raise RuntimeError(f'more than {max_steps} events')
        if progressed:
            continue
        nxt = queue.next_available()
        if nxt is None:
            return events
        clock.set(nxt)
