"""Retry policy: exponential backoff with multiplicative jitter."""

from __future__ import annotations

from dataclasses import dataclass


class PermanentError(Exception):
    """Raised by a handler for a failure that must not be retried."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base: float = 1.0
    factor: float = 2.0
    max_delay: float = 60.0
    jitter: float = 0.0

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError('max_attempts must be >= 1')
        if self.base <= 0:
            raise ValueError('base must be > 0')
        if self.factor < 1:
            raise ValueError('factor must be >= 1')
        if self.max_delay < self.base:
            raise ValueError('max_delay must be >= base')
        if not 0 <= self.jitter < 1:
            raise ValueError('jitter must be in [0, 1)')

    def backoff(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError('attempt must be >= 1')
        return min(self.max_delay, self.base * self.factor ** (attempt - 1))

    def delay(self, attempt: int, rng) -> float:
        u = rng.random()
        return self.backoff(attempt) * (1 + self.jitter * u)

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts
