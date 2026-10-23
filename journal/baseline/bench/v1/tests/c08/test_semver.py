import random

import pytest

from semver import Version, satisfies

V = Version.parse


def test_parse_parts():
    v = V('1.2.3-rc.1+exp.7')
    assert (v.major, v.minor, v.patch) == (1, 2, 3)
    assert v.prerelease == ('rc', '1')
    assert v.build == ('exp', '7')
    w = V('10.20.30')
    assert (w.major, w.minor, w.patch, w.prerelease, w.build) == (10, 20, 30, (), ())


def test_str_round_trips():
    for text in ['0.0.0', '1.2.3', '1.0.0-alpha', '1.0.0-0.3.7', '1.0.0-x.7.z.92',
                 '1.0.0-x-y-z.--', '1.0.0+20130313144700', '1.0.0-beta+exp.sha.5114f85',
                 '1.0.0+21AF26D3----117B344092BD', '2.0.0+001']:
        assert str(V(text)) == text


def test_parse_rejects_invalid():
    for text in ['1.2', '1', '1.2.3.4', 'v1.2.3', ' 1.2.3', '1.2.3 ', '01.2.3', '1.02.3',
                 '1.2.03', '1.2.3-', '1.2.3+', '1.2.3-a..b', '1.2.3-01', '1.2.3-a_b',
                 '1.2.3+a..b', '-1.2.3', '1.2.x', '']:
        with pytest.raises(ValueError):
            V(text)


def test_spec_precedence_chain():
    chain = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta',
             '1.0.0-beta.2', '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0']
    versions = [V(t) for t in chain]
    for a, b in zip(versions, versions[1:]):
        assert a < b and b > a and a <= b and a != b


def test_numeric_parts_compare_numerically():
    assert V('1.10.0') > V('1.9.0')
    assert V('2.0.0') > V('1.99.99')
    assert V('1.0.10') > V('1.0.9')


def test_prerelease_identifier_rules():
    assert V('1.0.0-2') < V('1.0.0-10')
    assert V('1.0.0-10') < V('1.0.0-a')       # numeric lower than alphanumeric
    assert V('1.0.0-B') < V('1.0.0-a')        # ASCII order
    assert V('1.0.0-a.b') > V('1.0.0-a')      # longer wins when prefix equal
    assert V('1.0.0-rc.1') < V('1.0.0')


def test_build_ignored_for_equality_and_hash():
    a, b = V('1.0.0+a'), V('1.0.0+b')
    assert a == b and not a < b and not a > b
    assert hash(a) == hash(b)
    assert len({a, b, V('1.0.0')}) == 1
    assert V('1.0.0-rc.1+x') < V('1.0.0+x')


def test_comparison_with_other_types():
    assert (V('1.0.0') == '1.0.0') is False
    assert V('1.0.0') != '1.0.0'
    with pytest.raises(TypeError):
        V('1.0.0') < '2.0.0'


def test_sorting_random_shuffle():
    ordered = ['0.0.1', '0.1.0-rc', '0.1.0', '1.0.0-0', '1.0.0-1', '1.0.0-1.a', '1.0.0-a',
               '1.0.0', '1.0.1', '1.1.0', '2.0.0-alpha', '2.0.0']
    rng = random.Random(8)
    for _ in range(20):
        shuffled = ordered[:]
        rng.shuffle(shuffled)
        assert [str(v) for v in sorted(V(t) for t in shuffled)] == ordered


def test_bump():
    v = V('1.2.3-rc.1+build.5')
    assert str(v.bump('major')) == '2.0.0'
    assert str(v.bump('minor')) == '1.3.0'
    assert str(v.bump('patch')) == '1.2.4'
    assert str(V('0.9.9').bump('minor')) == '0.10.0'
    assert str(v) == '1.2.3-rc.1+build.5'  # unchanged
    with pytest.raises(ValueError):
        v.bump('build')


def test_satisfies_comparators():
    assert satisfies('1.5.0', '>=1.0 <2.0')
    assert not satisfies('2.0.0', '>=1.0 <2.0')
    assert satisfies('1.0.0', '>=1.0.0')
    assert not satisfies('1.0.0', '>1.0.0')
    assert satisfies('1.0.0', '<=1.0.0')
    assert satisfies('1.2.3', '=1.2.3') and satisfies('1.2.3', '1.2.3')
    assert not satisfies('1.2.4', '1.2.3')
    assert satisfies(V('3.1.4'), '>3 <=3.2')


def test_caret():
    assert satisfies('1.2.3', '^1.2.3') and satisfies('1.9.9', '^1.2.3')
    assert not satisfies('2.0.0', '^1.2.3') and not satisfies('1.2.2', '^1.2.3')
    assert satisfies('0.2.9', '^0.2.3') and not satisfies('0.3.0', '^0.2.3')
    assert satisfies('0.0.3', '^0.0.3') and not satisfies('0.0.4', '^0.0.3')
    assert satisfies('1.2.0', '^1.2') and satisfies('1.99.0', '^1.2')
    assert not satisfies('1.1.9', '^1.2')


def test_tilde():
    assert satisfies('1.2.3', '~1.2.3') and satisfies('1.2.99', '~1.2.3')
    assert not satisfies('1.3.0', '~1.2.3')
    assert satisfies('1.2.0', '~1.2') and not satisfies('1.3.0', '~1.2')
    assert satisfies('1.9.0', '~1') and not satisfies('2.0.0', '~1')


def test_prerelease_uses_plain_precedence():
    assert satisfies('2.0.0-rc.1', '^1.2.0')
    assert not satisfies('1.2.3-beta', '>=1.2.3')
    assert satisfies('1.2.3-beta', '<1.2.3')


def test_build_metadata_in_ranges():
    assert satisfies('1.2.3+build.9', '=1.2.3')
    assert satisfies('1.2.3', '^1.2.3+meta')


def test_satisfies_errors():
    for spec in ['', '   ', '>=', '^', '>=1.2.x', '~v1', '>>1.0.0', '1.2-rc', '=>1.0.0']:
        with pytest.raises(ValueError):
            satisfies('1.0.0', spec)
    with pytest.raises(ValueError):
        satisfies('1.0', '>=1.0.0')
