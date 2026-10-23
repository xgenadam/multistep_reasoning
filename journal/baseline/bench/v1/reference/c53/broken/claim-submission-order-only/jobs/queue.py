"""Jobs and the queue that schedules them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATUSES = ('pending', 'running', 'done', 'dead')


@dataclass
class Job:
    id: str
    payload: Any
    status: str = 'pending'
    attempts: int = 0
    available_at: float = 0.0
    last_error: str | None = None
    seq: int = field(default=0, repr=False, compare=False)


class JobQueue:
    def __init__(self, clock):
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._dead: list[Job] = []
        self._seq = 0

    def submit(self, job_id, payload, delay: float = 0.0) -> Job:
        if job_id in self._jobs:
            raise ValueError(f'duplicate job id {job_id!r}')
        if delay < 0:
            raise ValueError('delay must be >= 0')
        job = Job(job_id, payload, available_at=self._clock() + delay, seq=self._seq)
        self._seq += 1
        self._jobs[job_id] = job
        return job

    def claim(self) -> Job | None:
        now = self._clock()
        ready = [j for j in self._jobs.values()
                 if j.status == 'pending' and j.available_at <= now]
        if not ready:
            return None
        job = min(ready, key=lambda j: j.seq)
        job.status = 'running'
        job.attempts += 1
        return job

    def _running(self, job_id) -> Job:
        job = self._jobs[job_id]
        if job.status != 'running':
            raise ValueError(f'job {job_id!r} is {job.status}, not running')
        return job

    def complete(self, job_id) -> None:
        self._running(job_id).status = 'done'

    def retry(self, job_id, error: str, at: float) -> None:
        job = self._running(job_id)
        job.status = 'pending'
        job.available_at = at
        job.last_error = error

    def bury(self, job_id, error: str) -> None:
        job = self._running(job_id)
        job.status = 'dead'
        job.last_error = error
        self._dead.append(job)

    def get(self, job_id) -> Job:
        return self._jobs[job_id]

    def dead_letters(self) -> list[Job]:
        return list(self._dead)

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in STATUSES}
        for job in self._jobs.values():
            out[job.status] += 1
        return out

    def next_available(self) -> float | None:
        times = [j.available_at for j in self._jobs.values() if j.status == 'pending']
        return min(times) if times else None
