"""Error classes and the tokenizer."""
import re
from typing import NamedTuple


class TemplateError(Exception):
    """Base class of every template error."""


class _LineError(TemplateError):
    def __init__(self, message: str, lineno: int):
        super().__init__(f'line {lineno}: {message}')
        self.message = message
        self.lineno = lineno


class TemplateSyntaxError(_LineError):
    """The template text is malformed."""


class TemplateRenderError(_LineError):
    """A tag failed while rendering."""


class TemplateNotFound(TemplateError):
    """A loader has no template of that name."""

    def __init__(self, name: str):
        super().__init__(f'template not found: {name}')
        self.name = name


class Token(NamedTuple):
    kind: str
    value: str
    lineno: int


_OPEN = re.compile(r'\{[{%#]')
_TAGS = {'{{': ('var', '}}'), '{%': ('block', '%}'), '{#': ('comment', '#}')}


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    pos, line, n = 0, 1, len(source)
    while pos < n:
        m = _OPEN.search(source, pos)
        start = m.start() if m else n
        if start > pos:
            text = source[pos:start]
            tokens.append(Token('text', text, line))
            line += text.count('\n')
        if not m:
            break
        kind, close = _TAGS[m.group()]
        end = source.find(close, start + 2)
        if end == -1:
            raise TemplateSyntaxError(f'unclosed {kind} tag', line)
        inner = source[start + 2:end]
        if kind != 'comment':
            tokens.append(Token(kind, inner.strip(), line))
        line += inner.count('\n')
        pos = end + 2
    return tokens
