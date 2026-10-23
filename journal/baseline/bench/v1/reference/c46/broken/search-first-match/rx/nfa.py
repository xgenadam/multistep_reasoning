"""Thompson construction and set-of-states simulation."""

from __future__ import annotations

from .parse import (AnyChar, Alt, CharClass, Concat, Empty, Group, Literal, Optional, Plus,
                    Star, parse)


class NFA:
    """States are integers. A state either consumes one character (pred, next)
    or has only epsilon edges. One accepting state."""

    def __init__(self, node):
        self.pred: list = []      # None for epsilon states
        self.next: list = []      # target after consuming a character
        self.eps: list = []       # epsilon targets
        self.start, self.accept = self._build(node)

    # ------------------------------------------------------------ construction

    def _new(self, pred=None) -> int:
        self.pred.append(pred)
        self.next.append(None)
        self.eps.append([])
        return len(self.pred) - 1

    def _build(self, node) -> tuple[int, int]:
        if isinstance(node, Empty):
            s = self._new()
            return s, s
        if isinstance(node, (Literal, AnyChar, CharClass)):
            if isinstance(node, Literal):
                ch = node.char
                pred = lambda c, ch=ch: c == ch
            elif isinstance(node, AnyChar):
                pred = lambda c: c != '\n'
            else:
                pred = node.matches
            s, e = self._new(pred), self._new()
            self.next[s] = e
            return s, e
        if isinstance(node, Group):
            return self._build(node.node)
        if isinstance(node, Concat):
            first, last = self._build(node.items[0])
            for item in node.items[1:]:
                s, e = self._build(item)
                self.eps[last].append(s)
                last = e
            return first, last
        if isinstance(node, Alt):
            s, e = self._new(), self._new()
            for option in node.options:
                os_, oe = self._build(option)
                self.eps[s].append(os_)
                self.eps[oe].append(e)
            return s, e
        if isinstance(node, (Star, Plus, Optional)):
            ns, ne = self._build(node.node)
            s, e = self._new(), self._new()
            self.eps[s].append(ns)
            self.eps[ne].append(e)
            if not isinstance(node, Plus):
                self.eps[s].append(e)
            if not isinstance(node, Optional):
                self.eps[ne].append(ns)
            return s, e
        raise TypeError(f'not an AST node: {node!r}')

    # ------------------------------------------------------------ simulation

    def _add(self, states: dict, state: int, origin: int) -> None:
        """Add state and its epsilon closure, keeping the earliest origin per state."""
        stack = [state]
        while stack:
            st = stack.pop()
            if st in states and states[st] <= origin:
                continue
            states[st] = origin
            stack.extend(self.eps[st])

    def _step(self, states: dict, c: str) -> dict:
        out: dict = {}
        for st, origin in states.items():
            pred = self.pred[st]
            if pred is not None and pred(c):
                self._add(out, self.next[st], origin)
        return out

    def match(self, text: str) -> bool:
        states: dict = {}
        self._add(states, self.start, 0)
        for c in text:
            states = self._step(states, c)
            if not states:
                return False
        return self.accept in states

    def search(self, text: str, start: int = 0):
        best = None
        states: dict = {}
        pos = start
        while pos <= len(text):
            if best is None:
                self._add(states, self.start, pos)
            if self.accept in states:
                cand = (states[self.accept], pos)
                if best is None or cand[0] < best[0]:
                    best = cand
                    break
            if best is not None:
                states = {s: o for s, o in states.items() if o <= best[0]}
                if not states:
                    break
            if pos == len(text):
                break
            states = self._step(states, text[pos])
            pos += 1
        return best

    def findall(self, text: str) -> list[str]:
        found, pos = [], 0
        while pos <= len(text):
            m = self.search(text, pos)
            if m is None:
                break
            i, j = m
            found.append(text[i:j])
            pos = j + 1 if i == j else j
        return found


def compile(pattern) -> NFA:
    node = parse(pattern) if isinstance(pattern, str) else pattern
    return NFA(node)


def match(pattern, text: str) -> bool:
    return compile(pattern).match(text)


def search(pattern, text: str, start: int = 0):
    return compile(pattern).search(text, start)


def findall(pattern, text: str) -> list[str]:
    return compile(pattern).findall(text)
