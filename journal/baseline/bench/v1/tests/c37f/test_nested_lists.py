from md2html import parse_blocks, to_html


def L(*items, ordered=False, start=None):
    return ("list", ordered, start, [i if isinstance(i, tuple) else (i, []) for i in items])


def test_spec_example():
    assert parse_blocks("- a\n  - b\n- c") == [L(("a", [L("b")]), "c")]
    assert to_html("- a\n  - b\n- c") == \
        "<ul>\n<li>a\n<ul>\n<li>b</li>\n</ul>\n</li>\n<li>c</li>\n</ul>\n"


def test_three_levels_and_closing_back_out():
    src = "- a\n  - b\n    - c\n  - d\n- e"
    assert parse_blocks(src) == [L(("a", [L(("b", [L("c")]), "d")]), "e")]
    assert to_html(src) == ("<ul>\n<li>a\n<ul>\n<li>b\n<ul>\n<li>c</li>\n</ul>\n</li>\n<li>d</li>\n</ul>\n"
                            "</li>\n<li>e</li>\n</ul>\n")


def test_close_several_levels_at_once():
    assert parse_blocks("- a\n  - b\n    - c\n- d") == [L(("a", [L(("b", [L("c")]))]), "d")]


def test_in_between_indent_starts_a_new_nested_list():
    assert parse_blocks("- a\n    - b\n  - c") == [L(("a", [L("b"), L("c")]))]
    assert parse_blocks("- a\n - b") == [L(("a", [L("b")]))]


def test_ordered_inside_bullets_with_start():
    src = "- a\n  3. x\n  4. y\n- b"
    assert parse_blocks(src) == [L(("a", [L("x", "y", ordered=True, start=3)]), "b")]
    assert '<li>a\n<ol start="3">\n<li>x</li>\n<li>y</li>\n</ol>\n</li>' in to_html(src)


def test_kind_change_in_nested_list_starts_a_sibling_list():
    assert parse_blocks("- a\n  1. x\n  - y\n  - z") == [
        L(("a", [L("x", ordered=True, start=1), L("y", "z")]))]


def test_kind_change_at_top_level_still_ends_the_list():
    assert parse_blocks("- a\n  - b\n* c") == [L(("a", [L("b")])), L("c")]


def test_continuations_go_to_the_innermost_item():
    assert parse_blocks("- a\n  - b\n  more\nlazy\n- c") == [L(("a", [L("b\nmore\nlazy")]), "c")]
    assert parse_blocks("- a\n  # not a heading\n  - b") == [L(("a\n# not a heading", [L("b")]))]


def test_list_ends_at_blank_line_and_column_zero_blocks():
    assert parse_blocks("- a\n  - b\n\n  - c") == [L(("a", [L("b")])), ("paragraph", "- c")]
    assert parse_blocks("- a\n  - b\n# h") == [L(("a", [L("b")])), ("heading", 1, "h")]
    assert parse_blocks("- a\n  - b\n---") == [L(("a", [L("b")])), ("hr",)]


def test_table_after_list_ends_it():
    assert parse_blocks("- a\n| x | y |\n|---|---|") == [
        L("a"), ("table", [None, None], ["x", "y"], [])]


def test_indented_marker_cannot_start_a_list():
    assert parse_blocks("  - a\n  - b") == [("paragraph", "- a\n- b")]
    assert parse_blocks("text\n  - a") == [("paragraph", "text\n- a")]
