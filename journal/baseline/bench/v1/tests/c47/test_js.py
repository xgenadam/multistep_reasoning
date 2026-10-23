import math
import random

import pytest

from js import JSONError, Token, dumps, loads, tokenize


def err(text):
    with pytest.raises(JSONError) as exc:
        loads(text)
    assert isinstance(exc.value, ValueError)
    return (exc.value.line, exc.value.column)


# ---------------------------------------------------------------- scanner

def test_tokenize_kinds_values_positions():
    toks = tokenize('{"a": [1, 2.5, true]}\n  null')
    assert [t.kind for t in toks] == ['{', 'STRING', ':', '[', 'NUMBER', ',', 'NUMBER', ',',
                                      'TRUE', ']', '}', 'NULL', 'EOF']
    assert toks[1] == Token('STRING', 'a', 1, 2)
    assert toks[6].value == 2.5 and toks[6].column == 11
    assert (toks[11].line, toks[11].column, toks[11].value) == (2, 3, None)
    assert (toks[12].line, toks[12].column) == (2, 7)
    assert toks[0].value is None


# ---------------------------------------------------------------- values

def test_loads_basic_structure():
    assert loads(' {"a": [1, -2, 3.0e1, false, null], "b": {"c": "d"}} ') == {
        'a': [1, -2, 30.0, False, None], 'b': {'c': 'd'}}
    assert loads('[]') == [] and loads('{}') == {}


def test_numbers_int_float_and_edges():
    assert loads('12345678901234567890') == 12345678901234567890
    assert type(loads('10')) is int and type(loads('1.0')) is float
    assert type(loads('1E2')) is float and loads('1E2') == 100.0
    assert loads('-0') == 0 and type(loads('-0')) is int
    assert math.copysign(1, loads('-0.0')) == -1
    assert loads('1e400') == math.inf
    assert loads('2.5e-3') == 0.0025 and loads('1e+2') == 100.0


@pytest.mark.parametrize('text, pos', [
    ('01', (1, 1)), ('[-]', (1, 2)), ('[1.]', (1, 2)), ('[0, 1.5.2]', (1, 5)),
    ('.5', (1, 1)),
])
def test_invalid_numbers(text, pos):
    assert err(text) == pos


def test_string_escapes_and_unicode():
    assert loads(r'"a\"b\\c\/d\b\f\n\r\t"') == 'a"b\\c/d\b\f\n\r\t'
    assert loads(r'"éé"') == 'éé'
    assert loads('"é😀"') == 'é😀'


def test_surrogate_pair_decodes_to_one_character():
    s = loads(r'"x😀y"')
    assert s == 'x😀y' and len(s) == 3


@pytest.mark.parametrize('text, pos', [
    (r'["abc', (1, 2)),
    (r'"ab\x"', (1, 4)),
    (r'"\u12g4"', (1, 2)),
    (r'["\ud83d"]', (1, 3)),
    (r'"\ud83dA"', (1, 2)),
    (r'"a\ude00"', (1, 3)),
    ('[\n  "line\nbreak"]', (2, 8)),
])
def test_string_errors(text, pos):
    assert err(text) == pos


@pytest.mark.parametrize('text, pos', [
    ('trueX', (1, 1)), ('[nul]', (1, 2)), ("{'a': 1}", (1, 2)),
])
def test_literal_and_character_errors(text, pos):
    assert err(text) == pos


# ---------------------------------------------------------------- structure errors

@pytest.mark.parametrize('text, pos', [
    ('[1,]', (1, 4)),
    ('{"a" 1}', (1, 6)),
    ('{1: 2}', (1, 2)),
    ('[1,', (1, 4)),
    ('', (1, 1)),
    ('{"a": 1}\n  x', (2, 3)),
    ('{\n"a":\n}', (3, 1)),
])
def test_structure_errors(text, pos):
    assert err(text) == pos


