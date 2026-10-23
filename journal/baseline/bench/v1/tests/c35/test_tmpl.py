import pytest

from tmpl import Template, Token, render, tokenize


def test_tokenize_example_from_the_spec():
    assert tokenize("a{{ x }}\n{% if y %}b{# c #}d") == [
        Token("text", "a", 1), Token("var", "x", 1), Token("text", "\n", 1),
        Token("block", "if y", 2), Token("text", "b", 2), Token("text", "d", 2)]


def test_tokenize_counts_lines_inside_tags_and_comments():
    toks = tokenize("{#\n\n#}{{\n x \n}}\nz{% endif %}")
    assert toks == [Token("var", "x", 3), Token("text", "\nz", 5), Token("block", "endif", 6)]


def test_text_and_stray_braces_are_copied_exactly():
    src = "a { b } c}} %} #}\n  \n\tend {x}"
    assert render(src) == src


def test_spec_example():
    src = ("{% for u in users %}{{ loop.index }}. {{ u.name|upper }}{% if u.admin %} (admin){% endif %}\n"
           "{% else %}nobody\n{% endfor %}\n")
    users = [{"name": "ada", "admin": True}, {"name": "bob"}]
    assert render(src, users=users) == "1. ADA (admin)\n2. BOB\n\n"
    assert render(src, users=[]) == "nobody\n\n"


def test_paths_through_dicts_attributes_and_indexes():
    class User:
        name = "ada"
        _secret = "no"

    ctx = {"u": User(), "rows": [{"t": "first"}, {"t": "second"}], "m": {"0": "zero"}}
    assert render("{{ u.name }}|{{ rows.1.t }}|{{ m.0 }}|{{ rows.5.t }}|{{ u._secret }}|{{ u.nope }}", ctx) \
        == "ada|second|zero|||"


def test_missing_and_none_render_empty_other_values_use_str():
    assert render("[{{ nope }}][{{ nope.deeper.still }}][{{ n }}][{{ t }}][{{ f }}][{{ x }}]",
                  n=None, t=True, f=2.5, x=0) == "[][][][True][2.5][0]"


def test_literals():
    assert render("{{ 'it' }}{{ \"is\" }}{{ 42 }}{{ -3 }}") == "itis42-3"


def test_kwargs_win_and_context_is_not_modified():
    ctx = {"a": 1, "b": 2}
    t = Template("{{ a }}{{ b }}{% for a in xs %}{{ a }}{% endfor %}")
    assert t.render(ctx, b=9, xs=[7]) == "197"
    assert ctx == {"a": 1, "b": 2}
    assert t.render(ctx) == "12"


def check_all(cases):
    for src, ctx, expected in cases:
        assert render(src, ctx) == expected, src


def test_text_filters():
    check_all([
        ("{{ s|upper }}", {"s": "aBc"}, "ABC"),
        ("{{ s|lower }}", {"s": "aBc"}, "abc"),
        ("[{{ s|trim }}]", {"s": "  a b \n"}, "[a b]"),
        ("[{{ n|upper }}]{{ x|upper }}", {"n": None, "x": True}, "[]TRUE"),
    ])


def test_sequence_filters():
    check_all([
        ("{{ xs|length }}/{{ d|length }}/{{ nope|length }}", {"xs": [1, 2, 3], "d": {"k": 1}}, "3/1/0"),
        ("{{ xs|first }}{{ xs|last }}{{ s|first }}[{{ e|first }}][{{ nope|last }}]",
         {"xs": [1, 2, 3], "s": "hey", "e": []}, "13h[][]"),
        ("{{ s|reverse }} {{ xs|reverse|join:',' }}", {"s": "abc", "xs": [1, 2, 3]}, "cba 3,2,1"),
        ("{% for p in d|items %}{{ p.0 }}={{ p.1 }};{% endfor %}", {"d": {"b": 1, "a": 2}}, "b=1;a=2;"),
    ])


