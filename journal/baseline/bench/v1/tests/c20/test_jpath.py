import pytest

from jpath import PathError, get, parse

DATA = {
    'a': {'b': [10, 20, {'c': 'deep'}]},
    'users': [{'name': 'ann'}, {'name': 'bob'}],
    'x.y': {'z': 1},
    'q"k': 'quoted',
    'back\\slash': 'bs',
    '0': 'zero-key',
    'items': [1, 2, 3],
    'text': 'hello',
    'none': None,
    'tup': (5, 6),
}


@pytest.mark.parametrize('path, expected', [
    ('a.b[2].c', ['a', 'b', 2, 'c']),
    ('a["x.y"][-1].0', ['a', 'x.y', -1, '0']),
    ('[0].name', [0, 'name']),
    ('', []),
    ('a[0][1]', ['a', 0, 1]),
    ('["q\\"k"]', ['q"k']),
    ('["back\\\\slash"]', ['back\\slash']),
    ('with space.k-1', ['with space', 'k-1']),
])
def test_parse(path, expected):
    assert parse(path) == expected


SYNTAX_ERRORS = [
    'a..b', '.a', 'a.', 'a.[0]', 'a[]', 'a[1.5]', 'a[x]', 'a[0', 'a["x', 'a["x"', 'a]',
    'a["\\n"]', 'a[+1]', 'a[ 1]', 'a"b',
]


def test_parse_syntax_errors():
    for path in SYNTAX_ERRORS:
        with pytest.raises(PathError) as e:
            parse(path)
        assert e.value.path == path


def test_get_nested():
    assert get(DATA, 'a.b[2].c') == 'deep'
    assert get(DATA, 'a.b[0]') == 10
    assert get(DATA, 'users[1].name') == 'bob'


def test_negative_indices():
    assert get(DATA, 'users[-1].name') == 'bob'
    assert get(DATA, 'a.b[-3]') == 10
    assert get(DATA, 'tup[-1]') == 6


def test_quoted_keys():
    assert get(DATA, '["x.y"].z') == 1
    assert get(DATA, '["q\\"k"]') == 'quoted'
    assert get(DATA, '["back\\\\slash"]') == 'bs'


def test_empty_path_is_whole_object():
    assert get(DATA, '') is DATA


def test_digit_name_is_a_dict_key_not_an_index():
    assert get(DATA, '0') == 'zero-key'
    assert get(DATA, 'items.0', 'dflt') == 'dflt'
    with pytest.raises(PathError):
        get(DATA, 'items.0')


def test_root_list():
    assert get([{'name': 'r'}], '[0].name') == 'r'


def test_missing_raises_without_default():
    for path in ['nope', 'a.b[3]', 'a.b[-4]', 'users[0].age']:
        with pytest.raises(PathError) as e:
            get(DATA, path)
        assert e.value.path == path
        assert isinstance(e.value, LookupError)


def test_missing_returns_default():
    assert get(DATA, 'nope', 7) == 7
    assert get(DATA, 'a.b[99]', 'd') == 'd'
    assert get(DATA, 'nope', None) is None


def test_none_value_is_not_missing():
    assert get(DATA, 'none', 'dflt') is None


def test_type_mismatches_are_missing():
    assert get(DATA, 'a[0]', 'd') == 'd'           # index into a dict
    assert get(DATA, 'text[0]', 'd') == 'd'        # strings are not indexed
    assert get(DATA, 'a.b[0].c', 'd') == 'd'       # key into an int
    assert get(DATA, 'a.b.x', 'd') == 'd'          # key into a list
    assert get({1: 'int-key'}, '[1]', 'd') == 'd'  # index never looks up dict keys


def test_syntax_error_ignores_default():
    with pytest.raises(PathError):
        get(DATA, 'a..b', 'dflt')
    with pytest.raises(PathError):
        get(DATA, 'a[', None)
