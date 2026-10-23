"""Semantic Versioning 2.0.0: parsing, precedence, bumping and simple ranges."""
import functools
import re

_NUM = r'(?:0|[1-9][0-9]*)'
_PRE_ID = r'(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
_BUILD_ID = r'[0-9A-Za-z-]+'
_VERSION = re.compile(
    rf'({_NUM})\.({_NUM})\.({_NUM})'
    rf'(?:-({_PRE_ID}(?:\.{_PRE_ID})*))?'
    rf'(?:\+({_BUILD_ID}(?:\.{_BUILD_ID})*))?')
_PARTIAL = re.compile(rf'({_NUM})(?:\.({_NUM}))?(?:\.({_NUM}))?')
_COMPARATOR = re.compile(r'(\^|~|>=|<=|>|<|=)?(.+)')


@functools.total_ordering
class Version:
    def __init__(self, major: int, minor: int, patch: int,
                 prerelease: tuple = (), build: tuple = ()):
        self.major, self.minor, self.patch = major, minor, patch
        self.prerelease = tuple(prerelease)
        self.build = tuple(build)

    @classmethod
    def parse(cls, text: str) -> 'Version':
        m = _VERSION.fullmatch(text) if isinstance(text, str) else None
        if not m:
            raise ValueError(f'invalid version: {text!r}')
        major, minor, patch, pre, build = m.groups()
        return cls(int(major), int(minor), int(patch),
                   tuple(pre.split('.')) if pre else (),
                   tuple(build.split('.')) if build else ())

    def __str__(self) -> str:
        text = f'{self.major}.{self.minor}.{self.patch}'
        if self.prerelease:
            text += '-' + '.'.join(self.prerelease)
        if self.build:
            text += '+' + '.'.join(self.build)
        return text

    def __repr__(self) -> str:
        return f'Version({str(self)!r})'

    def _key(self):
        pre = tuple((0, int(i), '') if i.isdigit() else (1, 0, i) for i in self.prerelease)
        # A release (no pre-release) sorts after every pre-release of the same version.
        return (self.major, self.minor, self.patch, 0 if self.prerelease else 1, pre)

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __hash__(self):
        return hash(self._key())

    def bump(self, kind: str) -> 'Version':
        if kind == 'major':
            return Version(self.major + 1, 0, 0)
        if kind == 'minor':
            return Version(self.major, self.minor + 1, 0)
        if kind == 'patch':
            return Version(self.major, self.minor, self.patch + 1)
        raise ValueError(f'unknown bump kind: {kind!r}')


def _partial(text: str) -> tuple[Version, int]:
    """A full or partial version for a comparator, and how many parts were given."""
    m = _PARTIAL.fullmatch(text)
    if m:
        parts = [int(p) for p in m.groups() if p is not None]
        return Version(*(parts + [0] * (3 - len(parts)))), len(parts)
    return Version.parse(text), 3


def _bounds(op: str, text: str) -> list[tuple[str, Version]]:
    v, given = _partial(text)
    if op == '^':
        upper = Version(v.major + 1, 0, 0)
        return [('>=', v), ('<', upper)]
    if op == '~':
        upper = Version(v.major + 1, 0, 0) if given == 1 else Version(v.major, v.minor + 1, 0)
        return [('>=', v), ('<', upper)]
    return [(op or '=', v)]


_TESTS = {
    '>=': lambda a, b: a >= b, '>': lambda a, b: a > b,
    '<=': lambda a, b: a <= b, '<': lambda a, b: a < b, '=': lambda a, b: a == b,
}


def satisfies(version, spec: str) -> bool:
    if not isinstance(version, Version):
        version = Version.parse(version)
    tokens = spec.split() if isinstance(spec, str) else []
    if not tokens:
        raise ValueError(f'empty range: {spec!r}')
    checks = []
    for token in tokens:
        m = _COMPARATOR.fullmatch(token)
        if not m:
            raise ValueError(f'invalid comparator: {token!r}')
        checks.extend(_bounds(m.group(1) or '', m.group(2)))
    return all(_TESTS[op](version, bound) for op, bound in checks)
