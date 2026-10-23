import pytest

from mdtable import format_table


def test_example_from_the_spec():
    out = format_table([['apple', 3], ['kiwi', 12]], ['fruit', 'qty'], ['left', 'right'])
    assert out == ('| fruit | qty |\n'
                   '| :---- | --: |\n'
                   '| apple |   3 |\n'
                   '| kiwi  |  12 |')


def test_default_is_left_aligned():
    out = format_table([['a', 'bb']], ['x', 'yyyy'])
    assert out.splitlines() == ['| x   | yyyy |',
                                '| :-- | :--- |',
                                '| a   | bb   |']


def test_center_padding_smaller_half_left():
    out = format_table([['ab'], ['abc'], ['a']], ['title'], ['center'])
    assert out.splitlines() == ['| title |',
                                '| :---: |',
                                '|  ab   |',
                                '|  abc  |',
                                '|   a   |']


def test_center_odd_gap_in_header():
    out = format_table([['abcdef']], ['ab'], ['center'])
    assert out.splitlines()[0] == '|   ab   |'


def test_right_aligned_header_padded_left():
    out = format_table([[12345]], ['n'], ['right'])
    assert out.splitlines() == ['|     n |', '| ----: |', '| 12345 |']


def test_minimum_width_three():
    out = format_table([['a', 'b', 'c']], ['x', 'y', 'z'], ['left', 'right', 'center'])
    assert out.splitlines() == ['| x   |   y |  z  |',
                                '| :-- | --: | :-: |',
                                '| a   |   b |  c  |']


def test_no_trailing_newline():
    out = format_table([[1]], ['a'])
    assert not out.endswith('\n')
    assert len(out.split('\n')) == 3


def test_pipes_escaped_and_counted_in_width():
    out = format_table([['a|b']], ['h'])
    assert out.splitlines() == ['| h    |', '| :--- |', '| a\\|b |']


def test_newlines_become_br():
    out = format_table([['one\ntwo'], ['x\r\ny']], ['h'])
    assert out.splitlines() == ['| h          |',
                                '| :--------- |',
                                '| one<br>two |',
                                '| x<br>y     |']


def test_none_and_non_strings():
    out = format_table([[None, 1.5, True]], ['a', 'b', 'c'])
    assert out.splitlines()[2] == '|     | 1.5 | True |'


def test_header_only_table():
    out = format_table([], ['alpha', 'b'])
    assert out == '| alpha | b   |\n| :---- | :-- |'


def test_wide_characters_use_len():
    out = format_table([['日本語の']], ['w'])
    assert out.splitlines() == ['| w    |', '| :--- |', '| 日本語の |']


def test_accepts_tuples_and_generators():
    rows = (r for r in [('a', 1), ('b', 2)])
    out = format_table(rows, ('k', 'v'), ('left', 'right'))
    assert out.splitlines()[3] == '| b   |   2 |'


def test_errors():
    with pytest.raises(ValueError):
        format_table([['a', 'b']], ['x'])
    with pytest.raises(ValueError):
        format_table([['a']], ['x', 'y'])
    with pytest.raises(ValueError):
        format_table([], [])
    with pytest.raises(ValueError):
        format_table([['a']], ['x'], ['left', 'right'])
    with pytest.raises(ValueError):
        format_table([['a']], ['x'], ['middle'])
