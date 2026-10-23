"""A token-bucket rate limiter driven by an injectable clock."""
import time


class TokenBucket:
    def __init__(self, rate, capacity, clock=time.monotonic):
        if not rate > 0:
            raise ValueError('rate must be greater than 0')
        if not capacity > 0:
            raise ValueError('capacity must be greater than 0')
        self.rate = rate
        self.capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        if now <= self._last:
            return
        self._tokens = min(float(self.capacity), self._tokens + (now - self._last) * self.rate)
        self._last = now

    def _check(self, n) -> None:
        if not n > 0:
            raise ValueError('n must be greater than 0')

    def try_acquire(self, n=1) -> bool:
        self._check(n)
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False

    def wait_time(self, n=1) -> float:
        self._check(n)
        self._refill()
        if self._tokens >= n:
            return 0.0
        return (n - self._tokens) / self.rate

    def available(self) -> float:
        self._refill()
        return self._tokens
