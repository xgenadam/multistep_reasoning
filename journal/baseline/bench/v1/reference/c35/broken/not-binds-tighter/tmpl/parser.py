"""Turn a template into a tree of nodes, reporting every syntax error."""
import re
from dataclasses import dataclass, field

from .lexer import TemplateSyntaxError, Token, tokenize

KEYWORDS = {'and', 'or', 'not', 'in'}
COMPARISONS = {'==', '!=', '<', '<=', '>', '>='}
# filter name -> type of its required argument (None: takes no argument)
FILTER_ARGS = {
    'upper': None, 'lower': None, 'trim': None, 'length': None, 'first': None,
    'last': None, 'reverse': None, 'items': None,
    'join': str, 'default': object, 'truncate': int,
}


# ------------------------------------------------------------ expression nodes

@dataclass
class Literal:
    value: object


@dataclass
class Path:
    name: str
    segments: list = field(default_factory=list)


@dataclass
class Filter:
    expr: object
    name: str
    args: tuple = ()


@dataclass
class Compare:
    op: str
    left: object
    right: object


@dataclass
class Not:
    operand: object


@dataclass
class BoolOp:
    op: str
    left: object
    right: object


# ------------------------------------------------------------ template nodes

@dataclass
class Text:
    text: str


@dataclass
class Output:
    expr: object
    lineno: int


@dataclass
class If:
    branches: list          # [(condition, body, lineno)]
    else_body: list | None
    lineno: int


@dataclass
class For:
    name: str
    iterable: object
    body: list
    else_body: list | None
    lineno: int


# ------------------------------------------------------------ expressions

_EXPR_TOKEN = re.compile(r'''("[^"]*"|'[^']*')|(-?\d+)|(==|!=|<=|>=|<|>|\||:|\.)|([A-Za-z_][A-Za-z0-9_]*)''')


def _expr_tokens(text: str, lineno: int) -> list[tuple[str, object]]:
    out, pos = [], 0
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return out
        m = _EXPR_TOKEN.match(text, pos)
        if not m:
            raise TemplateSyntaxError(f'unexpected character {text[pos]!r} in expression', lineno)
        s, i, op, name = m.groups()
        if s is not None:
            out.append(('str', s[1:-1]))
        elif i is not None:
            out.append(('int', int(i)))
        elif op is not None:
            out.append(('op', op))
        else:
            out.append(('kw' if name in KEYWORDS else 'name', name))
        pos = m.end()


class _ExprParser:
    def __init__(self, text: str, lineno: int):
        self.lineno = lineno
        self.tokens = _expr_tokens(text, lineno)
        self.i = 0

    def error(self, message: str):
        raise TemplateSyntaxError(message, self.lineno)

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def finish(self, node):
        if self.i < len(self.tokens):
            self.error(f'unexpected {self.tokens[self.i][1]!r} in expression')
        return node

    # conditions
    def condition(self):
        return self.finish(self.or_())

    def or_(self):
        left = self.and_()
        while self.peek() == ('kw', 'or'):
            self.take()
            left = BoolOp('or', left, self.and_())
        return left

    def and_(self):
        left = self.not_()
        while self.peek() == ('kw', 'and'):
            self.take()
            left = BoolOp('and', left, self.not_())
        return left

    def not_(self):
        if self.peek() == ('kw', 'not'):
            self.take()
            operand = self.value()
            kind, op = self.peek()
            if kind == 'op' and op in COMPARISONS:
                self.take()
                return Compare(op, Not(operand), self.value())
            return Not(operand)
        return self.comparison()

    def comparison(self):
        left = self.value()
        kind, op = self.peek()
        if kind == 'op' and op in COMPARISONS:
            self.take()
            return Compare(op, left, self.value())
        return left

    # value expressions
    def value_only(self):
        return self.finish(self.value())

    def value(self):
        node = self.atom()
        while self.peek() == ('op', '|'):
            self.take()
            kind, name = self.take()
            if kind != 'name':
                self.error('expected a filter name after |')
            if name not in FILTER_ARGS:
                self.error(f'unknown filter {name!r}')
            wanted = FILTER_ARGS[name]
            args = ()
            if self.peek() == ('op', ':'):
                self.take()
                kind, arg = self.take()
                if kind not in ('str', 'int'):
                    self.error(f'filter {name!r} needs a literal argument')
                if wanted is None:
                    self.error(f'filter {name!r} takes no argument')
                if wanted is not object and not isinstance(arg, wanted):
                    self.error(f'filter {name!r} needs a {wanted.__name__} argument')
                if name == 'truncate' and arg < 0:
                    self.error('truncate needs a length of 0 or more')
                args = (arg,)
            elif wanted is not None:
                self.error(f'filter {name!r} needs an argument')
            node = Filter(node, name, args)
        return node

    def atom(self):
        kind, value = self.take()
        if kind in ('str', 'int'):
            return Literal(value)
        if kind != 'name':
            self.error('expected a value' if kind is None else f'unexpected {value!r}')
        path = Path(value)
        while self.peek() == ('op', '.'):
            self.take()
            kind, seg = self.take()
            if kind == 'int' and seg >= 0:
                path.segments.append(seg)
            elif kind == 'name':
                path.segments.append(seg)
            else:
                self.error('expected a name or index after .')
        return path


