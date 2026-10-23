import random

import pytest

from jobs import (Event, Job, JobQueue, ManualClock, PermanentError, RetryPolicy, Worker,
                  run_until_idle)


class Flaky:
    """Fails the first `failures[payload]` calls for each payload."""

    def __init__(self, failures):
        self.failures = dict(failures)
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        if self.failures.get(payload, 0) > 0:
            self.failures[payload] -= 1
            raise RuntimeError(f'boom {payload}')


# ---------------------------------------------------------------- policy

def test_backoff_exponential_and_capped():
    p = RetryPolicy(base=1.0, factor=2.0, max_delay=10.0)
    assert [p.backoff(n) for n in range(1, 7)] == [1.0, 2.0, 4.0, 8.0, 10.0, 10.0]
    assert RetryPolicy(base=0.5, factor=3).backoff(3) == 4.5
    assert RetryPolicy(factor=1).backoff(9) == 1.0
    with pytest.raises(ValueError):
        p.backoff(0)


def test_delay_jitter_formula_one_draw():
    p = RetryPolicy(base=2.0, factor=2.0, jitter=0.25)
    rng, ref = random.Random(53), random.Random(53)
    for attempt in (1, 2, 3):
        u = ref.random()
        assert p.delay(attempt, rng) == pytest.approx(p.backoff(attempt) * (0.75 + 0.5 * u))
    assert rng.random() == ref.random()


def test_delay_without_jitter_still_draws():
    p = RetryPolicy(jitter=0.0)
    rng, ref = random.Random(1), random.Random(1)
    assert p.delay(3, rng) == 4.0
    ref.random()
    assert rng.random() == ref.random()


def test_should_retry():
    p = RetryPolicy(max_attempts=3)
    assert [p.should_retry(n) for n in (1, 2, 3, 4)] == [True, True, False, False]
    assert RetryPolicy(max_attempts=1).should_retry(1) is False


