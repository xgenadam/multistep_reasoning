import random

import pytest

import search
from search import (count, first_index, insertion_point, isqrt, last_index, rotation_offset,
                    search_rotated)

DUPS = [1, 2, 2, 2, 2, 2, 2, 3, 5, 5, 8]


def test_first_and_last_with_duplicates():
    assert first_index(DUPS, 2) == 1
    assert last_index(DUPS, 2) == 6
    assert first_index(DUPS, 5) == 8 and last_index(DUPS, 5) == 9
    assert first_index(DUPS, 1) == 0 and last_index(DUPS, 8) == 10


def test_absent_and_empty():
    for x in (0, 4, 9):
        assert first_index(DUPS, x) == -1
        assert last_index(DUPS, x) == -1
    assert first_index([], 1) == -1 and last_index([], 1) == -1


def test_all_equal():
    a = [7] * 9
    assert first_index(a, 7) == 0 and last_index(a, 7) == 8 and count(a, 7) == 9


def test_insertion_point():
    assert insertion_point(DUPS, 2) == 1
    assert insertion_point(DUPS, 4) == 8
    assert insertion_point(DUPS, 0) == 0
    assert insertion_point(DUPS, 9) == len(DUPS)
    assert insertion_point([], 3) == 0


def test_count():
    assert count(DUPS, 2) == 6
    assert count(DUPS, 4) == 0
    assert count([], 4) == 0


def test_matches_bisect_on_random_lists():
    import bisect
    rng = random.Random(27)
    for _ in range(300):
        a = sorted(rng.randrange(10) for _ in range(rng.randrange(15)))
        x = rng.randrange(-1, 11)
        assert insertion_point(a, x) == bisect.bisect_left(a, x)
        assert count(a, x) == a.count(x)
        exp_first = a.index(x) if x in a else -1
        exp_last = len(a) - 1 - a[::-1].index(x) if x in a else -1
        assert first_index(a, x) == exp_first
        assert last_index(a, x) == exp_last


def test_search_rotated():
    a = [40, 50, 10, 20, 30]
    for i, x in enumerate(a):
        assert search_rotated(a, x) == i
    assert search_rotated(a, 35) == -1
    assert search_rotated(a, 5) == -1
    assert search_rotated(a, 60) == -1
    assert search_rotated([], 1) == -1
    assert search_rotated([3], 3) == 0


def test_search_rotated_every_rotation():
    base = [2, 4, 6, 8, 10, 12, 14]
    for k in range(len(base)):
        a = base[k:] + base[:k]
        for i, x in enumerate(a):
            assert search_rotated(a, x) == i, (a, x)
        for x in (1, 5, 15):
            assert search_rotated(a, x) == -1


def test_rotation_offset():
    assert rotation_offset([40, 50, 10, 20, 30]) == 2
    assert rotation_offset([1, 2, 3]) == 0
    assert rotation_offset([5]) == 0
    assert rotation_offset([2, 1]) == 1
    base = list(range(10))
    for k in range(10):
        assert rotation_offset(base[k:] + base[:k]) == (10 - k) % 10
    with pytest.raises(ValueError):
        rotation_offset([])


def test_isqrt_small():
    assert [isqrt(n) for n in range(17)] == [0, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 4]


def test_isqrt_large_exact():
    for r in (10**15 + 7, 10**30 + 3, 3**200):
        assert isqrt(r * r) == r
        assert isqrt(r * r - 1) == r - 1
        assert isqrt(r * r + 2 * r) == r


def test_isqrt_errors():
    with pytest.raises(ValueError):
        isqrt(-1)
    for bad in (4.0, '4', True):
        with pytest.raises(TypeError):
            isqrt(bad)


def test_arguments_not_modified():
    a = list(DUPS)
    first_index(a, 2), last_index(a, 2), insertion_point(a, 2), count(a, 2)
    r = [40, 50, 10, 20, 30]
    search_rotated(r, 20), rotation_offset(r)
    assert a == DUPS and r == [40, 50, 10, 20, 30]


class Counting(list):
    """A list that counts element reads by index."""

    reads = 0

    def __getitem__(self, i):
        self.reads += 1
        return super().__getitem__(i)


def test_logarithmic_reads():
    a = Counting([0] * 5000 + [1] * 5000 + [2] * 5000)
    for fn in (first_index, last_index, insertion_point, count):
        a.reads = 0
        fn(a, 1)
        assert a.reads <= 80, fn.__name__
    r = Counting(list(range(7000, 20000)) + list(range(7000)))
    for fn in (lambda s: search_rotated(s, 123), rotation_offset):
        r.reads = 0
        fn(r)
        assert r.reads <= 120
