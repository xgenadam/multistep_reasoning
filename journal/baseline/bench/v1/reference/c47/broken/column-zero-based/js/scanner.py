"""Tokenizer with 1-based line/column positions."""

from __future__ import annotations

import re
from typing import Iterator, NamedTuple


class JSONError(ValueError):
    def __init__(self, msg: str, line: int, column: int):
        super().__init__(f'{msg} at line {line} column {column}')
        self.msg = msg
        self.line = line
        self.column = column


class Token(NamedTuple):
    kind: str
    value: object
    line: int
    column: int


WHITESPACE = ' \t\n\r'
PUNCT = '{}[]:,'
NUMBER_CHARS = set('0123456789+-.eE')
NUMBER_RE = re.compile(r'-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?')
LITERALS = {'true': ('TRUE', True), 'false': ('FALSE', False), 'null': ('NULL', None)}
ESCAPES = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r',
           't': '\t'}
HEX = set('0123456789abcdefABCDEF')


class Scanner:
    """Lazy scanner: yields tokens one by one, so errors come in reading order."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.line_start = 0

    def where(self, pos: int) -> tuple[int, int]:
        """(line, column) of a position at or after the current line start."""
        return self.line, pos - self.line_start

    def error(self, msg: str, pos: int):
        line, col = self.where(pos)
        raise JSONError(msg, line, col)

    def tokens(self) -> Iterator[Token]:
        text, n = self.text, len(self.text)
        while True:
            while self.pos < n and text[self.pos] in WHITESPACE:
                if text[self.pos] == '\n':
                    self.line += 1
                    self.line_start = self.pos + 1
                self.pos += 1
            start = self.pos
            line, col = self.where(start)
            if start >= n:
                yield Token('EOF', None, line, col)
                return
            c = text[start]
            if c in PUNCT:
                self.pos += 1
                yield Token(c, None, line, col)
            elif c == '"':
                yield Token('STRING', self._string(), line, col)
            elif c == '-' or c.isdigit() and c.isascii():
                yield Token('NUMBER', self._number(), line, col)
            elif c.isascii() and c.isalpha():
                end = start
                while end < n and text[end].isascii() and text[end].isalpha():
                    end += 1
                word = text[start:end]
                if word not in LITERALS:
                    self.error('invalid literal', start)
                self.pos = end
                kind, value = LITERALS[word]
                yield Token(kind, value, line, col)
            else:
                self.error(f'unexpected character {c!r}', start)

    def _number(self):
        text, start = self.text, self.pos
        end = start
        while end < len(text) and text[end] in NUMBER_CHARS:
            end += 1
        run = text[start:end]
        m = NUMBER_RE.fullmatch(run)
        if not m:
            self.error('invalid number', start)
        self.pos = end
        if m.group(1) or m.group(2):
            return float(run)
        return int(run)

    def _hex4(self, at: int, backslash: int) -> int:
        digits = self.text[at:at + 4]
        if len(digits) != 4 or any(d not in HEX for d in digits):
            self.error('bad \\u escape', backslash)
        return int(digits, 16)

    def _string(self) -> str:
        text, n = self.text, len(self.text)
        opened = self.pos
        i = opened + 1
        out = []
        while True:
            if i >= n:
                self.error('unterminated string', opened)
            c = text[i]
            if c == '"':
                self.pos = i + 1
                return ''.join(out)
            if c < ' ':
                self.error('control character in string', i)
            if c != '\\':
                out.append(c)
                i += 1
                continue
            if i + 1 >= n:
                self.error('unterminated string', opened)
            e = text[i + 1]
            if e in ESCAPES:
                out.append(ESCAPES[e])
                i += 2
                continue
            if e != 'u':
                self.error(f'invalid escape \\{e}', i)
            code = self._hex4(i + 2, i)
            if 0xDC00 <= code <= 0xDFFF:
                self.error('lone low surrogate', i)
            if 0xD800 <= code <= 0xDBFF:
                j = i + 6
                if text[j:j + 2] != '\\u':
                    self.error('lone high surrogate', i)
                low = self._hex4(j + 2, j)
                if not 0xDC00 <= low <= 0xDFFF:
                    self.error('lone high surrogate', i)
                code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                i = j + 6
            else:
                i += 6
            out.append(chr(code))


def tokenize(text: str) -> list[Token]:
    return list(Scanner(text).tokens())
