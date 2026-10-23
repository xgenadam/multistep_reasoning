import pytest

from ratelimit import TokenBucket


class Clock:
    def __init__(self, t=500.0):
        self.t = t
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.t

    def advance(self, dt):
        self.t += dt


@pytest.fixture
def clock():
    return Clock()


def test_invalid_rate_or_capacity(clock):
    for rate, capacity in [(0, 5), (-1, 5), (1, 0), (1, -2)]:
        with pytest.raises(ValueError):
            TokenBucket(rate, capacity, clock)


def test_starts_full_and_reads_injected_clock(clock):
    b = TokenBucket(2, 4, clock)
    assert clock.calls >= 1
    assert b.available() == pytest.approx(4)
    assert all(b.try_acquire() for _ in range(4))
    assert b.try_acquire() is False


def test_default_clock_works():
    b = TokenBucket(1000, 3)
    assert b.try_acquire(3) is True


def test_refill_is_continuous_and_fractional(clock):
    b = TokenBucket(1, 4, clock)
    assert b.try_acquire(4)
    clock.advance(0.5)
    assert b.available() == pytest.approx(0.5)
    assert b.try_acquire() is False
    clock.advance(0.5)
    assert b.try_acquire() is True
    assert b.available() == pytest.approx(0)


def test_refill_capped_at_capacity(clock):
    b = TokenBucket(2, 4, clock)
    assert b.try_acquire(3)
    clock.advance(100)
    assert b.available() == pytest.approx(4)
    assert b.try_acquire(4) is True
    assert b.try_acquire(0.5) is False


def test_failed_acquire_removes_nothing(clock):
    b = TokenBucket(1, 5, clock)
    assert b.try_acquire(4)
    assert b.try_acquire(2) is False
    assert b.available() == pytest.approx(1)
    assert b.try_acquire(1) is True


def test_wait_time(clock):
    b = TokenBucket(4, 8, clock)
    assert b.wait_time(8) == 0.0
    assert b.try_acquire(8)
    assert b.wait_time(1) == pytest.approx(0.25)
    assert b.wait_time(8) == pytest.approx(2.0)
    clock.advance(0.5)          # 2 tokens now
    assert b.wait_time(2) == 0.0
    assert b.wait_time(3) == pytest.approx(0.25)
    assert b.available() == pytest.approx(2)  # wait_time removed nothing


def test_wait_time_then_acquire_succeeds(clock):
    b = TokenBucket(2, 10, clock)
    assert b.try_acquire(10)
    clock.advance(1.25)
    wait = b.wait_time(6)
    assert wait == pytest.approx(1.75)
    clock.advance(wait)
    assert b.try_acquire(6) is True


def test_wait_time_returns_float(clock):
    b = TokenBucket(1, 2, clock)
    assert isinstance(b.wait_time(), float)
    b.try_acquire(2)
    assert isinstance(b.wait_time(), float)


def test_bad_n(clock):
    b = TokenBucket(1, 3, clock)
    for n in (0, -1, 3.5, 4):
        with pytest.raises(ValueError):
            b.try_acquire(n)
        with pytest.raises(ValueError):
            b.wait_time(n)
    assert b.try_acquire(3) is True  # exactly capacity is allowed


def test_clock_going_backwards(clock):
    b = TokenBucket(1, 10, clock)
    assert b.try_acquire(10)
    clock.advance(2)
    assert b.available() == pytest.approx(2)
    clock.advance(-5)
    assert b.available() == pytest.approx(2)
    clock.advance(4)            # still 1 s before the latest reading
    assert b.available() == pytest.approx(2)
    clock.advance(2)            # 1 s after the latest reading
    assert b.available() == pytest.approx(3)


def test_steady_rate_over_many_steps(clock):
    b = TokenBucket(10, 5, clock)
    assert b.try_acquire(5)
    granted = 0
    for _ in range(1000):
        clock.advance(0.0625)
        while b.try_acquire():
            granted += 1
    assert granted == 625  # 10 per second for 62.5 s


def test_float_rate_and_capacity(clock):
    b = TokenBucket(0.5, 1.5, clock)
    assert b.try_acquire(1.5)
    assert b.wait_time(1) == pytest.approx(2.0)
    clock.advance(2)
    assert b.try_acquire(1) is True
