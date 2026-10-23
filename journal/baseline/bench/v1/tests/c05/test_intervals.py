import random

import pytest

from intervals import insert, intersect, merge, remove


def points(intervals):
    return {x for s, e in intervals for x in range(s, e)}


def is_normal(result):
    assert isinstance(result, list)
    for item in result:
        assert type(item) is tuple and len(item) == 2
        assert item[0] < item[1]
    for (a, b), (c, d) in zip(result, result[1:]):
        assert b < c
    return True


def random_intervals(rng, n=6, lo=0, hi=40):
    out = []
    for _ in range(n):
        s = rng.randrange(lo, hi)
        out.append((s, s + rng.randrange(0, 8)))
    return out


def test_merge_example():
    assert merge([(5, 8), (1, 3), (2, 4), (8, 9), (6, 6)]) == [(1, 4), (5, 9)]


def test_merge_touching_intervals_coalesce():
    assert merge([(3, 5), (1, 3)]) == [(1, 5)]


def test_merge_gap_of_one_stays_apart():
    assert merge([(1, 3), (4, 6)]) == [(1, 3), (4, 6)]


def test_merge_nested_and_duplicates():
    assert merge([(0, 10), (2, 3), (0, 10), (9, 10)]) == [(0, 10)]


def test_merge_empty_inputs():
    assert merge([]) == []
    assert merge([(4, 4), (7, 7)]) == []


def test_accepts_lists_and_generators_and_returns_tuples():
    result = merge(iter([[2, 4], [0, 1]]))
    assert result == [(0, 1), (2, 4)]
    assert all(type(x) is tuple for x in result)


def test_negative_numbers():
    assert merge([(-5, -2), (-2, 0), (-10, -8)]) == [(-10, -8), (-5, 0)]


def test_arguments_not_modified():
    a = [(5, 8), (1, 3)]
    b = [[2, 6]]
    merge(a)
    insert(a, (3, 5))
    remove(a, (2, 6))
    intersect(a, b)
    assert a == [(5, 8), (1, 3)]
    assert b == [[2, 6]]


def test_invalid_interval_raises_everywhere():
    with pytest.raises(ValueError):
        merge([(1, 2), (5, 3)])
    with pytest.raises(ValueError):
        insert([(1, 2)], (4, 1))
    with pytest.raises(ValueError):
        remove([(1, 2)], (9, 8))
    with pytest.raises(ValueError):
        intersect([(1, 2)], [(3, 2)])


def test_insert_bridges_neighbours():
    assert insert([(1, 3), (6, 9)], (3, 6)) == [(1, 9)]
    assert insert([(1, 3), (6, 9)], (4, 5)) == [(1, 3), (4, 5), (6, 9)]
    assert insert([(1, 3)], (0, 0)) == [(1, 3)]


def test_remove_examples():
    assert remove([(0, 10)], (3, 5)) == [(0, 3), (5, 10)]
    assert remove([(0, 10)], (0, 10)) == []
    assert remove([(0, 4), (6, 10)], (2, 8)) == [(0, 2), (8, 10)]


def test_remove_keeps_boundaries_exact():
    assert remove([(0, 10)], (0, 1)) == [(1, 10)]
    assert remove([(0, 10)], (9, 10)) == [(0, 9)]
    assert remove([(0, 5)], (5, 9)) == [(0, 5)]
    assert remove([(0, 5)], (3, 3)) == [(0, 5)]


def test_remove_from_unsorted_overlapping_input():
    assert remove([(8, 12), (0, 5), (4, 9)], (5, 6)) == [(0, 5), (6, 12)]


def test_intersect_examples():
    assert intersect([(0, 5)], [(5, 9)]) == []
    assert intersect([(0, 10)], [(2, 3), (5, 7)]) == [(2, 3), (5, 7)]
    assert intersect([(0, 4), (6, 10)], [(3, 7)]) == [(3, 4), (6, 7)]
    assert intersect([], [(0, 9)]) == []


def test_intersect_result_is_coalesced():
    assert intersect([(0, 3), (3, 6)], [(1, 5)]) == [(1, 5)]
    assert intersect([(0, 5)], [(0, 2), (2, 5)]) == [(0, 5)]


def test_random_against_point_sets():
    rng = random.Random(5)
    for _ in range(400):
        a = random_intervals(rng)
        b = random_intervals(rng)
        new = random_intervals(rng, n=1)[0]
        m = merge(a)
        assert is_normal(m) and points(m) == points(a)
        ins = insert(a, new)
        assert is_normal(ins) and points(ins) == points(a) | points([new])
        rem = remove(a, new)
        assert is_normal(rem) and points(rem) == points(a) - points([new])
        both = intersect(a, b)
        assert is_normal(both) and points(both) == points(a) & points(b)
