import random
from functools import lru_cache

from linediff import diff


def model(a, b):
    """The prompt's rule, written directly with a memoised LCS."""
    a, b = tuple(a), tuple(b)

    @lru_cache(maxsize=None)
    def lcs(i, j):
        if i == len(a) or j == len(b):
            return 0
        if a[i] == b[j]:
            return 1 + lcs(i + 1, j + 1)
        return max(lcs(i + 1, j), lcs(i, j + 1))

    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            out.append(' ' + a[i])
            i, j = i + 1, j + 1
        elif lcs(i + 1, j) >= lcs(i, j + 1):
            out.append('-' + a[i])
            i += 1
        else:
            out.append('+' + b[j])
            j += 1
    out += ['-' + x for x in a[i:]] + ['+' + x for x in b[j:]]
    return out, lcs(0, 0)


def side(script, keep):
    return [e[1:] for e in script if e[0] in keep]


def test_example_from_the_spec():
    assert diff(['a', 'b', 'c'], ['a', 'x', 'c', 'd']) == [' a', '-b', '+x', ' c', '+d']


def test_identical_and_empty():
    assert diff([], []) == []
    assert diff(['a', 'b'], ['a', 'b']) == [' a', ' b']
    assert diff([], ['x', 'y']) == ['+x', '+y']
    assert diff(['x', 'y'], []) == ['-x', '-y']


def test_deletions_before_insertions_in_a_block():
    assert diff(['a', 'b', 'c', 'z'], ['x', 'y', 'z']) == ['-a', '-b', '-c', '+x', '+y', ' z']
    assert diff(['p', 'q'], ['r', 's']) == ['-p', '-q', '+r', '+s']


def test_equal_lines_matched_as_soon_as_met():
    assert diff(['a', 'x'], ['a', 'y', 'x']) == [' a', '+y', ' x']
    assert diff(['x', 'a'], ['a', 'y', 'a']) == ['-x', ' a', '+y', '+a']


def test_insertion_when_it_keeps_more_in_common():
    assert diff(['b', 'x'], ['y', 'b']) == ['+y', ' b', '-x']
    assert diff(['b', 'a'], ['a', 'b', 'a']) == ['+a', ' b', ' a']


def test_tie_prefers_deletion():
    # Matching either 'a' or 'b' gives an LCS of 1; deleting first keeps 'b'.
    assert diff(['a', 'b'], ['b', 'a']) == ['-a', ' b', '+a']


def test_lines_compared_exactly():
    assert diff(['a ', 'A'], ['a', 'A']) == ['-a ', '+a', ' A']
    assert diff([''], ['', '']) == [' ', '+']


def test_lines_starting_with_prefix_characters():
    assert diff(['-x', '+y', ' z'], ['+y', ' z', '-x']) == ['--x', ' +y', '  z', '+-x']


def test_inputs_not_modified():
    a, b = ['1', '2', '3'], ['3', '2', '1']
    diff(a, b)
    assert a == ['1', '2', '3'] and b == ['3', '2', '1']


def test_returns_list_of_str():
    out = diff(['a'], ['b'])
    assert isinstance(out, list) and all(isinstance(e, str) for e in out)


def test_random_matches_rule():
    rng = random.Random(15)
    for _ in range(400):
        a = [rng.choice('abcd') for _ in range(rng.randrange(0, 12))]
        b = [rng.choice('abcd') for _ in range(rng.randrange(0, 12))]
        expected, _ = model(a, b)
        assert diff(a, b) == expected, (a, b)


def test_random_reconstructs_and_is_minimal():
    rng = random.Random(16)
    for _ in range(200):
        a = [rng.choice('xyz') for _ in range(rng.randrange(0, 20))]
        b = [rng.choice('xyz') for _ in range(rng.randrange(0, 20))]
        script = diff(a, b)
        assert side(script, ' -') == a
        assert side(script, ' +') == b
        assert sum(e[0] == ' ' for e in script) == model(a, b)[1]


def test_large_inputs():
    rng = random.Random(17)
    a = [f'line {rng.randrange(300)}' for _ in range(2000)]
    b = [x if rng.random() < 0.85 else f'new {rng.randrange(300)}' for x in a]
    b = b[:1000] + [f'extra {k}' for k in range(50)] + b[1000:]
    script = diff(a, b)
    assert side(script, ' -') == a
    assert side(script, ' +') == b
    assert sum(e[0] != ' ' for e in script) < 800
