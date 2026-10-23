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
            open_tag = '<ol>' if start == 1 else f'<ol start="{start}">'
            close_tag = '</ol>'
        else:
            open_tag, close_tag = '<ul>', '</ul>'
        lis = '\n'.join(_item(text, children) for text, children in items)
        return f'{open_tag}\n{lis}\n{close_tag}'
    if kind == 'table':
        return _table(block)
    if kind == 'hr':
        return '<hr />'
    raise ValueError(f'unknown block {block!r}')


def _item(text: str, children: list[tuple]) -> str:
    if not children:
        return f'<li>{render_inline(text)}</li>'
    return f'<li>{render_inline(text)}\n{render_blocks(children)}\n</li>'


def _cell(tag: str, align, text: str) -> str:
    attr = f' align="{align}"' if align else ''
    return f'<{tag}{attr}>{render_inline(text)}</{tag}>'


def _table(block: tuple) -> str:
    _, aligns, header, rows = block
    out = ['<table>', '<thead>', '<tr>']
    out += [_cell('th', a, h) for a, h in zip(aligns, header)]
    out += ['</tr>', '</thead>']
    if rows:
        out.append('<tbody>')
        for row in rows:
            out.append('<tr>')
            out += [_cell('td', a, c) for a, c in zip(aligns, row)]
            out.append('</tr>')
        out.append('</tbody>')
    out.append('</table>')
    return '\n'.join(out)


def render_blocks(blocks: list[tuple]) -> str:
    return '\n'.join(render_block(b) for b in blocks)


def to_html(text: str) -> str:
    html = render_blocks(parse_blocks(text))
    return html + '\n' if html else ''
