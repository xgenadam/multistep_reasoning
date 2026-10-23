"""Exact arithmetic evaluation with powers, variables, functions and positioned errors."""
import re
from fractions import Fraction

_TOKEN = re.compile(
    r'(?P<num>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)'
    r'|(?P<op>\*\*|[-+*/(),])|(?P<ws>[ \t]+)')

# name -> (minimum, maximum) argument count, maximum None for unlimited
_ARITY = {'abs': (1, 1), 'min': (1, None), 'max': (1, None)}
_FUNCTIONS = {'abs': abs, 'min': lambda *a: min(a), 'max': lambda *a: max(a)}


class CalcError(Exception):
    def __init__(self, message: str, position: int):
        super().__init__(f'{message} at position {position}')
        self.position = position


def _tokenize(expr: str) -> list[tuple[str, str, int]]:
    """(kind, text, position) tuples; kind is 'num', 'name', 'op', 'bad' or 'end'."""
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
    """Recursive descent into a tree of tuples:
    ('num', value) | ('var', name, pos) | ('call', name, pos, args) | ('neg', x)
    | (op, pos, a, b) for + - * / **.
    """

    def __init__(self, expr: str):
        self.tokens = _tokenize(expr)
        self.i = 0

    def peek(self):
        return self.tokens[self.i]

    def at_op(self, *ops):
        kind, text, _ = self.peek()
        return kind == 'op' and text in ops

    def take(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def fail(self):
        kind, text, pos = self.peek()
        what = 'unexpected end' if kind == 'end' else f'unexpected {text!r}'
        raise CalcError(what, pos)

    def expect(self, op):
        if not self.at_op(op):
            self.fail()
        self.take()

    def parse(self):
        tree = self.expr()
        if self.peek()[0] != 'end':
            self.fail()
        return tree

    def expr(self):
        left = self.term()
        while self.at_op('+', '-'):
            _, op, pos = self.take()
            left = (op, pos, left, self.term())
        return left

    def term(self):
        left = self.unary()
        while self.at_op('*', '/'):
            _, op, pos = self.take()
            left = (op, pos, left, self.unary())
        return left

    def unary(self):
        if self.at_op('-'):
            self.take()
            return ('neg', self.unary())
        return self.power()

    def power(self):
        base = self.primary()
        if self.at_op('**'):
            _, op, pos = self.take()
            return (op, pos, base, self.unary())
        return base

    def primary(self):
        kind, text, pos = self.peek()
        if kind == 'num':
            self.take()
            return ('num', Fraction(text))
        if kind == 'name':
            self.take()
            if not self.at_op('('):
                return ('var', text, pos)
            self.take()
            args = []
            if not self.at_op(')'):
                args.append(self.expr())
                while self.at_op(','):
                    self.take()
                    args.append(self.expr())
            self.expect(')')
            return ('call', text, pos, args)
        if self.at_op('('):
            self.take()
            inner = self.expr()
            self.expect(')')
            return inner
        self.fail()


def _eval(node, variables) -> Fraction:
    tag = node[0]
    if tag == 'num':
        return node[1]
    if tag == 'neg':
        return -_eval(node[1], variables)
    if tag == 'var':
        _, name, pos = node
        if variables is None or name not in variables:
            raise CalcError(f'unknown variable {name!r}', pos)
        return Fraction(variables[name])
    if tag == 'call':
        _, name, pos, args = node
        if name not in _ARITY:
            raise CalcError(f'unknown function {name!r}', pos)
        lo, hi = _ARITY[name]
        if len(args) < lo or (hi is not None and len(args) > hi):
            raise CalcError(f'wrong number of arguments to {name}', pos)
        values = [_eval(a, variables) for a in args]
        return Fraction(_FUNCTIONS[name](*values))
    op, pos, a, b = node
    left, right = _eval(a, variables), _eval(b, variables)
    if op == '+':
        return left + right
    if op == '-':
        return left - right
    if op == '*':
        return left * right
    if op == '/':
        if right == 0:
            raise CalcError('division by zero', pos)
        return left / right
    if left == 0 and right < 0:
        raise CalcError('division by zero', pos)
    return left ** int(right)


def evaluate(expr: str, variables=None) -> Fraction:
    return Fraction(_eval(_Parser(expr).parse(), variables))
