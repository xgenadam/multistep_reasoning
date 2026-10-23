import pytest

from tmpl import (DictLoader, Environment, Template, TemplateError, TemplateNotFound,
                  TemplateRenderError, TemplateSyntaxError, parse, render)


def env(**templates):
    return Environment(loader=DictLoader(templates))


def test_spec_example():
    loader = DictLoader({
        "base.html": "<title>{% block title %}Site{% endblock %}</title>\n<main>{% block body %}{% endblock %}</main>\n",
        "page.html": '{% extends "base.html" %}{% block title %}{{ title }} - {{ super() }}{% endblock %}{% block body %}<p>{{ text }}</p>{% endblock %}',
    })
    e = Environment(loader=loader, autoescape=True)
    assert e.get_template("page.html").render(title="Q&A", text="1 < 2") == \
        "<title>Q&amp;A - Site</title>\n<main><p>1 &lt; 2</p></main>\n"


def test_loader_and_not_found():
    loader = DictLoader({"a": "A"})
    assert loader.get_source("a") == "A"
    with pytest.raises(TemplateNotFound) as info:
        loader.get_source("nope.html")
    assert info.value.name == "nope.html"
    assert str(info.value) == "template not found: nope.html"
    assert issubclass(TemplateNotFound, TemplateError)
    from tmpl.lexer import TemplateNotFound as T2
    assert T2 is TemplateNotFound


def test_environment_templates():
    e = env(a="{{ x }}!")
    t = e.get_template("a")
    assert isinstance(t, Template) and t.name == "a" and t.loader is e.loader
    assert t.render(x=1) == "1!"
    s = e.from_string("[{{ x }}]")
    assert s.name is None and s.render(x=2) == "[2]"
    with pytest.raises(TemplateNotFound):
        e.get_template("b")
    with pytest.raises(TemplateNotFound):
        Environment().get_template("a")
    with pytest.raises(TemplateSyntaxError):
        env(bad="{% if x %}").get_template("bad")


def test_blocks_without_extends_render_in_place():
    assert render("a{% block x %}[{{ v }}]{% block y %}y{% endblock y %}{% endblock %}b", v=1) == "a[1]yb"


def test_child_overrides_and_ignores_text_outside_blocks():
    e = env(base="<{% block a %}A{% endblock %}|{% block b %}B{% endblock %}>",
            child='  {# hi #}\n{% extends "base" %}junk {{ boom|length }}{% block b %}b{% endblock %}'
                  '{% for x in xs %}more{% endfor %}{% block unused %}U{% endblock %}')
    assert e.get_template("child").render(xs=[1]) == "<A|b>"


def test_three_level_chain_most_derived_wins():
    e = env(base="{% block a %}A{% endblock %}{% block b %}B{% endblock %}{% block c %}C{% endblock %}",
            mid="{% extends 'base' %}{% block a %}a1{% endblock %}{% block b %}b1{% endblock %}",
            leaf="{% extends 'mid' %}{% block a %}a2{% endblock %}")
    assert e.get_template("leaf").render() == "a2b1C"
    assert e.get_template("mid").render() == "a1b1C"


def test_super_chains_through_levels():
    e = env(base="{% block t %}A{% endblock %}",
            mid="{% extends 'base' %}{% block t %}B({{ super() }}){% endblock %}",
            leaf="{% extends 'mid' %}{% block t %}C({{ super( ) }}){% endblock %}")
    assert e.get_template("leaf").render() == "C(B(A))"


def test_nested_blocks():
    e = env(base="{% block outer %}[{% block inner %}i{% endblock %}]{% endblock %}",
            only_inner="{% extends 'base' %}{% block inner %}I{% endblock %}",
            outer="{% extends 'base' %}{% block outer %}<{% block inner %}J{% endblock %}>{% endblock %}",
            outer_super="{% extends 'base' %}{% block outer %}<{{ super() }}>{% endblock %}{% block inner %}K{% endblock %}")
    assert e.get_template("only_inner").render() == "[I]"
    assert e.get_template("outer").render() == "<J>"
    assert e.get_template("outer_super").render() == "<[K]>"


