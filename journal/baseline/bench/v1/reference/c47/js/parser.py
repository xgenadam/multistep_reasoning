"""Recursive-descent parser over the lazy token stream."""

from __future__ import annotations

from .scanner import JSONError, Scanner, Token

_SCALARS = {'STRING', 'NUMBER', 'TRUE', 'FALSE', 'NULL'}


class _Parser:
    def __init__(self, text: str):
        self._tokens = Scanner(text).tokens()
        self.tok: Token = next(self._tokens)

    def advance(self) -> Token:
        tok = self.tok
        if tok.kind != 'EOF':
            self.tok = next(self._tokens)
        return tok

    def fail(self, what: str):
        tok = self.tok
        if tok.kind == 'EOF':
            raise JSONError(f'unexpected end of text, expected {what}', tok.line, tok.column)
        raise JSONError(f'expected {what}, got {tok.kind}', tok.line, tok.column)

    def expect(self, kind: str, what: str) -> Token:
        if self.tok.kind != kind:
            self.fail(what)
        return self.advance()

    def value(self):
        kind = self.tok.kind
        if kind in _SCALARS:
            return self.advance().value
        if kind == '[':
            return self.array()
        if kind == '{':
            return self.object()
        self.fail('a value')

    def array(self) -> list:
        self.advance()
        items = []
        if self.tok.kind == ']':
            self.advance()
            return items
        while True:
            items.append(self.value())
            if self.tok.kind == ',':
                self.advance()
                continue
            self.expect(']', "',' or ']'")
            return items

    def object(self) -> dict:
        self.advance()
        obj: dict = {}
        if self.tok.kind == '}':
            self.advance()
            return obj
        while True:
            key = self.expect('STRING', 'a string key').value
            self.expect(':', "':'")
            obj[key] = self.value()
            if self.tok.kind == ',':
                self.advance()
                continue
            self.expect('}', "',' or '}'")
            return obj


def loads(text: str):
    p = _Parser(text)
    result = p.value()
    if p.tok.kind != 'EOF':
        raise JSONError('extra data after the value', p.tok.line, p.tok.column)
    return result
