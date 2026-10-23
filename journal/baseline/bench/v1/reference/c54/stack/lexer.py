"""Whitespace tokenizer with # comments."""

from __future__ import annotations

import re
from typing import NamedTuple

_NUMBER = re.compile(r'-?[0-9]+', re.ASCII)
_TOKEN = re.compile(r'\S+')


class Token(NamedTuple):
    kind: str
    value: object
    line: int
    col: int


def tokenize(source: str) -> list[Token]:
    tokens = []
    for line_no, line in enumerate(source.split('\n'), 1):
        for m in _TOKEN.finditer(line):
            text = m.group()
            if text.startswith('#'):
                break
            if _NUMBER.fullmatch(text):
                tokens.append(Token('number', int(text), line_no, m.start() + 1))
            else:
                tokens.append(Token('word', text.lower(), line_no, m.start() + 1))
    return tokens
