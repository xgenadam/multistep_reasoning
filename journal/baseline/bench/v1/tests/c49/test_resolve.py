import pytest

from resolve import PackageIndex, Range, ResolutionError, Version, resolve


def V(s):
    return Version(s)


def as_text(result):
    return {name: str(v) for name, v in result.items()}


# ---------------------------------------------------------------- versions

def test_version_parse_compare_and_str():
    v = V('1.10.0')
    assert (v.major, v.minor, v.patch) == (1, 10, 0)
    assert str(v) == '1.10.0'
    assert V('10.0.0') > V('9.0.0') > V('1.10.0') > V('1.9.9')
    assert V('1.2.3') == V('1.2.3') and hash(V('1.2.3')) == hash(V('1.2.3'))
    assert sorted([V('0.1.0'), V('0.0.10'), V('0.0.9')]) == [V('0.0.9'), V('0.0.10'), V('0.1.0')]


@pytest.mark.parametrize('text', ['1.2', '1.2.3.4', '01.2.3', '1.02.3', '1.2.-3', 'a.b.c', '', '1..3'])
def test_bad_versions(text):
    with pytest.raises(ValueError):
        V(text)


@pytest.mark.parametrize('spec, inside, outside', [
    ('*', ['0.0.0', '99.1.2'], []),
    ('1.2.3', ['1.2.3'], ['1.2.4']),
    ('==1.2.3', ['1.2.3'], ['1.2.2']),
    ('>=1.0.0, <2.0.0, !=1.5.0', ['1.0.0', '1.9.9'], ['1.5.0', '2.0.0', '0.9.9']),
    ('>1.0.0,<=1.2.0', ['1.0.1', '1.2.0'], ['1.0.0', '1.2.1']),
    ('^1.2.3', ['1.2.3', '1.99.0'], ['1.2.2', '2.0.0']),
    ('^0.2.3', ['0.2.3', '0.2.9'], ['0.3.0', '0.2.2']),
    ('^0.0.3', ['0.0.3'], ['0.0.4', '0.0.2']),
    ('~1.2.3', ['1.2.3', '1.2.99'], ['1.3.0', '1.2.2']),
])
def test_range_contains(spec, inside, outside):
    r = Range(spec)
    for v in inside:
        assert V(v) in r and r.contains(V(v)), (spec, v)
    for v in outside:
        assert V(v) not in r, (spec, v)


def test_range_str_and_errors():
    assert str(Range(' >= 1.0.0 ,  < 2.0.0 ')) == '>=1.0.0,<2.0.0'
    for bad in ['', '  ', '>=1.0.0,', '=>1.0.0', '>>1.0.0', '^1.0', 'latest']:
        with pytest.raises(ValueError):
            Range(bad)


# ---------------------------------------------------------------- index

def test_index_versions_newest_first_and_requirements():
    idx = PackageIndex()
    idx.add('a', '1.9.0')
    idx.add('a', '1.10.0', {'b': '^1.0.0'})
    idx.add('a', '0.5.0')
    assert idx.versions('a') == [V('1.10.0'), V('1.9.0'), V('0.5.0')]
    assert idx.versions('zzz') == []
    reqs = idx.requirements('a', V('1.10.0'))
    assert list(reqs) == ['b'] and isinstance(reqs['b'], Range) and V('1.4.0') in reqs['b']
    assert idx.requirements('a', V('1.9.0')) == {}
    with pytest.raises(KeyError):
        idx.requirements('a', V('3.0.0'))


def test_index_rejects_duplicates_and_bad_input():
    idx = PackageIndex()
    idx.add('a', '1.0.0')
    with pytest.raises(ValueError):
        idx.add('a', '1.0.0', {'b': '*'})
    with pytest.raises(ValueError):
        idx.add('a', '1.0', {})
    with pytest.raises(ValueError):
        idx.add('a', '2.0.0', {'b': '>>1'})


# ---------------------------------------------------------------- solving

def test_simple_newest_versions():
    idx = PackageIndex.from_dict({
        'app': {'1.0.0': {'lib': '^1.0.0'}, '2.0.0': {'lib': '^1.2.0', 'util': '*'}},
        'lib': {'1.0.0': {}, '1.3.0': {}, '2.0.0': {}},
        'util': {'0.1.0': {}, '0.2.0': {}},
    })
    assert as_text(resolve(idx, {'app': '*'})) == {'app': '2.0.0', 'lib': '1.3.0', 'util': '0.2.0'}


def test_result_is_versions_and_empty_root():
    idx = PackageIndex.from_dict({'a': {'1.0.0': {}}})
    result = resolve(idx, {'a': '*'})
    assert result == {'a': V('1.0.0')}
    assert resolve(idx, {}) == {}


def test_newer_dependency_constraint_respected():
    idx = PackageIndex.from_dict({
        'a': {'2.0.0': {'b': '<2.0.0'}, '1.0.0': {'b': '>=2.0.0'}},
        'b': {'1.0.0': {}, '2.0.0': {}},
    })
    assert as_text(resolve(idx, {'a': '*'})) == {'a': '2.0.0', 'b': '1.0.0'}


def test_backtracks_to_older_version():
    idx = PackageIndex.from_dict({
        'a': {'1.0.0': {}, '2.0.0': {}},
        'b': {'1.0.0': {'a': '>=3.0.0'}, '2.0.0': {'a': '<2.0.0'}},
    })
    assert as_text(resolve(idx, {'a': '*', 'b': '*'})) == {'a': '1.0.0', 'b': '2.0.0'}


