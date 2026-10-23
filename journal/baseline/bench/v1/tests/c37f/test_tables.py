from md2html import parse_blocks, render_blocks, to_html


def test_spec_table_html():
    src = "| Name | Qty |\n|------|----:|\n| apple | 3 |\n"
    assert to_html(src) == (
        "<table>\n<thead>\n<tr>\n<th>Name</th>\n<th align=\"right\">Qty</th>\n</tr>\n</thead>\n"
        "<tbody>\n<tr>\n<td>apple</td>\n<td align=\"right\">3</td>\n</tr>\n</tbody>\n</table>\n")


def test_alignments_and_outer_pipes_optional():
    assert parse_blocks("a | b | c | d\n:-- | --: | :-: | -\n1|2|3|4") == [
        ("table", ["left", "right", "center", None], ["a", "b", "c", "d"], [["1", "2", "3", "4"]])]
    assert parse_blocks("|a|b|\n|:-|-|") == [("table", ["left", None], ["a", "b"], [])]


def test_table_without_body_has_no_tbody():
    assert to_html("| only |\n|:---:|") == \
        '<table>\n<thead>\n<tr>\n<th align="center">only</th>\n</tr>\n</thead>\n</table>\n'


def test_short_rows_padded_long_rows_cut():
    assert parse_blocks("a|b|c\n-|-|-\n1|\n1|2|3|4|5\n|x||") == [
        ("table", [None] * 3, ["a", "b", "c"], [["1", "", ""], ["1", "2", "3"], ["x", "", ""]])]


def test_escaped_pipes():
    blocks = parse_blocks("| a \\| b | c |\n|---|---|\n| `x \\| y` | z \\|")
    assert blocks == [("table", [None, None], ["a | b", "c"], [["`x | y`", "z |"]])]
    assert "<td><code>x | y</code></td>" in render_blocks(blocks)


def test_cells_get_inline_markup():
    html = to_html("h|*e*\n-|-\n[l](u)|<x>")
    assert "<th><em>e</em></th>" in html
    assert '<td><a href="u">l</a></td>' in html
    assert "<td>&lt;x&gt;</td>" in html


def test_not_tables():
    assert parse_blocks("a | b\n--- | --- | ---") == [("paragraph", "a | b\n--- | --- | ---")]
    assert parse_blocks("a | b\nx | y") == [("paragraph", "a | b\nx | y")]
    assert parse_blocks("a | b\n-- | :x:") == [("paragraph", "a | b\n-- | :x:")]
    assert parse_blocks(" a | b\n---|---") == [("paragraph", "a | b\n---|---")]
    assert parse_blocks("a | b") == [("paragraph", "a | b")]


def test_table_interrupts_a_paragraph():
    assert parse_blocks("intro text\n| a | b |\n|---|---|\n| 1 | 2 |\nafter") == [
        ("paragraph", "intro text"), ("table", [None, None], ["a", "b"], [["1", "2"]]),
        ("paragraph", "after")]


def test_body_ends_at_blank_line_or_other_block():
    assert parse_blocks("a|b\n-|-\n1|2\n\n3|4") == [
        ("table", [None, None], ["a", "b"], [["1", "2"]]), ("paragraph", "3|4")]
    assert parse_blocks("a|b\n-|-\n1|2\n# h | x\n- i | j") == [
        ("table", [None, None], ["a", "b"], [["1", "2"]]), ("heading", 1, "h | x"),
        ("list", False, None, [("i | j", [])])]


def test_header_row_beats_horizontal_rule():
    assert parse_blocks("| x |\n---") == [("table", [None], ["x"], [])]


def test_table_inside_blockquote():
    assert parse_blocks("> a|b\n> -|-\n> 1|2") == [
        ("blockquote", [("table", [None, None], ["a", "b"], [["1", "2"]])])]
