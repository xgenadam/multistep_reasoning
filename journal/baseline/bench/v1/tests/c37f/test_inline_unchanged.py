from md2html import escape_html, render_inline as r


def test_escape_html():
    assert escape_html("a & <b> \"c\" 'd' &amp;") == "a &amp; &lt;b&gt; &quot;c&quot; 'd' &amp;amp;"
    assert r("<script>&") == "&lt;script&gt;&amp;"


def test_backslash_escapes():
    assert r(r"\*not\* \_x\_ \[a](b) \`c\` \\") == "*not* _x_ [a](b) `c` \\"
    assert r(r"a \q \ b\\") == r"a \q \ b" + "\\"
    assert r(r"\<\&") == "&lt;&amp;"


def test_code_spans():
    assert r("a `b < c` d") == "a <code>b &lt; c</code> d"
    assert r("``a`b``") == "<code>a`b</code>"
    assert r("`a``b`") == "<code>a``b</code>"
    assert r("` x `|`  `|` y`") == "<code>x</code>|<code>  </code>|<code> y</code>"
    assert r(r"`\*` `**x**`") == r"<code>\*</code> <code>**x**</code>"


def test_unclosed_code_span_is_literal():
    assert r("```a") == "```a"
    assert r("``a` *b*") == "``a` <em>b</em>"


def test_emphasis_basics():
    assert r("*a* _b_ **c** __d__") == "<em>a</em> <em>b</em> <strong>c</strong> <strong>d</strong>"
    assert r("a*b*c") == "a<em>b</em>c"


def test_emphasis_nests():
    assert r("**bold *both* bold**") == "<strong>bold <em>both</em> bold</strong>"
    assert r("*a **b** c*") == "<em>a <strong>b</strong> c</em>"
    assert r("**[*x*](u)**") == '<strong><a href="u"><em>x</em></a></strong>'


def test_emphasis_flanking_rules():
    assert r("* a*") == "* a*"
    assert r("*a *") == "*a *"
    assert r("**x") == "**x"
    assert r("2 * 3 * 4") == "2 * 3 * 4"
    assert r("**") == "**"


def test_underscores_inside_words():
    assert r("snake_case_name") == "snake_case_name"
    assert r("_a_b") == "_a_b"
    assert r("foo_bar_ baz") == "foo_bar_ baz"
    assert r("x _y_.") == "x <em>y</em>."


def test_escaped_closer_is_skipped():
    assert r(r"*a \* b*") == "<em>a * b</em>"
    assert r(r"*a\*") == "*a*"


def test_links():
    assert r("[x](http://a.b/c?d=1&e=\"2\")") == '<a href="http://a.b/c?d=1&amp;e=&quot;2&quot;">x</a>'
    assert r('[x](u "the title")') == '<a href="u" title="the title">x</a>'
    assert r('[x](u  "t"  )') == '<a href="u" title="t">x</a>'
    assert r("[](u)[e]()") == '<a href="u"></a><a href="">e</a>'


def test_not_links():
    assert r("[a] (b)") == "[a] (b)"
    assert r("[a](b c)") == "[a](b c)"
    assert r('[a](b "t)') == '[a](b &quot;t)'
    assert r("[a](b") == "[a](b"
    assert r("[a [b](c)") == '<a href="c">a [b</a>'


def test_images():
    assert r("![a *b*](i.png)") == '<img src="i.png" alt="a *b*" />'
    assert r('![<x>](p.png "t&")') == '<img src="p.png" alt="&lt;x&gt;" title="t&amp;" />'
    assert r("!x ![a](b c)") == "!x ![a](b c)"
    assert r("!![a](b)") == '!<img src="b" alt="a" />'