def parse_value(text: str, lineno: int):
    return _ExprParser(text, lineno).value_only()


def parse_condition(text: str, lineno: int):
    return _ExprParser(text, lineno).condition()


# ------------------------------------------------------------ statements

_FOR = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+)', re.S)


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    def body(self, stop: tuple[str, ...]):
        """Nodes up to a block tag whose word is in stop: (nodes, word, rest, token)."""
        nodes = []
        while self.i < len(self.tokens):
            tok = self.tokens[self.i]
            self.i += 1
            if tok.kind == 'text':
                nodes.append(Text(tok.value))
            elif tok.kind == 'var':
                nodes.append(Output(parse_value(tok.value, tok.lineno), tok.lineno))
            else:
                parts = tok.value.split(None, 1)
                word = parts[0] if parts else ''
                rest = parts[1].strip() if len(parts) > 1 else ''
                if word in stop:
                    if word in ('else', 'endif', 'endfor') and rest:
                        raise TemplateSyntaxError(f'{word!r} takes nothing after it', tok.lineno)
                    return nodes, word, rest, tok
                if word == 'for':
                    nodes.append(self.parse_for(rest, tok))
                elif word == 'if':
                    nodes.append(self.parse_if(rest, tok))
                elif word in ('elif', 'else', 'endif', 'endfor'):
                    raise TemplateSyntaxError(f'unexpected {word!r}', tok.lineno)
                else:
                    raise TemplateSyntaxError(f'unknown statement {word!r}', tok.lineno)
        return nodes, None, None, None

    def parse_for(self, rest: str, tok: Token) -> For:
        m = _FOR.fullmatch(rest)
        if not m or m.group(1) in KEYWORDS:
            raise TemplateSyntaxError('expected "for NAME in EXPRESSION"', tok.lineno)
        iterable = parse_value(m.group(2), tok.lineno)
        body, word, _, _ = self.body(('else', 'endfor'))
        else_body = None
        if word == 'else':
            else_body, word, _, _ = self.body(('endfor',))
        if word is None:
            raise TemplateSyntaxError("unclosed 'for'", tok.lineno)
        return For(m.group(1), iterable, body, else_body, tok.lineno)

    def parse_if(self, rest: str, tok: Token) -> If:
        branches = []
        cond, line = rest, tok.lineno
        while True:
            condition = parse_condition(cond, line)
            body, word, cond, end_tok = self.body(('elif', 'else', 'endif'))
            branches.append((condition, body, line))
            if word is None:
                raise TemplateSyntaxError("unclosed 'if'", tok.lineno)
            if word != 'elif':
                break
            line = end_tok.lineno
        else_body = None
        if word == 'else':
            else_body, word, _, _ = self.body(('endif',))
            if word is None:
                raise TemplateSyntaxError("unclosed 'if'", tok.lineno)
        return If(branches, else_body, tok.lineno)


def parse(source: str) -> list:
    return _Parser(tokenize(source)).body(())[0]
