"""Syntax tree classes and a recursive-descent parser."""
from dataclasses import dataclass, field

from .tokens import SQLSyntaxError, Token, tokenize


@dataclass(frozen=True)
class Column:
    name: str


@dataclass(frozen=True)
class Literal:
    value: object


@dataclass(frozen=True)
class Compare:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class And:
    left: object
    right: object


@dataclass(frozen=True)
class Or:
    left: object
    right: object


@dataclass(frozen=True)
class Not:
    operand: object


@dataclass(frozen=True)
class IsNull:
    operand: object
    negated: bool


@dataclass(frozen=True)
class Select:
    columns: list | None
    table: str
    where: object = None
    order_by: list = field(default_factory=list)
    limit: int | None = None


class _Parser:
    def __init__(self, sql: str):
        self.tokens = tokenize(sql)
        self.i = 0

    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def advance(self) -> Token:
        tok = self.tokens[self.i]
        if tok.kind != 'EOF':
            self.i += 1
        return tok

    def fail(self, what: str):
        tok = self.tok
        found = 'end of input' if tok.kind == 'EOF' else repr(tok.value)
        raise SQLSyntaxError(f'expected {what}, found {found}', tok.pos)

    def is_kw(self, *words: str) -> bool:
        return self.tok.kind == 'KEYWORD' and self.tok.value in words

    def expect_kw(self, word: str) -> Token:
        if not self.is_kw(word):
            self.fail(word)
        return self.advance()

    def expect(self, kind: str, what: str) -> Token:
        if self.tok.kind != kind:
            self.fail(what)
        return self.advance()

    # statement ---------------------------------------------------------
    def statement(self) -> Select:
        self.expect_kw('SELECT')
        columns = self.select_list()
        self.expect_kw('FROM')
        table = self.expect('IDENT', 'a table name').value
        where = None
        if self.is_kw('WHERE'):
            self.advance()
            where = self.condition()
        order_by = []
        if self.is_kw('ORDER'):
            self.advance()
            self.expect_kw('BY')
            order_by.append(self.order_item())
            while self.tok.kind == 'COMMA':
                self.advance()
                order_by.append(self.order_item())
        limit = None
        if self.is_kw('LIMIT'):
            self.advance()
            tok = self.tok
            if tok.kind != 'NUMBER' or not isinstance(tok.value, int) or tok.value < 0:
                self.fail('a non-negative integer')
            limit = self.advance().value
        if self.tok.kind != 'EOF':
            self.fail('end of statement')
        return Select(columns, table, where, order_by, limit)

    def select_list(self):
        if self.tok.kind == 'STAR':
            self.advance()
            return None
        names = []
        while True:
            tok = self.expect('IDENT', 'a column name')
            if tok.value in names:
                raise SQLSyntaxError(f'column {tok.value!r} listed twice', tok.pos)
            names.append(tok.value)
            if self.tok.kind != 'COMMA':
                return names
            self.advance()

    def order_item(self) -> tuple[str, bool]:
        name = self.expect('IDENT', 'a column name').value
        descending = False
        if self.is_kw('ASC', 'DESC'):
            descending = self.advance().value == 'DESC'
        return (name, descending)

    # conditions --------------------------------------------------------
    def condition(self):
        left = self.conjunction()
        while self.is_kw('OR'):
            self.advance()
            left = Or(left, self.conjunction())
        return left

    def conjunction(self):
        left = self.negation()
        while self.is_kw('AND'):
            self.advance()
            left = And(left, self.negation())
        return left

    def negation(self):
        if self.is_kw('NOT'):
            self.advance()
            return Not(self.negation())
        return self.predicate()

    def predicate(self):
        if self.tok.kind == 'LPAREN':
            self.advance()
            inner = self.condition()
            self.expect('RPAREN', '")"')
            return inner
        left = self.operand()
        if self.tok.kind == 'OP':
            op = self.advance().value
            return Compare(op, left, self.operand())
        if self.is_kw('IS'):
            self.advance()
            negated = False
            if self.is_kw('NOT'):
                self.advance()
                negated = True
            self.expect_kw('NULL')
            return IsNull(left, negated)
        self.fail('a comparison operator or IS')

    def operand(self):
        tok = self.tok
        if tok.kind == 'IDENT':
            self.advance()
            return Column(tok.value)
        if tok.kind in ('NUMBER', 'STRING'):
            self.advance()
            return Literal(tok.value)
        if tok.kind == 'KEYWORD' and tok.value in ('NULL', 'TRUE', 'FALSE'):
            self.advance()
            return Literal({'NULL': None, 'TRUE': True, 'FALSE': False}[tok.value])
        self.fail('a column name or a value')


def parse(sql: str) -> Select:
    return _Parser(sql).statement()
