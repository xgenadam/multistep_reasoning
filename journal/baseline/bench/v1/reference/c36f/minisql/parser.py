"""Syntax tree classes and a recursive-descent parser."""
from dataclasses import dataclass, field

from .tokens import SQLSyntaxError, Token, tokenize

AGGREGATES = ('COUNT', 'SUM', 'AVG', 'MIN', 'MAX')


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
class Aggregate:
    func: str
    arg: Column | None

    @property
    def text(self) -> str:
        return f"{self.func}({'*' if self.arg is None else self.arg.name})"


@dataclass(frozen=True)
class Join:
    table: str
    left: Column
    right: Column


@dataclass(frozen=True)
class Select:
    columns: list | None
    table: str
    where: object = None
    order_by: list = field(default_factory=list)
    limit: int | None = None
    items: list = field(default_factory=list)
    join: Join | None = None
    group_by: list = field(default_factory=list)

    @property
    def grouped(self) -> bool:
        return bool(self.group_by) or any(isinstance(e, Aggregate) for e, _ in self.items)


def canonical(expr) -> str:
    return expr.text if isinstance(expr, Aggregate) else expr.name


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
        star_pos = self.tok.pos
        items = self.select_list()            # None for *, else [(expr, key, pos)]
        self.expect_kw('FROM')
        table = self.expect('IDENT', 'a table name').value
        join = None
        if self.is_kw('JOIN'):
            self.advance()
            other = self.expect('IDENT', 'a table name').value
            self.expect_kw('ON')
            left = self.ref()
            if not (self.tok.kind == 'OP' and self.tok.value == '='):
                self.fail('"="')
            self.advance()
            join = Join(other, left, self.ref())
        where = None
        if self.is_kw('WHERE'):
            self.advance()
            where = self.condition()
        group_by = []
        if self.is_kw('GROUP'):
            self.advance()
            self.expect_kw('BY')
            group_by.append(self.ref().name)
            while self.tok.kind == 'COMMA':
                self.advance()
                group_by.append(self.ref().name)
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

        grouped = bool(group_by) or any(isinstance(e, Aggregate) for e, _, _ in items or [])
        if grouped:
            if items is None:
                raise SQLSyntaxError('* cannot be used in a grouped query', star_pos)
            for expr, _key, pos in items:
                if isinstance(expr, Column) and expr.name not in group_by:
                    raise SQLSyntaxError(f'{expr.name!r} is not in GROUP BY', pos)
        else:
            for text, _desc, pos, is_agg in order_by:
                if is_agg:
                    raise SQLSyntaxError('aggregate in ORDER BY of an ungrouped query', pos)
        order_by = [(text, desc) for text, desc, _pos, _agg in order_by]
        columns = None if items is None else [key for _e, key, _p in items]
        plain = [] if items is None else [(e, key) for e, key, _p in items]
        return Select(columns, table, where, order_by, limit, plain, join, group_by)

    def select_list(self):
        if self.tok.kind == 'STAR':
            self.advance()
            return None
        items, keys = [], set()
        while True:
            pos = self.tok.pos
            expr = self.ref_or_aggregate()
            key = canonical(expr)
            if self.is_kw('AS'):
                self.advance()
                key = self.expect('IDENT', 'an alias').value
            if key in keys:
                raise SQLSyntaxError(f'output column {key!r} listed twice', pos)
            keys.add(key)
            items.append((expr, key, pos))
            if self.tok.kind != 'COMMA':
                return items
            self.advance()

    def ref(self) -> Column:
        first = self.expect('IDENT', 'a column name').value
        if self.tok.kind == 'DOT':
            self.advance()
            second = self.expect('IDENT', 'a column name').value
            return Column(f'{first}.{second}')
        return Column(first)

    def ref_or_aggregate(self):
        if self.is_kw(*AGGREGATES):
            func = self.advance().value
            self.expect('LPAREN', '"("')
            if func == 'COUNT' and self.tok.kind == 'STAR':
                self.advance()
                arg = None
            else:
                arg = self.ref()
            self.expect('RPAREN', '")"')
            return Aggregate(func, arg)
        return self.ref()

    def order_item(self):
        pos = self.tok.pos
        expr = self.ref_or_aggregate()
        descending = False
        if self.is_kw('ASC', 'DESC'):
            descending = self.advance().value == 'DESC'
        return (canonical(expr), descending, pos, isinstance(expr, Aggregate))

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
            return self.ref()
        if tok.kind in ('NUMBER', 'STRING'):
            self.advance()
            return Literal(tok.value)
        if tok.kind == 'KEYWORD' and tok.value in ('NULL', 'TRUE', 'FALSE'):
            self.advance()
            return Literal({'NULL': None, 'TRUE': True, 'FALSE': False}[tok.value])
        self.fail('a column name or a value')


def parse(sql: str) -> Select:
    return _Parser(sql).statement()
