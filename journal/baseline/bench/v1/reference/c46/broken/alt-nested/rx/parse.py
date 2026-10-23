"""Pattern parser: a recursive-descent parser from pattern text to an AST."""

from __future__ import annotations

from dataclasses import dataclass


class RegexError(ValueError):
    def __init__(self, message: str, position: int):
        super().__init__(f'{message} at position {position}')
        self.message = message
        self.position = position


@dataclass(frozen=True)
class Empty:
    pass


@dataclass(frozen=True)
class Literal:
    char: str


@dataclass(frozen=True)
class AnyChar:
    pass


@dataclass(frozen=True)
class CharClass:
    items: tuple
    negated: bool = False

    def matches(self, c: str) -> bool:
        hit = any(lo <= c <= hi for lo, hi in self.items)
        return hit != self.negated


@dataclass(frozen=True)
class Concat:
    items: tuple


@dataclass(frozen=True)
class Alt:
    options: tuple


@dataclass(frozen=True)
class Star:
    node: object


@dataclass(frozen=True)
class Plus:
    node: object


@dataclass(frozen=True)
class Optional:
    node: object


@dataclass(frozen=True)
class Group:
    node: object


_QUANT = {'*': Star, '+': Plus, '?': Optional}


class _Parser:
    def __init__(self, pattern: str):
        self.p = pattern
        self.i = 0

    def _peek(self):
        return self.p[self.i] if self.i < len(self.p) else None

    def parse(self):
        node = self._alt()
        if self.i < len(self.p):  # only a ')' stops _alt early
            raise RegexError('unmatched )', self.i)
        return node

    def _alt(self):
        left = self._seq()
        if self._peek() == '|':
            self.i += 1
            return Alt((left, self._alt()))
        return left

    def _seq(self):
        items = []
        while self._peek() is not None and self._peek() not in '|)':
            if self._peek() in _QUANT:
                raise RegexError('nothing to repeat', self.i)
            atom = self._atom()
            if self._peek() is not None and self._peek() in _QUANT:
                atom = _QUANT[self._peek()](atom)
                self.i += 1
                if self._peek() is not None and self._peek() in _QUANT:
                    raise RegexError('multiple repeat', self.i)
            items.append(atom)
        if not items:
            return Empty()
        return items[0] if len(items) == 1 else Concat(tuple(items))

    def _atom(self):
        c = self.p[self.i]
        if c == '(':
            opened = self.i
            self.i += 1
            inner = self._alt()
            if self._peek() != ')':
                raise RegexError('unclosed (', opened)
            self.i += 1
            return Group(inner)
        if c == '[':
            return self._class()
        if c == '.':
            self.i += 1
            return AnyChar()
        if c == '\\':
            return Literal(self._escaped())
        self.i += 1
        return Literal(c)

    def _escaped(self) -> str:
        if self.i + 1 >= len(self.p):
            raise RegexError('trailing backslash', self.i)
        ch = self.p[self.i + 1]
        self.i += 2
        return ch

    def _class_char(self, opened: int) -> str:
        if self.i >= len(self.p):
            raise RegexError('unclosed [', opened)
        if self.p[self.i] == '\\':
            return self._escaped()
        ch = self.p[self.i]
        self.i += 1
        return ch

    def _class(self):
        opened = self.i
        self.i += 1
        negated = False
        if self._peek() == '^':
            negated = True
            self.i += 1
        items = []
        while True:
            c = self._peek()
            if c is None:
                raise RegexError('unclosed [', opened)
            if c == ']':
                if not items:
                    raise RegexError('empty class', opened)
                self.i += 1
                return CharClass(tuple(items), negated)
            lo_pos = self.i
            lo = self._class_char(opened)
            if (self._peek() == '-' and self.i + 1 < len(self.p)
                    and self.p[self.i + 1] != ']'):
                self.i += 1
                hi = self._class_char(opened)
                if lo > hi:
                    raise RegexError('bad range', lo_pos)
                items.append((lo, hi))
            else:
                items.append((lo, lo))


def parse(pattern: str):
    return _Parser(pattern).parse()
