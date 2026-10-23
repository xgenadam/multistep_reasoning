import random

import pytest

from pq import TaskQueue


def drain(q):
    out = []
    while len(q):
        out.append(q.pop())
    return out


def test_lowest_priority_first():
    q = TaskQueue()
    q.push('b', 2)
    q.push('a', 1)
    q.push('c', 3)
    assert drain(q) == [('a', 1), ('b', 2), ('c', 3)]


def test_fifo_among_equal_priorities():
    q = TaskQueue()
    for t in ['zeta', 'alpha', 'mid', 'beta']:
        q.push(t, 5)
    q.push('first', 1)
    assert [t for t, _ in drain(q)] == ['first', 'zeta', 'alpha', 'mid', 'beta']


def test_peek_does_not_remove():
    q = TaskQueue()
    q.push('x', 3)
    q.push('y', 1)
    assert q.peek() == ('y', 1)
    assert len(q) == 2
    assert q.pop() == ('y', 1)


def test_empty_raises_index_error():
    q = TaskQueue()
    with pytest.raises(IndexError):
        q.pop()
    with pytest.raises(IndexError):
        q.peek()


def test_duplicate_push_raises():
    q = TaskQueue()
    q.push('a', 1)
    with pytest.raises(ValueError):
        q.push('a', 2)
    assert q.priority('a') == 1


def test_reprioritize_moves_task():
    q = TaskQueue()
    q.push('a', 1)
    q.push('b', 2)
    q.push('c', 3)
    q.reprioritize('c', 0)
    q.reprioritize('a', 10)
    assert q.priority('a') == 10
    assert drain(q) == [('c', 0), ('b', 2), ('a', 10)]


def test_reprioritize_goes_behind_equals():
    q = TaskQueue()
    for t in 'abc':
        q.push(t, 1)
    q.reprioritize('a', 1)  # same priority, but now counts as newest
    assert [t for t, _ in drain(q)] == ['b', 'c', 'a']


def test_reprioritize_missing_raises():
    q = TaskQueue()
    with pytest.raises(KeyError):
        q.reprioritize('nope', 1)


def test_remove():
    q = TaskQueue()
    for i, t in enumerate('abcd'):
        q.push(t, i)
    q.remove('a')
    q.remove('c')
    assert 'a' not in q and 'b' in q
    assert len(q) == 2
    assert q.peek() == ('b', 1)
    assert drain(q) == [('b', 1), ('d', 3)]
    with pytest.raises(KeyError):
        q.remove('a')


def test_removed_task_can_be_pushed_again():
    q = TaskQueue()
    q.push('a', 1)
    q.push('b', 2)
    q.remove('a')
    q.push('a', 3)
    assert drain(q) == [('b', 2), ('a', 3)]


def test_len_after_many_reprioritizations():
    q = TaskQueue()
    q.push('a', 1)
    for p in range(50):
        q.reprioritize('a', p)
    assert len(q) == 1
    assert q.pop() == ('a', 49)
    assert len(q) == 0
    with pytest.raises(IndexError):
        q.pop()


def test_priority_missing_raises():
    with pytest.raises(KeyError):
        TaskQueue().priority('x')


def test_float_priorities_and_tuple_tasks():
    q = TaskQueue()
    q.push(('job', 1), 0.5)
    q.push(('job', 2), -1.25)
    assert q.pop() == (('job', 2), -1.25)


def test_matches_a_simple_model():
    rng = random.Random(22)
    q, model, seq = TaskQueue(), {}, 0
    for _ in range(3000):
        op = rng.random()
        task = rng.randrange(40)
        if op < 0.4:
            if task in model:
                with pytest.raises(ValueError):
                    q.push(task, 0)
            else:
                p = rng.randrange(5)
                q.push(task, p)
                model[task] = (p, seq)
                seq += 1
        elif op < 0.6 and task in model:
            p = rng.randrange(5)
            q.reprioritize(task, p)
            model[task] = (p, seq)
            seq += 1
        elif op < 0.7 and task in model:
            q.remove(task)
            del model[task]
        elif op < 1.0 and model:
            best = min(model, key=lambda t: model[t])
            assert q.pop() == (best, model[best][0])
            del model[best]
        assert len(q) == len(model)
