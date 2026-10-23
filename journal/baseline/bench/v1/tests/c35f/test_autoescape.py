from tmpl import DictLoader, Environment, Template, TemplateSyntaxError, parse, render

import pytest

NASTY = "<a href=\"x\">Tom & 'Jerry'</a>"
ESCAPED = "&lt;a href=&quot;x&quot;&gt;Tom &amp; &#x27;Jerry&#x27;&lt;/a&gt;"


def test_off_by_default():
    assert render("{{ x }}", x=NASTY) == NASTY
    assert Template("{{ x }}").autoescape is False
    assert Environment().autoescape is False


def test_escapes_every_output_but_not_template_text():
    t = Template("<p class='c'>{{ x }}</p>&{{ n }}", autoescape=True)
    assert t.render(x=NASTY, n=3) == "<p class='c'>" + ESCAPED + "</p>&3"


def test_escaping_happens_after_filters():
    t = Template("{{ xs|join:'<br>' }}|{{ s|upper }}|{{ s|truncate:2 }}", autoescape=True)
    assert t.render(xs=["a", "b"], s="<b>") == "a&lt;br&gt;b|&lt;B&gt;|&lt;b..."


def test_safe_as_last_filter():
    t = Template("{{ x|safe }}|{{ x|trim|safe }}|{{ x|safe|upper }}", autoescape=True)
    assert t.render(x=" <i> ") == " <i> |<i>| &lt;I&gt; "
    assert render("{{ x|safe }}", x="<i>") == "<i>"


def test_escape_filter():
    assert render("{{ x|escape }}", x=NASTY) == ESCAPED
    assert Template("{{ x|escape }}", autoescape=True).render(x=NASTY) == ESCAPED
    assert render("[{{ n|escape }}]") == "[]"
    t = Template("{{ x|escape|upper }}", autoescape=True)
    assert t.render(x="&") == "&amp;AMP;"


def test_safe_and_escape_take_no_argument():
    for src in ("{{ x|safe:1 }}", "{{ x|escape:'a' }}"):
        with pytest.raises(TemplateSyntaxError):
            parse(src)


def test_environment_setting_applies_to_the_whole_chain():
    loader = DictLoader({"base": "<{{ a }}>{% block b %}{{ a }}{% endblock %}",
                         "child": "{% extends 'base' %}{% block b %}[{{ super() }}|{{ a }}]{% endblock %}"})
    on = Environment(loader=loader, autoescape=True)
    assert on.get_template("child").render(a="&") == "<&amp;>[&amp;|&amp;]"
    assert on.from_string("{% extends 'child' %}").render(a="<") == "<&lt;>[&lt;|&lt;]"
    off = Environment(loader=loader)
    assert off.get_template("child").render(a="&") == "<&>[&|&]"


def test_conditions_and_loops_unaffected():
    t = Template("{% for c in s %}{% if c == '<' %}{{ c }}{% endif %}{% endfor %}", autoescape=True)
    assert t.render(s="a<b") == "&lt;"
