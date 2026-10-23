import re

import pytest

from ini import ParseError, parse

SAMPLE = """\
; top comment
# another comment

[server]
host = example.org
port=8080
debug = Yes
url = http://example.org/#top ; not a comment
empty =
tags = web, api,, internal ,

[ paths ]
cmd = run
    --fast
\t--quiet
root =   /srv/app
"""


def error_line(text):
    with pytest.raises(ParseError) as info:
        parse(text)
    err = info.value
    assert isinstance(err, ValueError)
    assert re.search(rf'\bline {err.lineno}\b', str(err))
    return err.lineno


@pytest.fixture
def cfg():
    return parse(SAMPLE)


def test_sections_in_order(cfg):
    assert cfg.sections() == ['server', 'paths']


def test_keys_in_order(cfg):
    assert cfg.keys('server') == ['host', 'port', 'debug', 'url', 'empty', 'tags']
    assert cfg.keys('paths') == ['cmd', 'root']
    with pytest.raises(KeyError):
        cfg.keys('nope')


def test_get_strips_and_keeps_hash_and_semicolon(cfg):
    assert cfg.get('server', 'host') == 'example.org'
    assert cfg.get('server', 'port') == '8080'
    assert cfg.get('server', 'url') == 'http://example.org/#top ; not a comment'
    assert cfg.get('server', 'empty') == ''
    assert cfg.get('paths', 'root') == '/srv/app'


def test_get_missing_returns_default(cfg):
    assert cfg.get('server', 'nope') is None
    assert cfg.get('nope', 'host', 'd') == 'd'
    assert cfg.get('server', 'HOST', 'd') == 'd'  # keys are case-sensitive


def test_continuation_lines_joined_with_newline(cfg):
    assert cfg.get('paths', 'cmd') == 'run\n--fast\n--quiet'


def test_getint(cfg):
    assert cfg.getint('server', 'port') == 8080
    c = parse('[n]\na = -7\nb = +3\nc = 007\n')
    assert (c.getint('n', 'a'), c.getint('n', 'b'), c.getint('n', 'c')) == (-7, 3, 7)
    assert cfg.getint('server', 'missing', 5) == 5
    assert cfg.getint('nope', 'port') is None


def test_getint_rejects():
    for value in ['4.0', '0x10', '', '1 2', 'ten', '1_000']:
        c = parse(f'[n]\nv = {value}\n')
        with pytest.raises(ValueError):
            c.getint('n', 'v')


def test_getbool_words_any_case():
    words = ['true', 'YES', 'On', '1', 'False', 'no', 'OFF', '0']
    text = '[b]\n' + ''.join(f'k{i} = {w}\n' for i, w in enumerate(words))
    c = parse(text)
    assert [c.getbool('b', f'k{i}') for i in range(8)] == [True] * 4 + [False] * 4


def test_getbool_rejects_and_defaults(cfg):
    assert cfg.getbool('server', 'debug') is True
    assert cfg.getbool('server', 'missing', False) is False
    with pytest.raises(ValueError):
        cfg.getbool('server', 'host')
    with pytest.raises(ValueError):
        cfg.getbool('server', 'empty')


def test_getlist(cfg):
    assert cfg.getlist('server', 'tags') == ['web', 'api', 'internal']
    assert cfg.getlist('server', 'empty') == []
    assert cfg.getlist('server', 'host') == ['example.org']
    assert cfg.getlist('server', 'missing') is None
    assert cfg.getlist('server', 'missing', ['x']) == ['x']


def test_split_at_first_equals():
    c = parse('[s]\nexpr = a=b = c\n')
    assert c.get('s', 'expr') == 'a=b = c'


def test_blank_or_comment_ends_continuation():
    assert error_line('[s]\na = 1\n\n  more\n') == 4
    assert error_line('[s]\na = 1\n; note\n  more\n') == 4


def test_indented_comment_is_a_comment():
    c = parse('[s]\na = 1\n   ; still a comment\nb = 2\n')
    assert c.get('s', 'a') == '1'
    assert c.keys('s') == ['a', 'b']


def test_indented_line_after_header_is_an_error():
    assert error_line('[s]\n  a = 1\n') == 2


def test_key_before_section():
    assert error_line('; c\n\nname = x\n[s]\n') == 3


def test_duplicate_key_reports_second_line():
    assert error_line('[a]\nx = 1\n[b]\nx = 2\ny = 3\n\nx = 4\n') == 7


def test_same_key_in_two_sections_is_fine():
    c = parse('[a]\nx = 1\n[b]\nx = 2\n')
    assert (c.get('a', 'x'), c.get('b', 'x')) == ('1', '2')


def test_duplicate_section():
    assert error_line('[a]\nx = 1\n[b]\n[ a ]\n') == 4


def test_empty_key_and_empty_section_name():
    assert error_line('[a]\n= 1\n') == 2
    assert error_line('[a]\nx = 1\n[  ]\n') == 3


def test_malformed_lines():
    assert error_line('[a]\nx = 1\njust words\n') == 3
    assert error_line('[a\nx = 1\n') == 1


def test_empty_text():
    c = parse('')
    assert c.sections() == []