def test_child_blocks_inside_statements_count_and_see_the_context():
    e = env(base="{% for x in xs %}{% block row %}{{ x }}{% endblock %},{% endfor %}{{ title }}",
            child="{% extends 'base' %}{% if never %}{% block row %}<{{ x }}:{{ loop.index }}>{% endblock %}{% endif %}")
    assert e.get_template("child").render(xs=["a", "b"], title="T") == "<a:1>,<b:2>,T"


def test_template_with_loader_keyword():
    t = Template("{% extends 'p' %}{% block x %}child{% endblock %}",
                 loader=DictLoader({"p": "p:{% block x %}{% endblock %}"}))
    assert t.render() == "p:child"
    assert t.render() == "p:child"


def test_missing_parent_and_missing_loader():
    with pytest.raises(TemplateNotFound) as info:
        env(c="{% extends 'gone' %}").get_template("c").render()
    assert info.value.name == "gone"
    t = Template("{% extends 'p' %}")
    with pytest.raises(TemplateNotFound):
        t.render()


def test_circular_extends():
    e = env(a="\n{% extends 'b' %}", b=" \n\n{% extends 'a' %}", s="{% extends 's' %}")
    with pytest.raises(TemplateRenderError) as info:
        e.get_template("a").render()
    assert info.value.lineno == 3
    with pytest.raises(TemplateRenderError) as info:
        e.get_template("s").render()
    assert info.value.lineno == 1


def test_super_without_parent_definition():
    e = env(base="{% block a %}A{% endblock %}",
            child="{% extends 'base' %}{% block a %}{{ super() }}{% endblock %}\n{% block z %}\n{% endblock %}")
    assert e.get_template("child").render() == "A"
    t = Template("{% block a %}\n\n{{ super() }}{% endblock %}")
    with pytest.raises(TemplateRenderError) as info:
        t.render()
    assert info.value.lineno == 3


def test_parent_syntax_error_raised_on_render():
    t = env(p="{% block x %}", c="{% extends 'p' %}").get_template("c")
    with pytest.raises(TemplateSyntaxError):
        t.render()


def check_syntax(cases):
    for src, line in cases:
        with pytest.raises(TemplateSyntaxError) as info:
            parse(src)
        assert info.value.lineno == line, src


def test_extends_must_be_first_and_quoted():
    check_syntax([
        ("x{% extends 'p' %}", 1),
        ("{{ a }}\n{% extends 'p' %}", 2),
        ("{% extends 'p' %}\n{% extends 'q' %}", 2),
        ("{% if a %}{% extends 'p' %}{% endif %}", 1),
        ("\n{% extends p %}", 2),
    ])


def test_bad_block_tags():
    check_syntax([
        ("{% block %}{% endblock %}", 1),
        ("{% block a b %}{% endblock %}", 1),
        ("{% block a %}{% endblock %}\n{% block a %}{% endblock %}", 2),
        ("{% block a %}{% block a %}{% endblock %}{% endblock %}", 1),
    ])


def test_unclosed_and_mismatched_blocks():
    check_syntax([
        ("\n{% block a %}x", 2),
        ("{% block a %}\n{% endblock b %}", 2),
        ("x\n{% endblock %}", 2),
        ("{% block a %}{% for x in y %}\n{% endblock %}{% endfor %}{% endblock %}", 2),
    ])


def test_bad_super():
    check_syntax([
        ("a\n{{ super() }}", 2),
        ("{% block a %}{{ super }}{% endblock %}", 1),
        ("{% block a %}{{ super()|upper }}{% endblock %}", 1),
    ])


def test_extends_after_whitespace_and_comments_is_allowed():
    t = Template(" \n{# c #}\n{% extends \"p\" %}{% block b %}2{% endblock %}",
                 loader=DictLoader({"p": "1{% block b %}{% endblock %}3"}))
    assert t.render() == "123"
