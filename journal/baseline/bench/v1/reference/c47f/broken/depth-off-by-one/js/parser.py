"""Recursive-descent parser over the lazy token stream."""

from __future__ import annotations

from .scanner import JSONError, Scanner, Token

_SCALARS = {'STRING', 'NUMBER', 'TRUE', 'FALSE', 'NULL'}


_POLICIES = ('last', 'first', 'error')


class _Parser:
    def __init__(self, text: str, duplicate_keys: str, max_depth, allow_nan: bool):
        self.duplicate_keys = duplicate_keys
        self.max_depth = max_depth
        self.depth = 0
        self._tokens = Scanner(text, allow_nan).tokens()
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
        if kind in ('[', '{'):
            if self.max_depth is not None and self.depth > self.max_depth:
                raise JSONError(f'nesting deeper than {self.max_depth}',
                                self.tok.line, self.tok.column)
            self.depth += 1
            result = self.array() if kind == '[' else self.object()
            self.depth -= 1
            return result
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
            key_tok = self.expect('STRING', 'a string key')
            key = key_tok.value
            repeated = key in obj
            if repeated and self.duplicate_keys == 'error':
                raise JSONError(f'duplicate key {key!r}', key_tok.line, key_tok.column)
            self.expect(':', "':'")
            value = self.value()
            if not (repeated and self.duplicate_keys == 'first'):
                obj[key] = value
            if self.tok.kind == ',':
                self.advance()
                continue
            self.expect('}', "',' or '}'")
            return obj


def loads(text: str, *, duplicate_keys: str = 'last', max_depth=None,
          allow_nan: bool = False):
    if duplicate_keys not in _POLICIES:
        raise ValueError(f'duplicate_keys must be one of {_POLICIES}')
    if max_depth is not None and (not isinstance(max_depth, int) or max_depth < 1):
        raise ValueError('max_depth must be None or an int >= 1')
    p = _Parser(text, duplicate_keys, max_depth, allow_nan)
    result = p.value()
    if p.tok.kind != 'EOF':
        raise JSONError('extra data after the value', p.tok.line, p.tok.column)
    return result
