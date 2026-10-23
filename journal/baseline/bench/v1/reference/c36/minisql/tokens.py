"""Exceptions and the tokenizer."""
from dataclasses import dataclass

KEYWORDS = frozenset({'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'ORDER', 'BY', 'ASC',
                      'DESC', 'LIMIT', 'IS', 'NULL', 'TRUE', 'FALSE'})
SINGLE = {'*': 'STAR', ',': 'COMMA', '(': 'LPAREN', ')': 'RPAREN'}


class SQLError(Exception):
    """Base of every minisql error."""


class SQLSyntaxError(SQLError):
    def __init__(self, message: str, pos: int):
        super().__init__(f'{message} at position {pos}')
        self.message = message
        self.pos = pos


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    pos: int


def _is_ident_start(ch: str) -> bool:
    return ch == '_' or ('a' <= ch <= 'z') or ('A' <= ch <= 'Z')


def _is_ident_char(ch: str) -> bool:
    return _is_ident_start(ch) or ch.isdigit() and ch.isascii()


def _digit(ch: str) -> bool:
    return '0' <= ch <= '9'


def _number(sql: str, i: int) -> tuple[Token, int]:
    start = i
    if sql[i] == '-':
        i += 1
    while i < len(sql) and _digit(sql[i]):
        i += 1
    is_float = False
    if i < len(sql) and sql[i] == '.':
        if i + 1 >= len(sql) or not _digit(sql[i + 1]):
            raise SQLSyntaxError('digits expected after "."', i)
        is_float = True
        i += 1
        while i < len(sql) and _digit(sql[i]):
            i += 1
    text = sql[start:i]
    value = float(text) if is_float else int(text)
    return Token('NUMBER', value, start), i


def _string(sql: str, i: int) -> tuple[Token, int]:
    start = i
    i += 1
    parts = []
    while True:
        if i >= len(sql):
            raise SQLSyntaxError('unterminated string', start)
        ch = sql[i]
        if ch == "'":
            if i + 1 < len(sql) and sql[i + 1] == "'":
                parts.append("'")
                i += 2
                continue
            return Token('STRING', ''.join(parts), start), i + 1
        parts.append(ch)
        i += 1


def tokenize(sql: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch.isspace():
            i += 1
        elif _is_ident_start(ch):
            j = i
            while j < n and _is_ident_char(sql[j]):
                j += 1
            word = sql[i:j]
            if word.upper() in KEYWORDS:
                tokens.append(Token('KEYWORD', word.upper(), i))
            else:
                tokens.append(Token('IDENT', word, i))
            i = j
        elif _digit(ch) or (ch == '-' and i + 1 < n and _digit(sql[i + 1])):
            tok, i = _number(sql, i)
            tokens.append(tok)
        elif ch == "'":
            tok, i = _string(sql, i)
            tokens.append(tok)
        elif ch in SINGLE:
            tokens.append(Token(SINGLE[ch], ch, i))
            i += 1
        elif ch in '<>!=':
            two = sql[i:i + 2]
            if two in ('<=', '>=', '!=', '<>'):
                tokens.append(Token('OP', '!=' if two == '<>' else two, i))
                i += 2
            elif ch in '<>=':
                tokens.append(Token('OP', ch, i))
                i += 1
            else:
                raise SQLSyntaxError(f'unexpected character {ch!r}', i)
        else:
            raise SQLSyntaxError(f'unexpected character {ch!r}', i)
    tokens.append(Token('EOF', None, n))
    return tokens
