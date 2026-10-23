import pytest

from fmt import MissingKey, TemplateError, placeholders, render


def test_simple_substitution():
    assert render('Hello {name}!', {'name': 'Ann'}) == 'Hello Ann!'
    assert render('{a}{b}{a}', {'a': 1, 'b': 2}) == '121'
    assert render('no placeholders', {}) == 'no placeholders'


def test_values_are_strd():
    assert render('{n} {x} {e}|', {'n': 3, 'x': None, 'e': ''}) == '3 None |'


def test_default_used_only_when_missing():
    t = 'You have {count:no} new messages'
    assert render(t, {}) == 'You have no new messages'
    assert render(t, {'count': 4}) == 'You have 4 new messages'
    assert render(t, {'count': ''}) == 'You have  new messages'


def test_empty_default_and_default_with_colons():
    assert render('[{x:}]', {}) == '[]'
    assert render('{url:http://example.com:80/a}', {}) == 'http://example.com:80/a'


def test_escapes():
    assert render('{{literal}} {name}', {'name': 'v'}) == '{literal} v'
    assert render('a }} b {{', {}) == 'a } b {'
    assert render('{{{name}}}', {'name': 'v'}) == '{v}'


def test_substituted_text_not_rescanned():
    assert render('{a}', {'a': '{b}', 'b': 'NO'}) == '{b}'
    assert render('{a}', {'a': '{{'}) == '{{'


def test_names():
    assert render('{_x1} {Y_}', {'_x1': 'a', 'Y_': 'b'}) == 'a b'


def test_missing_key():
    with pytest.raises(MissingKey) as e:
        render('Hi {first} {last}', {'first': 'A'})
    assert e.value.name == 'last'
    assert isinstance(e.value, KeyError)


@pytest.mark.parametrize('template, position', [
    ('abc {', 4),
    ('{}', 0),
    ('x {1abc}', 2),
    ('{a b}', 0),
    ('{name', 0),
    ('{a:{b}}', 0),
    ('ok } no', 3),
    ('{a}}', 3),
    ('{{ { }}', 3),
    ('{a.b}', 0),
])
def test_template_errors_and_positions(template, position):
    with pytest.raises(TemplateError) as e:
        render(template, {'a': 1, 'name': 2})
    assert e.value.position == position
    assert isinstance(e.value, ValueError)


def test_syntax_checked_before_missing_keys():
    with pytest.raises(TemplateError) as e:
        render('{missing} then }', {})
    assert e.value.position == 15


def test_placeholders():
    assert placeholders('{b} {a:x} {b} {{c}} {d}') == ['b', 'a', 'd']
    assert placeholders('none') == []
    with pytest.raises(TemplateError):
        placeholders('{bad')
