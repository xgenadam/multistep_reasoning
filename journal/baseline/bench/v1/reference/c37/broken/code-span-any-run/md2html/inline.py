"""Inline markup: escapes, code spans, emphasis, links and images."""
import string

PUNCTUATION = set(string.punctuation)


def escape_html(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _run(text: str, i: int, ch: str) -> int:
    j = i
    while j < len(text) and text[j] == ch:
        j += 1
    return j - i


def _code_span(text: str, i: int):
    """(html, end) for a code span opening at i, else None."""
    width = _run(text, i, '`')
    j = i + width
    while j < len(text):
        if text[j] == '`':
            m = _run(text, j, '`')
            if m >= width:
                content = text[i + width:j]
                if (len(content) >= 2 and content[0] == ' ' and content[-1] == ' '
                        and content.strip()):
                    content = content[1:-1]
                return f'<code>{escape_html(content)}</code>', j + m
            j += m
        else:
            j += 1
    return None


def _link(text: str, i: int):
    """(label, url, title, end) for `[label](url "title")` with `[` at i, else None."""
    close = text.find(']', i + 1)
    if close == -1 or not text.startswith('(', close + 1):
        return None
    label = text[i + 1:close]
    j = close + 2
    k = j
    while k < len(text) and text[k] not in ' )':
        k += 1
    url = text[j:k]
    title = None
    if k < len(text) and text[k] == ' ':
        while k < len(text) and text[k] == ' ':
            k += 1
        if k >= len(text) or text[k] != '"':
            return None
        end_quote = text.find('"', k + 1)
        if end_quote == -1:
            return None
        title = text[k + 1:end_quote]
        k = end_quote + 1
        while k < len(text) and text[k] == ' ':
            k += 1
    if k >= len(text) or text[k] != ')':
        return None
    return label, url, title, k + 1


def _find_closer(text: str, start: int, delim: str) -> int:
    """Index of the closing delimiter for an opener ending at start, or -1."""
    ch = delim[0]
    k = start
    while k < len(text):
        if text[k] == '\\':
            k += 2
            continue
        if text.startswith(delim, k) and k > start and not text[k - 1].isspace():
            after = k + len(delim)
            ok = True
            if len(delim) == 1 and (text[k - 1] == ch or (after < len(text) and text[after] == ch)):
                ok = False
            if ch == '_' and after < len(text) and text[after].isalnum():
                ok = False
            if ok:
                return k
        k += 1
    return -1


def _emphasis(text: str, i: int):
    """(html, end) for emphasis opening at i, else None."""
    ch = text[i]
    if ch == '_' and i > 0 and text[i - 1].isalnum():
        return None
    for delim, tag in ((ch * 2, 'strong'), (ch, 'em')):
        if not text.startswith(delim, i):
            continue
        start = i + len(delim)
        if start >= len(text) or text[start].isspace():
            continue
        k = _find_closer(text, start, delim)
        if k != -1:
            return f'<{tag}>{render_inline(text[start:k])}</{tag}>', k + len(delim)
    return None


def render_inline(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '\\' and i + 1 < n and text[i + 1] in PUNCTUATION:
            out.append(escape_html(text[i + 1]))
            i += 2
            continue
        if c == '`':
            span = _code_span(text, i)
            if span:
                out.append(span[0])
                i = span[1]
            else:
                width = _run(text, i, '`')
                out.append('`' * width)
                i += width
            continue
        if c == '!' and text.startswith('[', i + 1):
            link = _link(text, i + 1)
            if link:
                alt, url, title, end = link
                attrs = f' title="{escape_html(title)}"' if title is not None else ''
                out.append(f'<img src="{escape_html(url)}" alt="{escape_html(alt)}"{attrs} />')
                i = end
                continue
        if c == '[':
            link = _link(text, i)
            if link:
                label, url, title, end = link
                attrs = f' title="{escape_html(title)}"' if title is not None else ''
                out.append(f'<a href="{escape_html(url)}"{attrs}>{render_inline(label)}</a>')
                i = end
                continue
        if c in '*_':
            em = _emphasis(text, i)
            if em:
                out.append(em[0])
                i = em[1]
                continue
        out.append(escape_html(c))
        i += 1
    return ''.join(out)
