import random
import re

import pytest

from justify import justify


def test_classic_example():
    text = 'This is an example of text justification.'
    assert justify(text, 16) == [
        'This    is    an',
        'example  of text',
        'justification.',
    ]


def test_extra_spaces_go_left_first():
    assert justify('a b c d', 9) == ['a b c d']  # one line: it is the last
    assert justify('a b c d xy', 9) == ['a  b  c d', 'xy']
    assert justify('a b c d e', 6) == ['a  b c', 'd e']


def test_exact_fit_line():
    assert justify('abc def ghi', 7) == ['abc def', 'ghi']


def test_single_word_line_is_padded():
    assert justify('longword a b', 9) == ['longword ', 'a b']


def test_last_line_left_aligned_without_padding():
    lines = justify('aa bb cc dd', 8)
    assert lines == ['aa bb cc', 'dd']
    lines = justify('one two three four five', 14)
    assert lines == ['one  two three', 'four five']


def test_single_line_text_is_the_last_line():
    assert justify('short text', 40) == ['short text']
    assert justify('word', 10) == ['word']


def test_input_whitespace_is_ignored():
    assert justify('  a\n\nb\t\tc  ', 4) == ['a  b', 'c']


def test_no_words():
    assert justify('', 10) == []
    assert justify(' \n\t ', 10) == []


def test_overlong_word_on_its_own_line():
    assert justify('a bb supercalifragilistic cc d', 6) == [
        'a   bb',
        'supercalifragilistic',
        'cc d',
    ]


def test_overlong_word_first_and_last():
    assert justify('abcdefgh x y', 4) == ['abcdefgh', 'x y']
    assert justify('x y abcdefgh', 4) == ['x  y', 'abcdefgh']


def test_overlong_word_alone():
    assert justify('abcdefgh', 3) == ['abcdefgh']


def test_width_one():
    assert justify('a b c', 1) == ['a', 'b', 'c']


def test_width_below_one_raises():
    for width in (0, -5):
        with pytest.raises(ValueError):
            justify('a b', width)


def test_random_properties():
    rng = random.Random(11)
    for _ in range(300):
        width = rng.randrange(1, 25)
        words = [''.join(rng.choice('abcxyz') for _ in range(rng.randrange(1, 9)))
                 for _ in range(rng.randrange(1, 25))]
        lines = justify(' '.join(words), width)
        assert ' '.join(lines).split() == words
        for line in lines[:-1]:
            ws = line.split()
            if len(ws) == 1:
                assert line == (ws[0] if len(ws[0]) > width else ws[0].ljust(width))
            else:
                assert len(line) == width and line[0] != ' ' and line[-1] != ' '
                gaps = [len(g) for g in re.findall(r' +', line)]
                assert gaps == sorted(gaps, reverse=True)
                assert max(gaps) - min(gaps) <= 1
        assert lines[-1] == ' '.join(lines[-1].split())


def test_greedy_fill_is_maximal():
    rng = random.Random(12)
    for _ in range(300):
        width = rng.randrange(3, 20)
        words = [''.join(rng.choice('ab') for _ in range(rng.randrange(1, 6)))
                 for _ in range(rng.randrange(2, 20))]
        lines = justify(' '.join(words), width)
        for line, nxt in zip(lines, lines[1:]):
            first_next = nxt.split()[0]
            used = len(' '.join(line.split()))
            if len(line.split()[0]) <= width and len(first_next) <= width:
                assert used + 1 + len(first_next) > width