@pytest.mark.parametrize('kwargs', [
    {'max_attempts': 0}, {'base': 0}, {'factor': 0.5}, {'max_delay': 0.5}, {'jitter': 1.0},
    {'jitter': -0.1},
])
def test_policy_validation(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


# ---------------------------------------------------------------- clock and queue

def test_manual_clock():
    c = ManualClock(5.0)
    assert c() == 5.0
    c.advance(2.5)
    c.set(10)
    assert c() == 10
    with pytest.raises(ValueError):
        c.set(9.9)
    with pytest.raises(ValueError):
        c.advance(-1)


def test_submit_and_claim_order():
    clock = ManualClock()
    q = JobQueue(clock)
    job = q.submit('a', 1, delay=5)
    assert isinstance(job, Job) and job.available_at == 5 and job.status == 'pending'
    q.submit('b', 2)
    q.submit('c', 3)
    q.submit('d', 4, delay=0.0)
    assert [q.claim().id for _ in range(3)] == ['b', 'c', 'd']
    assert q.claim() is None
    clock.set(5)
    got = q.claim()
    assert (got.id, got.status, got.attempts) == ('a', 'running', 1)


def test_claim_earliest_available_then_submission_order():
    clock = ManualClock()
    q = JobQueue(clock)
    q.submit('late', 0, delay=3)
    q.submit('early', 0, delay=1)
    q.submit('tie', 0, delay=1)
    clock.set(10)
    assert [q.claim().id for _ in range(3)] == ['early', 'tie', 'late']


def test_submit_errors():
    q = JobQueue(ManualClock())
    q.submit('a', None)
    with pytest.raises(ValueError):
        q.submit('a', None)
    with pytest.raises(ValueError):
        q.submit('b', None, delay=-1)


def test_state_transitions_and_errors():
    clock = ManualClock()
    q = JobQueue(clock)
    for name in 'xyz':
        q.submit(name, name)
    for _ in range(3):
        q.claim()
    q.complete('x')
    q.retry('y', 'E: no', 7.0)
    q.bury('z', 'E: dead')
    assert q.get('y').status == 'pending' and q.get('y').available_at == 7.0
    assert q.get('y').last_error == 'E: no'
    assert q.counts() == {'pending': 1, 'running': 0, 'done': 1, 'dead': 1}
    assert [j.id for j in q.dead_letters()] == ['z']
    assert q.next_available() == 7.0
    with pytest.raises(ValueError):
        q.complete('x')
    with pytest.raises(ValueError):
        q.bury('y', 'not running')
    with pytest.raises(KeyError):
        q.complete('nope')
    with pytest.raises(KeyError):
        q.get('nope')


def test_next_available_none_and_dead_letters_copy():
    q = JobQueue(ManualClock())
    assert q.next_available() is None
    q.dead_letters().append('junk')
    assert q.dead_letters() == []


# ---------------------------------------------------------------- workers

def make(policy=None, failures=None, seed=7, workers=1, start=0.0):
    clock = ManualClock(start)
    q = JobQueue(clock)
    handler = Flaky(failures or {})
    rng = random.Random(seed)
    ws = [Worker(f'w{i}', q, handler, policy or RetryPolicy(), rng, clock)
          for i in range(workers)]
    return clock, q, handler, ws, rng


def test_worker_step_success():
    clock, q, handler, (w,), _ = make(start=3.0)
    q.submit('j1', 'p')
    assert w.step() == Event(3.0, 'w0', 'j1', 1, 'done', None)
    assert q.get('j1').status == 'done'
    assert w.step() is None


def test_worker_step_retry_uses_policy_delay():
    policy = RetryPolicy(base=2.0, jitter=0.5)
    clock, q, handler, (w,), _ = make(policy, {'p': 1}, seed=11, start=100.0)
    q.submit('j1', 'p')
    expected = policy.delay(1, random.Random(11))
    ev = w.step()
    assert ev.outcome == 'retry' and ev.attempt == 1 and ev.time == 100.0
    assert ev.delay == pytest.approx(expected)
    job = q.get('j1')
    assert job.status == 'pending' and job.available_at == pytest.approx(100.0 + expected)
    assert job.last_error == 'RuntimeError: boom p'


def test_permanent_error_goes_straight_to_dead_letters():
    clock = ManualClock()
    q = JobQueue(clock)

    def handler(payload):
        raise PermanentError('bad input')

    w = Worker('w', q, handler, RetryPolicy(max_attempts=9), random.Random(0), clock)
    q.submit('j', None)
    assert w.step() == Event(0.0, 'w', 'j', 1, 'dead', None)
    assert q.get('j').last_error == 'PermanentError: bad input'
    assert q.dead_letters()[0].id == 'j'


def test_run_until_idle_backoff_timeline():
    policy = RetryPolicy(max_attempts=4, base=1.0, factor=2.0, jitter=0.0)
    clock, q, handler, ws, _ = make(policy, {'p': 3})
    q.submit('j', 'p')
    events = run_until_idle(q, ws, clock)
    assert [(e.time, e.attempt, e.outcome, e.delay) for e in events] == [
        (0.0, 1, 'retry', 1.0), (1.0, 2, 'retry', 2.0), (3.0, 3, 'retry', 4.0),
        (7.0, 4, 'done', None)]
    assert clock() == 7.0


def test_dead_after_max_attempts():
    policy = RetryPolicy(max_attempts=3, jitter=0.0)
    clock, q, handler, ws, _ = make(policy, {'p': 99})
    q.submit('j', 'p')
    events = run_until_idle(q, ws, clock)
    assert [e.outcome for e in events] == ['retry', 'retry', 'dead']
    assert handler.calls == ['p', 'p', 'p']
    assert q.get('j').attempts == 3 and q.counts()['dead'] == 1


def test_round_robin_across_workers():
    clock, q, handler, ws, _ = make(RetryPolicy(jitter=0.0), {'b': 1}, workers=2)
    for name in 'abc':
        q.submit(name, name)
    events = run_until_idle(q, ws, clock)
    assert [(e.time, e.worker, e.job_id, e.outcome) for e in events] == [
        (0.0, 'w0', 'a', 'done'), (0.0, 'w1', 'b', 'retry'), (0.0, 'w0', 'c', 'done'),
        (1.0, 'w0', 'b', 'done')]


def test_delayed_submission_and_jump():
    clock, q, handler, ws, _ = make()
    q.submit('later', 'x', delay=50)
    q.submit('now', 'y')
    events = run_until_idle(q, ws, clock)
    assert [(e.time, e.job_id) for e in events] == [(0.0, 'now'), (50.0, 'later')]


def test_seeded_jitter_reproducible():
    policy = RetryPolicy(max_attempts=5, base=1.0, jitter=0.3)

    def simulate(seed):
        clock, q, handler, ws, _ = make(policy, {'a': 2, 'b': 3, 'c': 1}, seed=seed,
                                        workers=2)
        for name in 'abc':
            q.submit(name, name)
        return run_until_idle(q, ws, clock)

    first, again, other = simulate(5), simulate(5), simulate(6)
    assert first == again
    assert first != other
    rng = random.Random(5)
    retries = [e for e in first if e.outcome == 'retry']
    assert len(retries) == 6
    for e in retries:
        assert e.delay == pytest.approx(policy.delay(e.attempt, rng))


def test_max_steps_guard():
    clock, q, handler, ws, _ = make(RetryPolicy(max_attempts=50, jitter=0.0), {'p': 99})
    q.submit('j', 'p')
    with pytest.raises(RuntimeError):
        run_until_idle(q, ws, clock, max_steps=10)