def test_first_problem_in_reading_order_wins():
    assert err('[1,] @') == (1, 4)
    assert err('[1 "unterminated') == (1, 4)


def test_error_str_format():
    with pytest.raises(JSONError) as exc:
        loads('[1,\n 2,,]')
    e = exc.value
    assert (e.line, e.column) == (2, 4)
    assert str(e) == f'{e.msg} at line 2 column 4'


def test_crlf_counts_one_line():
    assert err('[1,\r\n\r\n  ]') == (3, 3)


def test_duplicate_key_last_wins_first_position():
    assert list(loads('{"a": 1, "b": 2, "a": 3}').items()) == [('a', 3), ('b', 2)]


# ---------------------------------------------------------------- dumps

def test_dumps_compact():
    assert dumps({'a': [1, 2.5, None, True, False], 'b': 'x'}) == \
        '{"a":[1,2.5,null,true,false],"b":"x"}'
    assert dumps((1, (2,))) == '[1,[2]]'


def test_dumps_indent_layout():
    assert dumps({'a': [1, 2], 'b': {}}, indent=2) == \
        '{\n  "a": [\n    1,\n    2\n  ],\n  "b": {}\n}'
    assert dumps([[], {'k': []}], indent=0) == '[\n[],\n{\n"k": []\n}\n]'
    assert dumps('s', indent=4) == '"s"'


def test_dumps_sort_keys():
    assert dumps({'b': 1, 'a': {'d': 1, 'c': 2}}, sort_keys=True) == '{"a":{"c":2,"d":1},"b":1}'
    assert dumps({'b': 1, 'a': 2}) == '{"b":1,"a":2}'


def test_dumps_string_escapes():
    assert dumps('q"\\\n\t\x01\x1f é') == '"q\\"\\\\\\n\\t\\u0001\\u001f é"'
    assert dumps('é😀') == '"é😀"'
    assert dumps('é😀\x7f', ensure_ascii=True) == '"\\u00e9\\ud83d\\ude00\x7f"'


def test_dumps_floats():
    assert dumps(1.0) == '1.0'
    assert dumps(1e16) == repr(1e16)
    assert dumps(-0.0) == '-0.0'
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            dumps([bad])


def test_dumps_type_errors():
    with pytest.raises(TypeError):
        dumps({1: 'a'})
    with pytest.raises(TypeError):
        dumps({'a': {1, 2}})
    with pytest.raises(TypeError):
        dumps(object())
    with pytest.raises(ValueError):
        dumps([1], indent=-1)


def test_dumps_cycles_and_shared_children():
    a = [1]
    a.append(a)
    with pytest.raises(ValueError):
        dumps(a)
    d = {}
    d['self'] = [d]
    with pytest.raises(ValueError):
        dumps(d)
    x = [1]
    assert dumps([x, x]) == '[[1],[1]]'


# ---------------------------------------------------------------- round trips

def random_value(rng, depth=0):
    roll = rng.random()
    if depth > 3 or roll < 0.5:
        kind = rng.randrange(6)
        if kind == 0:
            return rng.randrange(-10**20, 10**20)
        if kind == 1:
            return rng.uniform(-1e6, 1e6) * 10 ** rng.randrange(-20, 20)
        if kind == 2:
            return ''.join(rng.choice('ab"\\\n\t\x00é😀/ ') for _ in range(rng.randrange(6)))
        return [None, True, False][kind - 3]
    if roll < 0.75:
        return [random_value(rng, depth + 1) for _ in range(rng.randrange(4))]
    return {''.join(rng.choice('xyzé😀"') for _ in range(3)):
            random_value(rng, depth + 1) for _ in range(rng.randrange(4))}


@pytest.mark.parametrize('options', [{}, {'indent': 2, 'sort_keys': True, 'ensure_ascii': True}])
def test_round_trip_random(options):
    rng = random.Random(47)
    for _ in range(300):
        value = random_value(rng)
        assert loads(dumps(value, **options)) == value
