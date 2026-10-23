import random
import re

import pytest

import rx
from rx import (Alt, AnyChar, CharClass, Concat, Empty, Group, Literal, Optional, Plus,
                RegexError, Star, compile, findall, match, parse, search)


# ---------------------------------------------------------------- parse

def test_parse_concat_and_star():
    assert parse('ab*') == Concat((Literal('a'), Star(Literal('b'))))


def test_parse_single_and_empty():
    assert parse('a') == Literal('a')
    assert parse('') == Empty()
    assert parse('()') == Group(Empty())


def test_parse_alt_is_flat_and_binds_loosest():
    assert parse('ab|c|') == Alt((Concat((Literal('a'), Literal('b'))), Literal('c'), Empty()))
    assert parse('(a|)') == Group(Alt((Literal('a'), Empty())))


def test_parse_quantifiers_and_group():
    assert parse('(ab)+c?.') == Concat((Plus(Group(Concat((Literal('a'), Literal('b'))))),
                                        Optional(Literal('c')), AnyChar()))


def test_parse_classes():
    assert parse('[a-cx]') == CharClass((('a', 'c'), ('x', 'x')), False)
    assert parse('[^0-9]') == CharClass((('0', '9'),), True)
    assert parse('[-a-]') == CharClass((('-', '-'), ('a', 'a'), ('-', '-')), False)
    assert parse('[.*(|]') == CharClass(tuple((c, c) for c in '.*(|'), False)
    assert parse(r'[\]\\]') == CharClass(((']', ']'), ('\\', '\\')), False)


def test_parse_escapes_and_literal_specials():
    assert parse(r'\.\*') == Concat((Literal('.'), Literal('*')))
    assert parse('a]b c') == Concat(tuple(Literal(c) for c in 'a]b c'))


@pytest.mark.parametrize('pattern, position', [
    ('*a', 0), ('(?a)', 1), ('a**', 2), ('ab)c', 2), ('(a(b)', 0), ('((a', 1),
    ('x[ab', 1), ('[]', 0), ('a[z-a]', 2), ('ab\\', 2),
])
def test_parse_errors(pattern, position):
    with pytest.raises(RegexError) as exc:
        parse(pattern)
    assert exc.value.position == position
    assert isinstance(exc.value, ValueError)
    assert exc.value.message


def test_compile_rejects_bad_pattern_and_accepts_ast():
    with pytest.raises(RegexError):
        compile('(a')
    assert compile(Concat((Literal('h'), Star(Literal('i'))))).match('hiii')


# ---------------------------------------------------------------- match

@pytest.mark.parametrize('pattern, text, expected', [
    ('abc', 'abcd', False), ('a+', '', False), ('colou?r', 'color', True),
    ('(ab|cd)*e', 'abcdabe', True), ('a.c', 'a\nc', False), ('[^x]', '\n', True),
    ('[a-c]+', 'abd', False), (r'a\+b', 'a+b', True), ('a|', '', True),
])
def test_match_table(pattern, text, expected):
    assert match(pattern, text) is expected


def test_nested_quantifiers_with_empty_body():
    assert match('(a*)*b', 'aab')
    assert match('(a?)+', '')
    assert not match('(a|b?)+c', 'abba')


# ---------------------------------------------------------------- search / findall

def test_search_leftmost_then_longest():
    assert search('a|ab|abc', 'xxabcab') == (2, 5)
    assert search('b+', 'abbbcbb') == (1, 4)
    assert search('z', 'abc') is None


def test_search_empty_match_and_start():
    assert search('a*', 'bbb') == (0, 0)
    assert search('a*', 'baa', 1) == (1, 3)
    assert search('a', 'aba', 1) == (2, 3)
    assert search('x*', 'ab', 2) == (2, 2)


def test_search_longest_not_first_alternative():
    assert search('(a|ab)(c|bcd)', 'abcd') == (0, 4)


def test_findall_rules():
    assert findall('a*', 'baa') == ['', 'aa', '']
    assert findall('[0-9]+', 'a1b22c333') == ['1', '22', '333']
    assert findall('ab|a', 'abaab') == ['ab', 'a', 'ab']
    assert findall('x', '') == []
    assert findall('', 'ab') == ['', '', '']


def test_nfa_methods_reusable():
    nfa = compile('[a-z]+')
    assert nfa.search('12ab3') == (2, 4)
    assert nfa.findall('ab cd') == ['ab', 'cd']
    assert nfa.match('abc') and not nfa.match('ab1')


# ---------------------------------------------------------------- against Python's re

ALPHABET = 'ab'


def random_pattern(rng, depth=0):
    roll = rng.random()
    if depth > 2 or roll < 0.35:
        atom = rng.choice(['a', 'b', '.', '[ab]', '[^a]', '[a-b]'])
    elif roll < 0.55:
        atom = '(' + random_pattern(rng, depth + 1) + ')'
    elif roll < 0.75:
        atom = random_pattern(rng, depth + 1) + random_pattern(rng, depth + 1)
        return atom
    else:
        return random_pattern(rng, depth + 1) + '|' + random_pattern(rng, depth + 1)
    if rng.random() < 0.4:
        atom += rng.choice('*+?')
    return atom


def brute_search(pattern, text):
    for i in range(len(text) + 1):
        for j in range(len(text), i - 1, -1):
            if re.fullmatch(pattern, text[i:j]):
                return (i, j)
    return None


def test_random_patterns_match_like_re():
    rng = random.Random(46)
    for _ in range(300):
        pattern = random_pattern(rng)
        nfa = compile(pattern)
        for _ in range(6):
            text = ''.join(rng.choice(ALPHABET + 'c') for _ in range(rng.randrange(6)))
            assert nfa.match(text) == bool(re.fullmatch(pattern, text)), (pattern, text)


def test_random_patterns_search_leftmost_longest():
    rng = random.Random(4646)
    for _ in range(200):
        pattern = random_pattern(rng)
        nfa = compile(pattern)
        for _ in range(4):
            text = ''.join(rng.choice(ALPHABET + 'c') for _ in range(rng.randrange(7)))
            assert nfa.search(text) == brute_search(pattern, text), (pattern, text)


def test_package_exports():
    for name in ['parse', 'compile', 'match', 'search', 'findall', 'RegexError', 'Empty',
                 'Literal', 'AnyChar', 'CharClass', 'Concat', 'Alt', 'Star', 'Plus',
                 'Optional', 'Group']:
        assert hasattr(rx, name), name
