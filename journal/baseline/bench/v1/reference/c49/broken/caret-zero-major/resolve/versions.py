"""MAJOR.MINOR.PATCH versions and comma-separated ranges."""

from __future__ import annotations

import re
from functools import total_ordering

_PART = re.compile(r'0|[1-9][0-9]*')
_OPS = ('==', '!=', '>=', '<=', '>', '<', '^', '~')


@total_ordering
class Version:
    __slots__ = ('major', 'minor', 'patch')

    def __init__(self, text: str):
        parts = text.split('.') if isinstance(text, str) else []
        if len(parts) != 3 or not all(_PART.fullmatch(p) for p in parts):
            raise ValueError(f'bad version: {text!r}')
        self.major, self.minor, self.patch = (int(p) for p in parts)

    @property
    def key(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __eq__(self, other):
        return isinstance(other, Version) and self.key == other.key

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self.key < other.key

    def __hash__(self):
        return hash(self.key)

    def __str__(self):
        return f'{self.major}.{self.minor}.{self.patch}'

    def __repr__(self):
        return f'Version({str(self)!r})'


def _caret_upper(v: Version) -> Version:
    return Version(f'{v.major + 1}.0.0')


class Range:
    def __init__(self, spec: str):
        if not isinstance(spec, str) or not spec.strip():
            raise ValueError('empty range')
        self.spec = re.sub(r'\s+', '', spec)
        self._checks: list[tuple[str, Version | None]] = []
        for raw in self.spec.split(','):
            if not raw:
                raise ValueError(f'empty constraint in {spec!r}')
            if raw == '*':
                continue
            op = next((o for o in _OPS if raw.startswith(o)), '==')
            text = raw[len(op):] if raw.startswith(op) else raw
            v = Version(text)
            if op == '^':
                self._checks += [('>=', v), ('<', _caret_upper(v))]
            elif op == '~':
                self._checks += [('>=', v), ('<', Version(f'{v.major}.{v.minor + 1}.0'))]
            else:
                self._checks.append((op, v))

    def contains(self, v: Version) -> bool:
        for op, bound in self._checks:
            ok = {'==': v == bound, '!=': v != bound, '>=': v >= bound, '<=': v <= bound,
                  '>': v > bound, '<': v < bound}[op]
            if not ok:
                return False
        return True

    def __contains__(self, v: Version) -> bool:
        return self.contains(v)

    def __str__(self):
        return self.spec

    def __repr__(self):
        return f'Range({self.spec!r})'
