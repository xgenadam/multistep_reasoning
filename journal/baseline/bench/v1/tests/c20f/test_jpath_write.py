import copy

import pytest

import jpath
from jpath import WILDCARD, PathError, delete, get, parse


def data():
    return {
        'users': [{'name': 'ann', 'tags': ['x', 'y']}, {'name': 'bob'}, {'name': 'cy', 'tags': []}],
        'groups': {'g1': {'size': 3}, 'g2': {'size': 5}, 'g3': {}},
        'text': 'hi',
        'tup': (1, {'k': 'v'}),
    }


def test_parse_wildcard():
    segs = parse('users[*].name')
    assert segs[0] == 'users' and segs[2] == 'name'
    assert segs[1] is WILDCARD
    assert parse('["*"]') == ['*']


def test_wildcard_over_list():
    assert get(data(), 'users[*].name') == ['ann', 'bob', 'cy']


def test_wildcard_over_mapping_values_in_order():
    assert get(data(), 'groups[*].size') == [3, 5]


def test_nested_wildcards_and_skipped_branches():
    assert get(data(), 'users[*].tags[*]') == ['x', 'y']
    assert get(data(), 'users[*]["tags"][0]') == ['x']


def test_wildcard_no_matches_returns_empty_list_and_ignores_default():
    assert get(data(), 'users[*].age') == []
    assert get(data(), 'text[*]', 'dflt') == []
    assert get(data(), 'missing[*]') == []


def test_wildcard_syntax_errors_still_raise():
    with pytest.raises(PathError):
        get(data(), 'users[*', [])


def test_set_replaces_and_adds_keys():
    d = data()
    assert jpath.set(d, 'users[0].name', 'ANN') is None
    jpath.set(d, 'groups.g3.size', 0)
    jpath.set(d, 'new', 1)
    assert d['users'][0]['name'] == 'ANN'
    assert d['groups']['g3'] == {'size': 0}
    assert d['new'] == 1


def test_set_negative_index_and_append():
    d = data()
    jpath.set(d, 'users[-1].name', 'CY')
    assert d['users'][2]['name'] == 'CY'
    jpath.set(d, 'users[0].tags[2]', 'z')
    assert d['users'][0]['tags'] == ['x', 'y', 'z']


def test_set_creates_containers_by_next_segment():
    d = {}
    jpath.set(d, 'a[0].b', 1)
    assert d == {'a': [{'b': 1}]}
    d = {}
    jpath.set(d, 'x.y[0][0]', 'v')
    assert d == {'x': {'y': [['v']]}}
    d = {'list': []}
    jpath.set(d, 'list[0].k', 2)
    assert d == {'list': [{'k': 2}]}


def test_set_through_a_tuple_into_a_dict():
    d = data()
    jpath.set(d, 'tup[1].k', 'w')
    assert d['tup'][1] == {'k': 'w'}


SET_ERRORS = [
    '', 'users[*].name', 'users.name', 'groups[0]', 'text.x', 'text[0]', 'tup[0]',
    'users[5]', 'users[-4].name', 'new[1]', 'new.deep[0][1]', 'users[3].a[2]',
]


def test_set_errors_leave_obj_unchanged():
    for path in SET_ERRORS:
        d = data()
        before = copy.deepcopy(d)
        with pytest.raises(PathError) as e:
            jpath.set(d, path, 'v')
        assert e.value.path == path
        assert d == before, path


def test_delete_returns_removed_value():
    d = data()
    assert delete(d, 'users[1]') == {'name': 'bob'}
    assert [u['name'] for u in d['users']] == ['ann', 'cy']
    assert delete(d, 'groups.g1') == {'size': 3}
    assert list(d['groups']) == ['g2', 'g3']
    assert delete(d, 'users[0].tags[-1]') == 'y'
    assert d['users'][0]['tags'] == ['x']


def test_delete_errors():
    for path in ['', 'nope', 'users[9]', 'users[*]', 'tup[0]', 'text[0]', 'users.0']:
        d = data()
        before = copy.deepcopy(d)
        with pytest.raises(PathError):
            delete(d, path)
        assert d == before, path
