import pytest

from lru import LRUCache


class Clock:
    def __init__(self, t=1000.0):
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


@pytest.mark.parametrize('ttl', [0, -1, -0.5])
def test_ttl_must_be_positive(ttl, clock):
    with pytest.raises(ValueError):
        LRUCache(2, ttl=ttl, clock=clock)


def test_default_clock_works_without_ttl():
    cache = LRUCache(2)
    cache.put('a', 1)
    assert cache.get('a') == 1
    assert cache.stats() == {'hits': 1, 'misses': 0, 'evictions': 0, 'expirations': 0}


def test_expires_exactly_at_ttl(clock):
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put('a', 1)
    clock.advance(9.999)
    assert cache.get('a') == 1
    clock.advance(0.001)
    assert cache.get('a') is None
    assert cache.get('a', 'gone') == 'gone'


def test_get_does_not_extend_life(clock):
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put('a', 1)
    for _ in range(3):
        clock.advance(3)
        assert cache.get('a') == 1
    clock.advance(1)  # 10 s after the put
    assert 'a' not in cache


def test_put_restarts_the_clock(clock):
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put('a', 1)
    clock.advance(8)
    cache.put('a', 2)
    clock.advance(8)
    assert cache.get('a') == 2
    clock.advance(2)
    assert cache.get('a') is None


def test_expired_entries_are_invisible(clock):
    cache = LRUCache(3, ttl=5, clock=clock)
    cache.put('a', 1)
    clock.advance(2)
    cache.put('b', 2)
    clock.advance(3)  # a expired, b has 2 s left
    assert 'a' not in cache
    assert len(cache) == 1
    assert cache.keys() == ['b']


def test_expired_entries_do_not_count_towards_capacity(clock):
    cache = LRUCache(2, ttl=5, clock=clock)
    cache.put('a', 1)
    clock.advance(1)
    cache.put('b', 2)
    clock.advance(4)  # a expired
    assert cache.put('c', 3) is None  # room without evicting b
    assert cache.keys() == ['b', 'c']
    assert cache.stats()['evictions'] == 0


def test_put_returns_only_a_live_evicted_key(clock):
    cache = LRUCache(2, ttl=100, clock=clock)
    cache.put('a', 1)
    cache.put('b', 2)
    cache.get('a')
    assert cache.put('c', 3) == 'b'
    assert cache.stats()['evictions'] == 1


def test_put_of_an_expired_key_is_a_new_key(clock):
    cache = LRUCache(2, ttl=5, clock=clock)
    cache.put('a', 1)
    cache.put('b', 2)
    clock.advance(5)  # both expired
    assert cache.put('a', 10) is None
    assert cache.keys() == ['a']
    assert cache.get('a') == 10
    assert cache.stats()['expirations'] == 2


def test_lru_order_among_live_entries(clock):
    cache = LRUCache(3, ttl=100, clock=clock)
    for k in 'abc':
        cache.put(k, k)
        clock.advance(1)
    cache.get('a')
    assert cache.keys() == ['b', 'c', 'a']
    assert cache.put('d', 'd') == 'b'


def test_stats_counts(clock):
    cache = LRUCache(2, ttl=10, clock=clock)
    cache.put('a', 1)
    cache.get('a')          # hit
    cache.get('x')          # miss
    'a' in cache            # neither
    cache.put('b', 2)
    cache.put('c', 3)       # evicts a
    clock.advance(10)       # b and c expire
    cache.get('b')          # miss
    assert cache.stats() == {'hits': 1, 'misses': 2, 'evictions': 1, 'expirations': 2}


def test_expirations_count_without_being_looked_at(clock):
    cache = LRUCache(5, ttl=1, clock=clock)
    for k in 'abc':
        cache.put(k, k)
    clock.advance(1)
    assert cache.stats()['expirations'] == 3
    assert cache.stats()['expirations'] == 3  # each entry once


def test_replaced_or_evicted_entries_never_expire(clock):
    cache = LRUCache(1, ttl=10, clock=clock)
    cache.put('a', 1)
    cache.put('a', 2)       # replaces the first entry
    cache.put('b', 3)       # evicts a
    clock.advance(10)       # only b expires
    assert cache.stats() == {'hits': 0, 'misses': 0, 'evictions': 1, 'expirations': 1}


def test_stats_is_a_fresh_dict_with_four_int_keys(clock):
    cache = LRUCache(2, ttl=10, clock=clock)
    s = cache.stats()
    assert set(s) == {'hits', 'misses', 'evictions', 'expirations'}
    assert all(type(v) is int for v in s.values())
    s['hits'] = 99
    assert cache.stats()['hits'] == 0


def test_resize_skips_expired_entries(clock):
    cache = LRUCache(4, ttl=10, clock=clock)
    cache.put('a', 1)
    clock.advance(5)
    for k in 'bcd':
        cache.put(k, k)
    clock.advance(5)  # a expired
    assert cache.resize(2) == ['b']
    assert cache.keys() == ['c', 'd']
    assert cache.stats()['evictions'] == 1
    assert cache.stats()['expirations'] == 1


def test_no_ttl_never_expires(clock):
    cache = LRUCache(2, clock=clock)
    cache.put('a', 1)
    clock.advance(10 ** 9)
    assert cache.get('a') == 1
    assert cache.stats()['expirations'] == 0


def test_time_is_read_only_through_the_clock(clock, monkeypatch):
    import time
    monkeypatch.setattr(time, 'monotonic', lambda: (_ for _ in ()).throw(AssertionError('wall clock')))
    monkeypatch.setattr(time, 'time', lambda: (_ for _ in ()).throw(AssertionError('wall clock')))
    cache = LRUCache(2, ttl=5, clock=clock)
    cache.put('a', 1)
    clock.advance(5)
    assert cache.get('a') is None
    assert clock.calls > 0
