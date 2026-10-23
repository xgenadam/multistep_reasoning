import pytest

from lru import LRUCache


def filled(*keys, capacity=3):
    cache = LRUCache(capacity)
    for k in keys:
        cache.put(k, k.upper())
    return cache


@pytest.mark.parametrize('capacity', [0, -1])
def test_capacity_below_one_raises(capacity):
    with pytest.raises(ValueError):
        LRUCache(capacity)


def test_get_returns_value_and_default():
    cache = filled('a')
    assert cache.get('a') == 'A'
    assert cache.get('zz') is None
    assert cache.get('zz', 42) == 42


def test_put_returns_none_until_full():
    cache = LRUCache(2)
    assert cache.put('a', 1) is None
    assert cache.put('b', 2) is None
    assert len(cache) == 2


def test_put_evicts_least_recent_and_returns_it():
    cache = filled('a', 'b', 'c')
    assert cache.put('d', 'D') == 'a'
    assert 'a' not in cache
    assert cache.keys() == ['b', 'c', 'd']


def test_get_refreshes_recency():
    cache = filled('a', 'b', 'c')
    cache.get('a')
    assert cache.put('d', 'D') == 'b'
    assert cache.keys() == ['c', 'a', 'd']


def test_missing_get_changes_nothing():
    cache = filled('a', 'b', 'c')
    cache.get('zz')
    assert cache.keys() == ['a', 'b', 'c']
    assert len(cache) == 3


def test_update_existing_key_never_evicts():
    cache = filled('a', 'b', 'c')
    assert cache.put('a', 'new') is None
    assert len(cache) == 3
    assert cache.get('a') == 'new'
    assert cache.keys() == ['b', 'c', 'a']


def test_update_refreshes_recency():
    cache = filled('a', 'b', 'c')
    cache.put('a', 1)
    assert cache.put('d', 'D') == 'b'


def test_contains_does_not_touch_recency():
    cache = filled('a', 'b', 'c')
    assert 'a' in cache
    assert 'zz' not in cache
    assert cache.put('d', 'D') == 'a'


def test_keys_oldest_first_and_is_a_list():
    cache = filled('a', 'b', 'c')
    keys = cache.keys()
    assert isinstance(keys, list)
    assert keys == ['a', 'b', 'c']
    keys.append('x')  # a copy, not a view
    assert cache.keys() == ['a', 'b', 'c']


def test_capacity_one():
    cache = LRUCache(1)
    assert cache.put('a', 1) is None
    assert cache.put('b', 2) == 'a'
    assert cache.keys() == ['b']


def test_none_values_are_stored():
    cache = LRUCache(2)
    cache.put('a', None)
    assert 'a' in cache
    assert cache.get('a', 'default') is None


def test_resize_down_evicts_in_order():
    cache = filled('a', 'b', 'c', capacity=4)
    cache.put('d', 'D')
    cache.get('a')  # order: b c d a
    assert cache.resize(2) == ['b', 'c']
    assert cache.keys() == ['d', 'a']
    assert cache.put('e', 'E') == 'd'


def test_resize_up_keeps_everything():
    cache = filled('a', 'b')
    assert cache.resize(5) == []
    for k in 'cde':
        assert cache.put(k, k) is None
    assert len(cache) == 5
    assert cache.put('f', 'f') == 'a'


@pytest.mark.parametrize('capacity', [0, -3])
def test_resize_below_one_raises(capacity):
    cache = filled('a')
    with pytest.raises(ValueError):
        cache.resize(capacity)


def test_long_sequence_matches_model():
    import random
    rng = random.Random(6)
    cache, model = LRUCache(5), []
    for _ in range(2000):
        k = rng.randrange(9)
        if rng.random() < 0.5:
            evicted = cache.put(k, k * 10)
            if k in model:
                model.remove(k)
                expected = None
            elif len(model) == 5:
                expected = model.pop(0)
            else:
                expected = None
            model.append(k)
            assert evicted == expected
        else:
            got = cache.get(k)
            if k in model:
                model.remove(k)
                model.append(k)
                assert got == k * 10
            else:
                assert got is None
        assert cache.keys() == model
