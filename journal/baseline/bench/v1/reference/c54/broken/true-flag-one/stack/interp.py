"""Structure check, compilation to a tree, and execution."""

from __future__ import annotations

from .lexer import Token, tokenize


class StackError(Exception):
    def __init__(self, message: str, token: Token):
        text = str(token.value)
        super().__init__(f'{message}: {text} at line {token.line}, column {token.col}')
        self.word = text
        self.line = token.line
        self.col = token.col


class StackUnderflow(StackError):
    pass


class UnknownWord(StackError):
    pass


class DivisionByZero(StackError):
    pass


class ControlError(StackError):
    pass


class StepLimitExceeded(StackError):
    pass


def _div(a, b, tok):
    if b == 0:
        raise DivisionByZero('division by zero', tok)
    return a // b


def _mod(a, b, tok):
    if b == 0:
        raise DivisionByZero('division by zero', tok)
    return a % b


def _flag(cond: bool) -> int:
    return 1 if cond else 0


# name -> (items popped, function of (popped items, token) returning the items pushed)
BUILTINS = {
    '+': (2, lambda s, t: [s[0] + s[1]]),
    '-': (2, lambda s, t: [s[0] - s[1]]),
    '*': (2, lambda s, t: [s[0] * s[1]]),
    '/': (2, lambda s, t: [_div(s[0], s[1], t)]),
    'mod': (2, lambda s, t: [_mod(s[0], s[1], t)]),
    'negate': (1, lambda s, t: [-s[0]]),
    'abs': (1, lambda s, t: [abs(s[0])]),
    'dup': (1, lambda s, t: [s[0], s[0]]),
    'drop': (1, lambda s, t: []),
    'swap': (2, lambda s, t: [s[1], s[0]]),
    'over': (2, lambda s, t: [s[0], s[1], s[0]]),
    'rot': (3, lambda s, t: [s[1], s[2], s[0]]),
    '=': (2, lambda s, t: [_flag(s[0] == s[1])]),
    '<>': (2, lambda s, t: [_flag(s[0] != s[1])]),
    '<': (2, lambda s, t: [_flag(s[0] < s[1])]),
    '>': (2, lambda s, t: [_flag(s[0] > s[1])]),
    '0=': (1, lambda s, t: [_flag(s[0] == 0)]),
    'and': (2, lambda s, t: [s[0] & s[1]]),
    'or': (2, lambda s, t: [s[0] | s[1]]),
}
CONTROL = {'if', 'else', 'then', 'begin', 'until'}


def compile_tokens(tokens: list[Token]) -> list:
    """Check the control structure and build a tree of nodes.

    Nodes: ('num', value, tok), ('word', name, tok), ('if', then, else, tok),
    ('loop', body, until_tok).
    """
    root: list = []
    # Each open frame: [kind, opener token, node list being filled, if-node or None]
    frames: list = [['root', None, root, None]]
    for tok in tokens:
        top = frames[-1]
        if tok.kind == 'number':
            top[2].append(('num', tok.value, tok))
            continue
        name = tok.value
        if name == 'if':
            node = ['if', [], None, tok]
            top[2].append(node)
            frames.append(['if', tok, node[1], node])
        elif name == 'else':
            if top[0] != 'if' or top[3][2] is not None:
                raise ControlError('else without a matching if', tok)
            top[3][2] = []
            top[2] = top[3][2]
        elif name == 'then':
            if top[0] != 'if':
                raise ControlError('then without a matching if', tok)
            frames.pop()
        elif name == 'begin':
            node = ['loop', [], None]
            top[2].append(node)
            frames.append(['begin', tok, node[1], node])
        elif name == 'until':
            if top[0] != 'begin':
                raise ControlError('until without a matching begin', tok)
            top[3][2] = tok
            frames.pop()
        else:
            top[2].append(('word', name, tok))
    if len(frames) > 1:
        raise ControlError(f'{frames[-1][0]} is never closed', frames[-1][1])
    return root


class Interpreter:
    def __init__(self, max_steps: int = 100000):
        self.max_steps = max_steps
        self.stack: list[int] = []
        self.output: list[int] = []
        self._steps = 0

    def run(self, source: str) -> None:
        program = compile_tokens(tokenize(source))
        self._steps = 0
        self._exec(program)

    def _step(self, tok: Token) -> None:
        if self._steps >= self.max_steps:
            raise StepLimitExceeded('step limit exceeded', tok)
        self._steps += 1

    def _pop_flag(self, tok: Token) -> int:
        if not self.stack:
            raise StackUnderflow('stack underflow', tok)
        return self.stack.pop()

    def _exec(self, nodes: list) -> None:
        for node in nodes:
            kind = node[0]
            if kind == 'num':
                self._step(node[2])
                self.stack.append(node[1])
            elif kind == 'word':
                self._step(node[2])
                self._word(node[1], node[2])
            elif kind == 'if':
                _, then_body, else_body, tok = node
                self._step(tok)
                if self._pop_flag(tok):
                    self._exec(then_body)
                elif else_body is not None:
                    self._exec(else_body)
            else:
                _, body, until_tok = node
                while True:
                    self._exec(body)
                    self._step(until_tok)
                    if self._pop_flag(until_tok):
                        break

    def _word(self, name: str, tok: Token) -> None:
        if name == '.':
            self.output.append(self._pop_flag(tok))
            return
        if name == 'depth':
            self.stack.append(len(self.stack))
            return
        if name not in BUILTINS:
            raise UnknownWord('unknown word', tok)
        arity, fn = BUILTINS[name]
        if len(self.stack) < arity:
            raise StackUnderflow('stack underflow', tok)
        args = self.stack[len(self.stack) - arity:]
        result = fn(args, tok)
        del self.stack[len(self.stack) - arity:]
        self.stack.extend(result)


def evaluate(source: str) -> list[int]:
    interp = Interpreter()
    interp.run(source)
    return interp.stack
