import re

_UNITS = {
    # name: (scale, (length, mass, time))
    'mm': (0.001, (1, 0, 0)), 'cm': (0.01, (1, 0, 0)), 'm': (1.0, (1, 0, 0)),
    'km': (1000.0, (1, 0, 0)), 'in': (0.0254, (1, 0, 0)), 'ft': (0.3048, (1, 0, 0)),
    'yd': (0.9144, (1, 0, 0)), 'mi': (1609.344, (1, 0, 0)),
    'mg': (0.000001, (0, 1, 0)), 'g': (0.001, (0, 1, 0)), 'kg': (1.0, (0, 1, 0)),
    't': (1000.0, (0, 1, 0)), 'oz': (0.028349523125, (0, 1, 0)),
    'lb': (0.45359237, (0, 1, 0)),
    'ms': (0.001, (0, 0, 1)), 's': (1.0, (0, 0, 1)), 'min': (60.0, (0, 0, 1)),
    'h': (3600.0, (0, 0, 1)), 'day': (86400.0, (0, 0, 1)),
}

_FACTOR = re.compile(r'([A-Za-z]+)(?:\^([1-9][0-9]*))?')


class UnitError(ValueError):
    pass


class DimensionError(ValueError):
    pass


def _reduce(expr):
    if not isinstance(expr, str) or not expr:
        raise UnitError(f'bad unit expression {expr!r}')
    tokens = re.split(r'([*/])', expr)
    scale, dims = 1.0, [0, 0, 0]
    op = '*'
    for i, tok in enumerate(tokens):
        if i % 2:
            op = tok
            continue
        m = _FACTOR.fullmatch(tok)
        if not m:
            raise UnitError(f'bad factor {tok!r} in {expr!r}')
        name, power = m.group(1), int(m.group(2) or 1)
        if name not in _UNITS:
            raise UnitError(f'unknown unit {name!r}')
        s, d = _UNITS[name]
        sign = 1 if op == '*' else -1
        scale *= s ** (sign * power)
        for k in range(3):
            dims[k] += sign * d[k]
    return scale, tuple(dims)


def convert(value, from_unit, to_unit):
    s1, d1 = _reduce(from_unit)
    s2, d2 = _reduce(to_unit)
    if d1 != d2:
        raise DimensionError(f'cannot convert {from_unit!r} to {to_unit!r}')
    return float(value * s1 / s2)
