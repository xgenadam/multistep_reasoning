"""Structure check, compilation to a tree, and execution."""

from __future__ import annotations

import sys

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


class CallDepthExceeded(StackError):
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
    return -1 if cond else 0


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
RESERVED = set(BUILTINS) | CONTROL | {'.', 'depth', ':', ';'}


def compile_tokens(tokens: list[Token]) -> list:
    """Check the control structure and build a tree of nodes.

    Nodes: ('num', value, tok), ('word', name, tok), ('if', then, else, tok),
    ('loop', body, until_tok), ('def', name, body).
    """
    root: list = []
    # Each open frame: [kind, opener token, node list being filled, if-node or None]
    frames: list = [['root', None, root, None]]
    pending_name = None          # the ':' token whose name is the next token
    for tok in tokens:
        top = frames[-1]
        if pending_name is not None:
            if tok.kind != 'word' or tok.value in RESERVED:
                raise ControlError('bad name for a definition', tok)
            node = ['def', tok.value, []]
            top[2].append(node)
            frames.append(['def', pending_name, node[2], node])
            pending_name = None
            continue
        if tok.kind == 'number':
            top[2].append(('num', tok.value, tok))
            continue
        name = tok.value
        if name == ':':
            if len(frames) > 1:
                raise ControlError(': inside another structure', tok)
            pending_name = tok
        elif name == ';':
            if top[0] != 'def':
                raise ControlError('; without a matching :', tok)
            frames.pop()
        elif name == 'if':
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
    if pending_name is not None:
        raise ControlError(': without a name', pending_name)
    if len(frames) > 1:
        raise ControlError(f'{frames[-1][0]} is never closed', frames[-1][1])
    return root


class Interpreter:
    def __init__(self, max_steps: int = 100000, max_depth: int = 100):
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.stack: list[int] = []
        self.output: list[int] = []
        self._words: dict[str, list] = {}
        self._steps = 0
        self._depth = 0

    def defined(self) -> list[str]:
        return sorted(self._words)

    def run(self, source: str) -> None:
        program = compile_tokens(tokenize(source))
        self._steps = 0
        self._depth = 0
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
            elif kind == 'def':
                snapshot = dict(self._words)
                self._words[node[1]] = [('scope', snapshot, node[2])]
            elif kind == 'scope':
                saved = self._words
                self._words = node[1]
                try:
                    self._exec(node[2])
                finally:
                    self._words = saved
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
        if name in self._words:
            if self._depth >= self.max_depth:
                raise CallDepthExceeded('call depth exceeded', tok)
            self._depth += 1
            try:
                self._exec(self._words[name])
            finally:
                self._depth -= 1
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


def repl(infile, outfile, interp: Interpreter | None = None) -> int:
    interp = interp if interp is not None else Interpreter()
    for line in infile:
        before = len(interp.output)
        try:
            interp.run(line)
        except StackError as e:
            outfile.write(f'error: {type(e).__name__}: {e.word}\n')
            continue
        values = interp.output[before:]
        outfile.write((' '.join(map(str, values)) + ' ok' if values else 'ok') + '\n')
    return 0


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        return repl(sys.stdin, sys.stdout)
    try:
        with open(args[0], encoding='utf-8') as f:
            source = f.read()
    except OSError as e:
        print(f'error: cannot read {args[0]}: {e}', file=sys.stderr)
        return 2
    interp = Interpreter()
    try:
        interp.run(source)
    except StackError as e:
        if interp.output:
            print(' '.join(map(str, interp.output)))
        print(f'error: {type(e).__name__}: {e.word} at line {e.line}, column {e.col}',
              file=sys.stderr)
        return 1
    if interp.output:
        print(' '.join(map(str, interp.output)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
