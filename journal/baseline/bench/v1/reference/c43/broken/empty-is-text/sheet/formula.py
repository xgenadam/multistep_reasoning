"""Formula tokenizer, parser and evaluator."""
import re
from dataclasses import dataclass


class FormulaError(ValueError):
    """A formula that cannot be parsed."""


class ErrorValue(str):
    """An error shown in a cell; compares equal to its text."""

    def __repr__(self) -> str:
        return f'ErrorValue({str(self)!r})'


ERROR = ErrorValue('#ERROR!')
CYCLE = ErrorValue('#CYCLE!')

NAME_RE = re.compile(r'[A-Z][1-9][0-9]{0,2}')


def is_cell_name(name: str) -> bool:
    return bool(NAME_RE.fullmatch(name))


@dataclass(frozen=True)
class Num:
    value: int | float


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Unary:
    op: str
    operand: object


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object


def tokenize(source: str) -> list[tuple[str, object]]:
    tokens = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
        elif ch in '+-*/()':
            tokens.append(('op', ch))
            i += 1
        elif '0' <= ch <= '9':
            m = re.compile(r'[0-9]+').match(source, i)
            j = m.end()
            if j < n and source[j] == '.':
                frac = re.compile(r'[0-9]+').match(source, j + 1)
                if not frac:
                    raise FormulaError(f'digits expected after "." at {j}')
                j = frac.end()
                tokens.append(('num', float(source[i:j])))
            else:
                tokens.append(('num', int(source[i:j])))
            i = j
        elif ch.isascii() and ch.isalpha():
            m = re.compile(r'([A-Za-z]+)([0-9]*)').match(source, i)
            letters, digits = m.group(1), m.group(2)
            if not digits:
                raise FormulaError(f'unexpected word {letters!r}')
            name = (letters + digits).upper()
            if not is_cell_name(name):
                raise FormulaError(f'reference {name} is outside the sheet')
            tokens.append(('ref', name))
            i = m.end()
        else:
            raise FormulaError(f'unexpected character {ch!r} at {i}')
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expr(self):
        node = self.term()
        while self.peek() in (('op', '+'), ('op', '-')):
            node = BinOp(self.take()[1], node, self.term())
        return node

    def term(self):
        node = self.unary()
        while self.peek() in (('op', '*'), ('op', '/')):
            node = BinOp(self.take()[1], node, self.unary())
        return node

    def unary(self):
        kind, value = self.take()
        if kind == 'op' and value in '+-':
            return Unary(value, self.unary())
        if kind == 'num':
            return Num(value)
        if kind == 'ref':
            return Ref(value)
        if (kind, value) == ('op', '('):
            node = self.expr()
            if self.take() != ('op', ')'):
                raise FormulaError('")" expected')
            return node
        raise FormulaError('incomplete expression' if kind is None else f'unexpected {value!r}')


def parse_formula(source: str):
    tokens = tokenize(source)
    if not tokens:
        raise FormulaError('empty formula')
    parser = _Parser(tokens)
    tree = parser.expr()
    if parser.i != len(tokens):
        raise FormulaError(f'unexpected {parser.peek()[1]!r}')
    return tree


def references(tree) -> set[str]:
    if isinstance(tree, Ref):
        return {tree.name}
    if isinstance(tree, Unary):
        return references(tree.operand)
    if isinstance(tree, BinOp):
        return references(tree.left) | references(tree.right)
    return set()


def _numeric(*values):
    """The first error among the operands, #ERROR! for text, or None when all are numbers."""
    for v in values:
        if isinstance(v, ErrorValue):
            return v
    for v in values:
        if isinstance(v, str):
            return ERROR
    return None


def evaluate(tree, lookup):
    if isinstance(tree, Num):
        return tree.value
    if isinstance(tree, Ref):
        value = lookup(tree.name)
        return '' if value is None else value
    if isinstance(tree, Unary):
        value = evaluate(tree.operand, lookup)
        bad = _numeric(value)
        if bad is not None:
            return bad
        return -value if tree.op == '-' else value
    if isinstance(tree, BinOp):
        left = evaluate(tree.left, lookup)
        right = evaluate(tree.right, lookup)
        bad = _numeric(left, right)
        if bad is not None:
            return bad
        if tree.op == '+':
            return left + right
        if tree.op == '-':
            return left - right
        if tree.op == '*':
            return left * right
        if right == 0:
            return ERROR
        return left / right
    raise TypeError(f'not a formula tree: {tree!r}')
