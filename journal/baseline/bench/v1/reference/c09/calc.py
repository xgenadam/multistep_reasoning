"""Exact arithmetic evaluation with positioned errors."""
import re
from fractions import Fraction

_TOKEN = re.compile(r'(?P<num>\d+(?:\.\d+)?)|(?P<op>[-+*/()])|(?P<ws>[ \t]+)')


class CalcError(Exception):
    def __init__(self, message: str, position: int):
        super().__init__(f'{message} at position {position}')
        self.position = position


def _tokenize(expr: str) -> list[tuple[str, str, int]]:
    """(kind, text, position) tuples; kind is 'num', 'op', 'bad' or 'end'."""
    tokens, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            tokens.append(('bad', expr[pos], pos))
            break
        if m.lastgroup != 'ws':
            tokens.append((m.lastgroup, m.group(), pos))
        pos = m.end()
    tokens.append(('end', '', len(expr)))
    return tokens


class _Parser:
    """Recursive descent into a tree of tuples: ('num', value) | ('neg', x) | (op, pos, a, b)."""

    def __init__(self, expr: str):
        self.tokens = _tokenize(expr)
        self.i = 0

    def peek(self):
        return self.tokens[self.i]

    def take(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def fail(self):
        kind, text, pos = self.peek()
        what = 'unexpected end' if kind == 'end' else f'unexpected {text!r}'
        raise CalcError(what, pos)

    def parse(self):
        tree = self.expr()
        if self.peek()[0] != 'end':
            self.fail()
        return tree

    def expr(self):
        left = self.term()
        while self.peek()[1] in ('+', '-') and self.peek()[0] == 'op':
            _, op, pos = self.take()
            left = (op, pos, left, self.term())
        return left

    def term(self):
        left = self.unary()
        while self.peek()[1] in ('*', '/') and self.peek()[0] == 'op':
            _, op, pos = self.take()
            left = (op, pos, left, self.unary())
        return left

    def unary(self):
        if self.peek()[:2] == ('op', '-'):
            self.take()
            return ('neg', self.unary())
        return self.primary()

    def primary(self):
        kind, text, _ = self.peek()
        if kind == 'num':
            self.take()
            return ('num', Fraction(text))
        if (kind, text) == ('op', '('):
            self.take()
            inner = self.expr()
            if self.peek()[:2] != ('op', ')'):
                self.fail()
            self.take()
            return inner
        self.fail()


def _eval(node) -> Fraction:
    tag = node[0]
    if tag == 'num':
        return node[1]
    if tag == 'neg':
        return -_eval(node[1])
    op, pos, a, b = node
    left, right = _eval(a), _eval(b)
    if op == '+':
        return left + right
    if op == '-':
        return left - right
    if op == '*':
        return left * right
    if right == 0:
        raise CalcError('division by zero', pos)
    return left / right


def evaluate(expr: str) -> Fraction:
    return Fraction(_eval(_Parser(expr).parse()))
