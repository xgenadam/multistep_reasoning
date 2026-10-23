"""Convert between integers (1..3999) and canonical Roman numerals."""
import re

_VALUES = [
    (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
    (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
    (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'),
]

_CANONICAL = re.compile(
    r'M{0,3}(CM|CD|D?C{0,4})(XC|XL|L?X{0,4})(IX|IV|V?I{0,4})')
_DIGIT = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}


def to_roman(n: int) -> str:
    """The canonical numeral for 1 <= n <= 3999."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f'expected an int, got {type(n).__name__}')
    if not 1 <= n <= 3999:
        raise ValueError(f'out of range 1..3999: {n}')
    parts = []
    for value, symbol in _VALUES:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return ''.join(parts)


def from_roman(s: str) -> int:
    """The value of a canonical numeral; anything else raises ValueError."""
    if not isinstance(s, str):
        raise TypeError(f'expected a str, got {type(s).__name__}')
    if not s or not _CANONICAL.fullmatch(s):
        raise ValueError(f'not a canonical Roman numeral: {s!r}')
    total = 0
    for i, ch in enumerate(s):
        value = _DIGIT[ch]
        if i + 1 < len(s) and _DIGIT[s[i + 1]] > value:
            total -= value
        else:
            total += value
    return total
