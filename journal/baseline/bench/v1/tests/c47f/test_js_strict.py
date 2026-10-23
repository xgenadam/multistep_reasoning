import math

import pytest

from js import JSONError, dumps, loads, tokenize


def err(text, **kw):
    with pytest.raises(JSONError) as exc:
        loads(text, **kw)
    return (exc.value.line, exc.value.column)


# ---------------------------------------------------------------- repeated keys

def test_duplicate_default_and_last():
    text = '{"a": 1, "b": 2, "a": 3}'
    assert list(loads(text).items()) == [('a', 3), ('b', 2)]
    assert list(loads(text, duplicate_keys='last').items()) == [('a', 3), ('b', 2)]


def test_duplicate_first_keeps_first_value():
    assert list(loads('{"a": 1, "b": 2, "a": {"x": 1}}', duplicate_keys='first').items()) == [
        ('a', 1), ('b', 2)]


def test_duplicate_error_points_at_repeated_key():
    assert err('{"a": 1,\n  "b": 2, "a": 3}', duplicate_keys='error') == (2, 11)


def test_duplicate_error_before_value_is_parsed():
    assert err('{"a": 1, "a": @}', duplicate_keys='error') == (1, 10)


def test_duplicate_compared_after_decoding():
    assert err(r'{"a": 1, "a": 2}', duplicate_keys='error') == (1, 10)


def test_duplicate_separate_objects_are_independent():
    assert loads('[{"a": 1}, {"a": 2, "b": {"a": 3}}]', duplicate_keys='error') == [
        {'a': 1}, {'a': 2, 'b': {'a': 3}}]


def test_bad_duplicate_policy():
    with pytest.raises(ValueError) as exc:
        loads('{}', duplicate_keys='merge')
    assert not isinstance(exc.value, JSONError)


# ---------------------------------------------------------------- depth

def test_depth_limit_boundaries():
    assert loads('[[1]]', max_depth=2) == [[1]]
    assert loads('[{}, [2], {"k": 3}]', max_depth=2) == [{}, [2], {'k': 3}]
    assert loads('7', max_depth=1) == 7
    assert err('[[[1]]]', max_depth=2) == (1, 3)


def test_depth_error_at_opening_bracket_before_contents():
    assert err('{"a": [1,\n  {"b": @}]}', max_depth=2) == (2, 3)


def test_depth_unlimited_by_default():
    deep = '[' * 50 + ']' * 50
    value = loads(deep)
    for _ in range(49):
        value = value[0]
    assert value == []
    assert err(deep, max_depth=49) == (1, 50)


@pytest.mark.parametrize('bad', [0, -1])
def test_bad_max_depth(bad):
    with pytest.raises(ValueError):
        loads('[]', max_depth=bad)


# ---------------------------------------------------------------- NaN / infinities

def test_nan_tokens_when_allowed():
    toks = tokenize('[NaN, Infinity, -Infinity]', allow_nan=True)
    nums = [t for t in toks if t.kind == 'NUMBER']
    assert len(nums) == 3
    assert math.isnan(nums[0].value)
    assert nums[1].value == math.inf and nums[2].value == -math.inf
    assert (nums[2].line, nums[2].column) == (1, 17)


def test_loads_allow_nan():
    got = loads('{"x": NaN, "y": -Infinity}', allow_nan=True)
    assert math.isnan(got['x']) and got['y'] == -math.inf
    assert loads('[1, true, -2]', allow_nan=True) == [1, True, -2]


@pytest.mark.parametrize('text, pos', [
    ('[NaN]', (1, 2)), ('[Infinity]', (1, 2)), ('[1, -Infinity]', (1, 5)),
])
def test_nan_rejected_by_default(text, pos):
    assert err(text) == pos


@pytest.mark.parametrize('text, pos', [
    ('[nan]', (1, 2)), ('[NaNa]', (1, 2)), ('[-Inf]', (1, 2)), ('[-NaN]', (1, 2)),
    ('[Infinityy]', (1, 2)),
])
def test_nan_spelling_strict_when_allowed(text, pos):
    assert err(text, allow_nan=True) == pos


def test_dumps_allow_nan():
    assert dumps([math.nan, math.inf, -math.inf, 1.5], allow_nan=True) == \
        '[NaN,Infinity,-Infinity,1.5]'
    with pytest.raises(ValueError):
        dumps([math.inf])


def test_nan_round_trip():
    text = dumps({'a': [math.inf, -math.inf, math.nan]}, allow_nan=True, indent=2)
    back = loads(text, allow_nan=True)
    assert back['a'][:2] == [math.inf, -math.inf] and math.isnan(back['a'][2])
