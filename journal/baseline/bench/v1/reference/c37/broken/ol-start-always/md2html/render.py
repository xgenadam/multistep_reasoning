"""Turn parsed blocks into HTML."""
from .blocks import parse_blocks
from .inline import escape_html, render_inline


def render_block(block: tuple) -> str:
    kind = block[0]
    if kind == 'heading':
        _, level, text = block
        return f'<h{level}>{render_inline(text)}</h{level}>'
    if kind == 'paragraph':
        return f'<p>{render_inline(block[1])}</p>'
    if kind == 'code':
        _, lang, code = block
        cls = f' class="language-{escape_html(lang)}"' if lang else ''
        return f'<pre><code{cls}>{escape_html(code)}</code></pre>'
    if kind == 'blockquote':
        inner = render_blocks(block[1])
        return '<blockquote>\n' + (inner + '\n' if inner else '') + '</blockquote>'
    if kind == 'list':
        _, ordered, start, items = block
        if ordered:
            open_tag = f'<ol start="{start}">'
            close_tag = '</ol>'
        else:
            open_tag, close_tag = '<ul>', '</ul>'
        lis = '\n'.join(f'<li>{render_inline(item)}</li>' for item in items)
        return f'{open_tag}\n{lis}\n{close_tag}'
    if kind == 'hr':
        return '<hr />'
    raise ValueError(f'unknown block {block!r}')


def render_blocks(blocks: list[tuple]) -> str:
    return '\n'.join(render_block(b) for b in blocks)


def to_html(text: str) -> str:
    html = render_blocks(parse_blocks(text))
    return html + '\n' if html else ''