def test_filters_with_arguments():
    check_all([
        ("{{ xs|join:\", \" }}[{{ nope|join:'-' }}]", {"xs": ["a", None, 3]}, "a, , 3[]"),
        ("{{ a|default:'x' }}{{ b|default:'x' }}{{ c|default:7 }}{{ d|default:'x' }}{{ e|default:'x' }}",
         {"b": "", "c": None, "d": 0, "e": False}, "xx70False"),
        ("{{ s|truncate:5 }}|{{ t|truncate:5 }}|{{ u|truncate:0 }}", {"s": "hello", "t": "hello!", "u": "ab"},
         "hello|hello...|..."),
    ])


def test_filters_chain_left_to_right():
    assert render("{{ s | trim | upper | truncate : 3 }}", s="  hello ") == "HEL..."
    assert render("{{ s|truncate:3|upper }}", s="hello") == "HEL..."


def test_for_loop_variables():
    src = "{% for x in xs %}{{ loop.index0 }}{{ loop.index }}{{ loop.length }}{% if loop.first %}F{% endif %}{% if loop.last %}L{% endif %}{{ x }} {% endfor %}"
    assert render(src, xs="ab") == "012Fa 122Lb "


def test_for_over_mapping_none_and_else():
    assert render("{% for k in d %}{{ k }}{% endfor %}", d={"x": 1, "y": 2}) == "xy"
    assert render("{% for k in nope %}{{ k }}{% else %}empty{% endfor %}") == "empty"
    assert render("{% for k in xs %}{{ k }}{% else %}empty{% endfor %}", xs=[0]) == "0"


def test_loop_scope_is_restored():
    src = "{% for x in xs %}{{ x }}{% endfor %}[{{ x }}][{{ loop }}]"
    assert render(src, xs=[1, 2]) == "12[][]"
    assert render(src, xs=[1, 2], x="outer") == "12[outer][]"


def test_nested_loops_loop_is_innermost():
    src = "{% for r in rows %}{% for c in r %}{{ loop.index }}{{ c }}{% endfor %}/{{ loop.index }};{% endfor %}"
    assert render(src, rows=[["a", "b"], ["c"]]) == "1a2b/1;1c/2;"


def test_if_elif_else_picks_first_true_branch():
    src = "{% if n == 1 %}one{% elif n == 2 %}two{% elif n < 4 %}three{% elif n < 5 %}never{% else %}many{% endif %}"
    assert [render(src, n=n) for n in (1, 2, 3, 9)] == ["one", "two", "three", "many"]


def test_if_without_else_and_truthiness():
    src = "{% if v %}yes{% endif %}."
    assert [render(src, v=v) for v in (0, "", [], None, "a", [0], 3)] == \
        [".", ".", ".", ".", "yes.", "yes.", "yes."]


def cond(expr, /, **ctx):
    return render("{% if " + expr + " %}T{% else %}F{% endif %}", ctx) == "T"


def test_not_is_looser_than_comparison():
    assert cond("not a == b", a=1, b=2) is True
    assert cond("not a == b", a=1, b=1) is False
    assert cond("not not a", a=1) is True


def test_and_binds_tighter_than_or():
    assert cond("a or b and c", a=True, b=False, c=False) is True
    assert cond("not a and b", a=False, b=True) is True
    assert cond("a and b or c", a=False, b=True, c=True) is True


def test_conditions_with_filters_literals_and_missing_names():
    assert cond("a != 'x' and xs|length >= 2", a="y", xs=[1, 2]) is True
    assert cond("name|upper == 'ADA' or 0", name="ada") is True
    assert cond("missing == missing2") is True
    assert cond("n > -5 and n <= 0", n=0) is True


def test_multiline_template_whitespace_is_preserved():
    src = "<ul>\n{% for i in xs %}  <li>{{ i }}</li>\n{% endfor %}</ul>\n"
    assert render(src, xs=[1, 2]) == "<ul>\n  <li>1</li>\n  <li>2</li>\n</ul>\n"
