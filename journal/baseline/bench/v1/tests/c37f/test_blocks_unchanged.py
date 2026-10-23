# Copied from tests/c37/test_blocks.py. Adapted for c37f: list items are now
# (text, children) tuples instead of strings (the spec changes the item shape);
# nothing else is changed.
import md2html
from md2html import parse_blocks, render_blocks, to_html


def test_spec_example():
    src = "# Hi *there*\n\nSome `code` & [a link](http://x.org/?a=1&b=2).\n\n- one\n- two\n"
    assert to_html(src) == (
        '<h1>Hi <em>there</em></h1>\n'
        '<p>Some <code>code</code> &amp; <a href="http://x.org/?a=1&amp;b=2">a link</a>.</p>\n'
        '<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n')


def test_empty_and_blank_documents():
    assert to_html("") == ""
    assert to_html("\n  \n\t\n") == ""
    assert parse_blocks("") == []


def test_headings():
    assert parse_blocks("# One\n###### Six\n## Title ##\n# C#\n#tag\n####### seven\n#\n### x ### \n") == [
        ("heading", 1, "One"), ("heading", 6, "Six"), ("heading", 2, "Title"), ("heading", 1, "C#"),
        ("paragraph", "#tag\n####### seven"), ("heading", 1, ""), ("heading", 3, "x")]
    assert to_html("## a *b*") == "<h2>a <em>b</em></h2>\n"


def test_paragraph_lines_are_stripped_and_joined():
    assert parse_blocks("  one  \ntwo\n   three\n\nfour") == [
        ("paragraph", "one\ntwo\nthree"), ("paragraph", "four")]
    assert to_html("a\nb") == "<p>a\nb</p>\n"


def test_indented_markers_are_paragraph_text():
    assert parse_blocks(" # not\n  - not\n > not") == [("paragraph", "# not\n- not\n> not")]


def test_block_starts_interrupt_a_paragraph():
    assert parse_blocks("para\n# h\npara\n- item\npara\n> q\npara\n---\npara\n```\nc\n```") == [
        ("paragraph", "para"), ("heading", 1, "h"), ("paragraph", "para"),
        ("list", False, None, [("item\npara", [])]), ("blockquote", [("paragraph", "q")]),
        ("paragraph", "para"), ("hr",), ("paragraph", "para"), ("code", "", "c\n")]


def test_fenced_code():
    src = "```python extra words\nif a < b:\n\n    print('&')\n```\nafter"
    assert parse_blocks(src) == [("code", "python", "if a < b:\n\n    print('&')\n"), ("paragraph", "after")]
    assert to_html(src) == ('<pre><code class="language-python">if a &lt; b:\n\n    print(\'&amp;\')\n'
                            '</code></pre>\n<p>after</p>\n')


def test_fence_close_needs_enough_backticks_and_unclosed_runs_to_end():
    assert parse_blocks("````\n```\n# x\n`````  \nz") == [("code", "", "```\n# x\n"), ("paragraph", "z")]
    assert parse_blocks("```\n*a*\n\n") == [("code", "", "*a*\n\n\n")]
    assert to_html("```\n```") == "<pre><code></code></pre>\n"


def test_horizontal_rules():
    assert parse_blocks("---\n* * *\n_ _ _ _  \n-- -\n--\n-*-") == [
        ("hr",), ("hr",), ("hr",), ("hr",), ("paragraph", "--\n-*-")]
    assert to_html("***") == "<hr />\n"


def test_blockquotes():
    src = "> # h\n>para\n>\n> - a\nafter"
    assert parse_blocks(src) == [
        ("blockquote", [("heading", 1, "h"), ("paragraph", "para"), ("list", False, None, [("a", [])])]),
        ("paragraph", "after")]
    assert to_html(src) == ("<blockquote>\n<h1>h</h1>\n<p>para</p>\n<ul>\n<li>a</li>\n</ul>\n</blockquote>\n"
                            "<p>after</p>\n")


def test_nested_and_empty_blockquotes():
    assert to_html("> > deep\n> back") == \
        "<blockquote>\n<blockquote>\n<p>deep</p>\n</blockquote>\n<p>back</p>\n</blockquote>\n"
    assert to_html(">") == "<blockquote>\n</blockquote>\n"
    assert parse_blocks("> a\n\n> b") == [("blockquote", [("paragraph", "a")]),
                                         ("blockquote", [("paragraph", "b")])]


def test_bullet_lists_split_on_marker_change_and_blank_lines():
    assert parse_blocks("- a\n- b\n* c\n+ d\n\n- e") == [
        ("list", False, None, [("a", []), ("b", [])]), ("list", False, None, [("c", [])]),
        ("list", False, None, [("d", [])]), ("list", False, None, [("e", [])])]


def test_ordered_lists_and_start():
    assert parse_blocks("3. c\n1. d\n- x\n007. z") == [
        ("list", True, 3, [("c", []), ("d", [])]), ("list", False, None, [("x", [])]), ("list", True, 7, [("z", [])])]
    assert to_html("1. a\n2. b") == "<ol>\n<li>a</li>\n<li>b</li>\n</ol>\n"
    assert to_html("3. a") == '<ol start="3">\n<li>a</li>\n</ol>\n'
    assert parse_blocks("1.5 x\n1) y\n-x") == [("paragraph", "1.5 x\n1) y\n-x")]


def test_list_continuations_and_rule_ending_a_list():
    assert parse_blocks("- a\n  more\nlazy\n- b\n- - -\n- c") == [
        ("list", False, None, [("a\nmore\nlazy", []), ("b", [])]), ("hr",), ("list", False, None, [("c", [])])]
    assert to_html("- **a**\n  b") == "<ul>\n<li><strong>a</strong>\nb</li>\n</ul>\n"


def test_crlf_and_render_blocks():
    assert parse_blocks("# a\r\nb\rc") == [("heading", 1, "a"), ("paragraph", "b\nc")]
    assert render_blocks([("hr",), ("paragraph", "x")]) == "<hr />\n<p>x</p>"
    assert render_blocks([]) == ""


def test_exports():
    for name in ("to_html", "parse_blocks", "render_blocks", "render_inline", "escape_html"):
        assert callable(getattr(md2html, name))
