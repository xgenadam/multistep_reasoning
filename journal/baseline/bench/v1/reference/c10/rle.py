"""Run-length encoding with backslash escapes for digits and backslashes."""
from itertools import groupby

_DIGITS = '0123456789'
_SPECIAL = set(_DIGITS + '\\')


def _written(ch: str) -> str:
    return '\\' + ch if ch in _SPECIAL else ch


def encode(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f'expected str, got {type(text).__name__}')
    out = []
    for ch, group in groupby(text):
        n = sum(1 for _ in group)
        out.append((str(n) if n > 1 else '') + _written(ch))
    return ''.join(out)


def decode(data: str) -> str:
    if not isinstance(data, str):
        raise TypeError(f'expected str, got {type(data).__name__}')
    out = []
    i, n = 0, len(data)
    while i < n:
        start = i
        while i < n and data[i] in _DIGITS:
            i += 1
        digits = data[start:i]
        if digits:
            if digits[0] == '0' or int(digits) < 2:
                raise ValueError(f'invalid count {digits!r} at index {start}')
            count = int(digits)
        else:
            count = 1
        if i >= n:
            raise ValueError(f'count without a character at index {start}')
        ch = data[i]
        if ch == '\\':
            if i + 1 >= n or data[i + 1] not in _SPECIAL:
                raise ValueError(f'invalid escape at index {i}')
            ch = data[i + 1]
            i += 2
        else:
            i += 1
        out.append(ch * count)
    return ''.join(out)
