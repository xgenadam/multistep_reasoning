import pytest

import tmpl
from tmpl import (Template, TemplateError, TemplateRenderError, TemplateSyntaxError, parse,
                  render, tokenize)


def test_error_classes():
    assert issubclass(TemplateSyntaxError, TemplateError)
    assert issubclass(TemplateRenderError, TemplateError)
    assert issubclass(TemplateError, Exception)
    e = TemplateSyntaxError("bad thing", 7)
    assert (e.message, e.lineno, str(e)) == ("bad thing", 7, "line 7: bad thing")
    e = TemplateRenderError("worse", 2)
    assert (e.message, e.lineno, str(e)) == ("worse", 2, "line 2: worse")
    from tmpl.lexer import TemplateSyntaxError as T2
    assert T2 is TemplateSyntaxError


def test_unclosed_tag_in_tokenize():
    with pytest.raises(TemplateSyntaxError) as info:
        tokenize("ok\n\nhere {{ x \n more")
    assert info.value.lineno == 3


def check_syntax(cases):
    for src, line in cases:
        with pytest.raises(TemplateSyntaxError) as info:
            parse(src)
        assert info.value.lineno == line, src
        assert str(info.value).startswith(f"line {line}: "), src
        with pytest.raises(TemplateSyntaxError):
            Template(src)


def test_unclosed_blocks_report_the_opening_line():
    check_syntax([
        ("a\n{% if x %}\nb\n{% for y in z %}{% endfor %}\n", 2),
        ("{% for y in z %}\n{% if a %}{% endif %}\n", 1),
        ("{# never closed\n", 1),
        ("{#\n\n#}{{ x\n", 3),
    ])


def test_misplaced_closers_report_their_own_line():
    check_syntax([
        ("x\n{% if a %}\n{% endfor %}{% endif %}", 3),
        ("\n\n{% endif %}", 3),
        ("{% if a %}\n{% else %}\n{% else %}{% endif %}", 3),
        ("{% if a %}\n{% else %}\n{% elif b %}{% endif %}", 3),
        ("{% for x in y %}\n{% elif b %}{% endfor %}", 2),
        ("{% if a %}{% endif extra %}", 1),
    ])


def test_bad_statements():
    check_syntax([
        ("ok\n{% while x %}", 2),
        ("{% for x of y %}{% endfor %}", 1),
        ("{% for in y %}{% endfor %}", 1),
        ("{% if %}{% endif %}", 1),
        ("{% if a < b < c %}{% endif %}", 1),
    ])


def test_bad_expressions():
    check_syntax([
        ("a\n\n{{ }}", 3),
        ("{{ a == b }}", 1),
        ("{{ not }}", 1),
        ("{{ a. }}", 1),
    ])


def test_bad_filters():
    check_syntax([
        ("{{ x|shout }}", 1),
        ("\n{{ x|join }}", 2),
        ("{{ x|upper:'a' }}", 1),
        ("{{ x|truncate:'a' }}", 1),
        ("{{ x|truncate:-1 }}", 1),
        ("{{ x|join:3 }}", 1),
    ])


def test_line_numbers_after_multiline_tags():
    src = "{{\nx\n}}\n{% if a\n %}ok{% endif %}\n{% if b %}"
    with pytest.raises(TemplateSyntaxError) as info:
        parse(src)
    assert info.value.lineno == 6


def check_render_error(src, ctx, line):
    t = Template(src)
    with pytest.raises(TemplateRenderError) as info:
        t.render(ctx)
    assert info.value.lineno == line
    assert str(info.value).startswith(f"line {line}: ")


def test_filter_render_errors():
    check_render_error("a\n{{ n|length }}", {"n": 5}, 2)
    check_render_error("{{ xs|items }}", {"xs": [1]}, 1)


def test_loop_over_non_iterable():
    check_render_error("\n\n{% for x in n %}{% endfor %}", {"n": 3}, 3)


def test_unorderable_comparisons():
    check_render_error("{% if 'a' < 1 %}{% endif %}", {}, 1)
    check_render_error("{% if a %}\n{% elif x < 1 %}{% endif %}", {"a": False, "x": None}, 2)


def test_short_circuit_avoids_render_errors():
    assert render("{% if a and x < 1 %}y{% else %}n{% endif %}", a=False, x=None) == "n"
    assert render("{% if a or x < 1 %}y{% else %}n{% endif %}", a=True, x=None) == "y"


def test_exports():
    for name in ["Template", "render", "tokenize", "parse", "Token", "TemplateError",
                 "TemplateSyntaxError", "TemplateRenderError"]:
        assert hasattr(tmpl, name)