def test_candidate_rejected_when_dependency_already_selected_conflicts():
    # order: a, c, then b (added by a). c 2.0.0 is selected before b is visited;
    # b 2.0.0 needs c 1.x, so b falls back to 1.0.0.
    idx = PackageIndex.from_dict({
        'a': {'1.0.0': {'b': '*'}},
        'b': {'1.0.0': {}, '2.0.0': {'c': '^1.0.0'}},
        'c': {'1.0.0': {}, '2.0.0': {}},
    })
    assert as_text(resolve(idx, {'a': '*', 'c': '*'})) == {'a': '1.0.0', 'c': '2.0.0', 'b': '1.0.0'}


def test_result_follows_search_order_not_global_optimum():
    # The first complete assignment found depth-first wins.
    idx = PackageIndex.from_dict({
        'a': {'1.0.0': {'x': '1.0.0'}, '2.0.0': {'x': '2.0.0'}},
        'x': {'1.0.0': {}, '2.0.0': {'y': '>=5.0.0'}},
        'y': {'1.0.0': {}},
    })
    assert as_text(resolve(idx, {'a': '*'})) == {'a': '1.0.0', 'x': '1.0.0'}


def test_selection_order_of_result():
    idx = PackageIndex.from_dict({
        'b': {'1.0.0': {'z': '*', 'c': '*'}},
        'a': {'1.0.0': {}},
        'c': {'1.0.0': {}},
        'z': {'1.0.0': {}},
    })
    assert list(resolve(idx, {'b': '*', 'a': '*'})) == ['a', 'b', 'c', 'z']


def test_undo_removes_added_names():
    # a 2.0.0 adds 'bad' (unresolvable); after backtracking, a 1.0.0 must not need it.
    idx = PackageIndex.from_dict({
        'a': {'2.0.0': {'bad': '*'}, '1.0.0': {}},
        'bad': {},
    })
    assert as_text(resolve(idx, {'a': '*'})) == {'a': '1.0.0'}


def test_bad_root_spec():
    idx = PackageIndex.from_dict({'a': {'1.0.0': {}}})
    with pytest.raises(ValueError):
        resolve(idx, {'a': '>=x'})


# ---------------------------------------------------------------- explanations

def failure(idx, root):
    with pytest.raises(ResolutionError) as exc:
        resolve(idx, root)
    assert isinstance(exc.value, Exception)
    assert str(exc.value) == exc.value.explanation
    return exc.value


def test_explanation_prompt_example():
    idx = PackageIndex.from_dict({'app': {'1.0.0': {'lib': '<2.0.0'}}, 'lib': {'2.0.0': {}}})
    e = failure(idx, {'app': '*', 'lib': '>=2.0.0'})
    assert e.package == 'lib'
    assert e.explanation == ('cannot resolve lib\n'
                             '  <root> requires lib >=2.0.0\n'
                             '  app 1.0.0 requires lib <2.0.0\n'
                             '  lib 2.0.0 is excluded by the constraints')


def test_explanation_unknown_package():
    idx = PackageIndex.from_dict({'app': {'1.0.0': {'ghost': '^1.0.0'}}})
    e = failure(idx, {'app': '*'})
    assert e.package == 'ghost'
    assert e.explanation == ('cannot resolve ghost\n'
                             '  app 1.0.0 requires ghost ^1.0.0\n'
                             '  no versions of ghost are known')


def test_explanation_dependency_conflict_lines():
    idx = PackageIndex.from_dict({
        'a': {'1.0.0': {}, '2.0.0': {}},
        'b': {'1.0.0': {'a': '>=3.0.0', 'c': '*'}, '2.0.0': {'a': '<1.0.0'},
              '3.0.0': {}},
    })
    e = failure(idx, {'a': '>=2.0.0', 'b': '<3.0.0'})
    assert e.package == 'b'
    assert e.explanation == ('cannot resolve b\n'
                             '  <root> requires b <3.0.0\n'
                             '  b 3.0.0 is excluded by the constraints\n'
                             '  b 2.0.0 requires a <1.0.0, but a 2.0.0 is selected\n'
                             '  b 1.0.0 requires a >=3.0.0, but a 2.0.0 is selected')


def test_explanation_is_first_dead_end():
    # First dead end: with a 2.0.0 selected, x has nothing acceptable. After
    # backtracking, a 1.0.0 leads to a dead end on y. The first one is reported.
    idx = PackageIndex.from_dict({
        'a': {'2.0.0': {'x': '>=2.0.0'}, '1.0.0': {'y': '*'}},
        'x': {'1.0.0': {}},
        'y': {},
    })
    e = failure(idx, {'a': '*'})
    assert e.package == 'x'
    assert e.explanation.splitlines()[:2] == ['cannot resolve x',
                                              '  a 2.0.0 requires x >=2.0.0']


def test_explanation_constraints_in_selection_order():
    idx = PackageIndex.from_dict({
        'p': {'1.0.0': {'z': '>=1.0.0'}},
        'q': {'1.0.0': {'z': '<1.0.0'}},
        'z': {'1.0.0': {}, '0.5.0': {}},
    })
    e = failure(idx, {'q': '*', 'p': '*', 'z': '~1.0.0'})
    assert e.explanation == ('cannot resolve z\n'
                             '  <root> requires z ~1.0.0\n'
                             '  p 1.0.0 requires z >=1.0.0\n'
                             '  q 1.0.0 requires z <1.0.0\n'
                             '  z 1.0.0 is excluded by the constraints\n'
                             '  z 0.5.0 is excluded by the constraints')
