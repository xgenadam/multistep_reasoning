"""Formula tokenizer, parser and evaluator."""
import re
from dataclasses import dataclass


class FormulaError(ValueError):
    """A formula that cannot be parsed."""


class ErrorValue(str):
    """An error shown in a cell; compares equal to its text."""

    def __repr__(self) -> str:
        return f'ErrorValue({str(self)!r})'


DIV0 = ErrorValue('#DIV/0!')
VALUE = ErrorValue('#VALUE!')
REF = ErrorValue('#REF!')
CYCLE = ErrorValue('#CYCLE!')

FUNCTIONS = ('SUM', 'AVG', 'MIN', 'MAX')
NAME_RE = re.compile(r'[A-Z][1-9][0-9]{0,2}')
DIGITS = re.compile(r'[0-9]+')
WORD = re.compile(r'([A-Za-z]+)([0-9]*)')


def is_cell_name(name: str) -> bool:
    return bool(NAME_RE.fullmatch(name))


def row_major(name: str) -> tuple[int, str]:
    return (int(name[1:]), name[0])


@dataclass(frozen=True)
class Num:
    value: int | float


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Range:
    start: str
    end: str

    @property
    def inside(self) -> bool:
        return is_cell_name(self.start) and is_cell_name(self.end)

    def cells(self) -> list[str]:
        """Every cell of the rectangle in row-major order (both corners must be inside)."""
        (r1, c1), (r2, c2) = row_major(self.start), row_major(self.end)
        rows = range(min(r1, r2), max(r1, r2) + 1)
        cols = [chr(c) for c in range(ord(min(c1, c2)), ord(max(c1, c2)) + 1)]
        return [f'{c}{r}' for r in rows for c in cols]


@dataclass(frozen=True)
class Unary:
    op: str
    operand: object


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Call:
    func: str
    args: tuple


def tokenize(source: str) -> list[tuple[str, object]]:
    tokens = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
        elif ch in '+-*/(),:':
            tokens.append(('op', ch))
            i += 1
        elif '0' <= ch <= '9':
            j = DIGITS.match(source, i).end()
            if j < n and source[j] == '.':
                frac = DIGITS.match(source, j + 1)
                if not frac:
                    raise FormulaError(f'digits expected after "." at {j}')
                j = frac.end()
                tokens.append(('num', float(source[i:j])))
            else:
                tokens.append(('num', int(source[i:j])))
            i = j
        elif ch.isascii() and ch.isalpha():
            m = WORD.match(source, i)
            letters, digits = m.group(1), m.group(2)
            if digits:
                tokens.append(('ref', (letters + digits).upper()))
            else:
                name = letters.upper()
                if name not in FUNCTIONS:
                    raise FormulaError(f'unknown function {letters!r}')
                tokens.append(('func', name))
            i = m.end()
        else:
            raise FormulaError(f'unexpected character {ch!r} at {i}')
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self, ahead: int = 0):
        j = self.i + ahead
        return self.tokens[j] if j < len(self.tokens) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, value: str):
        if self.take() != ('op', value):
            raise FormulaError(f'{value!r} expected')

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
        if kind == 'func':
            return self.call(value)
        if (kind, value) == ('op', '('):
            node = self.expr()
            self.expect(')')
            return node
        raise FormulaError('incomplete expression' if kind is None else f'unexpected {value!r}')

    def call(self, func: str):
        self.expect('(')
        args = [self.arg()]
        while self.peek() == ('op', ','):
            self.take()
            args.append(self.arg())
        self.expect(')')
        return Call(func, tuple(args))

    def arg(self):
        if self.peek()[0] == 'ref' and self.peek(1) == ('op', ':'):
            start = self.take()[1]
            self.take()
            kind, end = self.take()
            if kind != 'ref':
                raise FormulaError('a reference is expected after ":"')
            return Range(start, end)
        return self.expr()


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
        return {tree.name} if is_cell_name(tree.name) else set()
    if isinstance(tree, Range):
        return set(tree.cells()) if tree.inside else set()
    if isinstance(tree, Unary):
        return references(tree.operand)
    if isinstance(tree, BinOp):
        return references(tree.left) | references(tree.right)
    if isinstance(tree, Call):
        found = set()
        for arg in tree.args:
            found |= references(arg)
        return found
    return set()


def _numeric(*values):
    """The leftmost error among the operands, #VALUE! for text, or None when all are numbers."""
    for v in values:
        if isinstance(v, ErrorValue):
            return v
    for v in values:
        if isinstance(v, str):
            return VALUE
    return None


def _collect(arg, lookup, numbers: list):
    """Add the argument's numbers to `numbers`; return an error value or None."""
    if isinstance(arg, Ref):
        arg = Range(arg.name, arg.name)
    if isinstance(arg, Range):
        if not arg.inside:
            return REF
        for cell in arg.cells():
            value = lookup(cell)
            if isinstance(value, ErrorValue):
                return value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numbers.append(value)
        return None
    value = evaluate(arg, lookup)
    if isinstance(value, ErrorValue):
        return value
    if isinstance(value, str):
        return VALUE
    numbers.append(value)
    return None


def _call(tree: Call, lookup):
    numbers: list = []
    for arg in tree.args:
        error = _collect(arg, lookup, numbers)
        if error is not None:
            return error
    if tree.func == 'SUM':
        total = sum(numbers)
        return total if all(isinstance(v, int) for v in numbers) else float(total)
    if tree.func == 'AVG':
        return sum(numbers) / len(numbers) if numbers else DIV0
    if not numbers:
        return 0
    return min(numbers) if tree.func == 'MIN' else max(numbers)


def evaluate(tree, lookup):
    if isinstance(tree, Num):
        return tree.value
    if isinstance(tree, Ref):
        if not is_cell_name(tree.name):
            return REF
        value = lookup(tree.name)
        return 0 if value is None else value
    if isinstance(tree, Call):
        return _call(tree, lookup)
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
            return DIV0
        return left / right
    raise TypeError(f'not a formula tree: {tree!r}')
