"""Serializer: compact or indented, optional key sorting and ASCII escaping."""

from __future__ import annotations

import math

_SHORT = {'"': '\\"', '\\': '\\\\', '\b': '\\b', '\f': '\\f', '\n': '\\n', '\r': '\\r',
          '\t': '\\t'}


def _quote(s: str, ensure_ascii: bool) -> str:
    out = ['"']
    for c in s:
        if c in _SHORT:
            out.append(_SHORT[c])
        elif c < ' ':
            out.append(f'\\u{ord(c):04x}')
        elif ensure_ascii and ord(c) > 0x7F:
            code = ord(c)
            out.append(f'\\u{code:04x}')
        else:
            out.append(c)
    out.append('"')
    return ''.join(out)


def dumps(obj, *, indent=None, sort_keys=False, ensure_ascii=False) -> str:
    if indent is not None and indent < 0:
        raise ValueError('indent must be >= 0')
    active: set[int] = set()
    parts: list[str] = []

    def write(value, level: int) -> None:
        if value is None:
            parts.append('null')
        elif value is True:
            parts.append('true')
        elif value is False:
            parts.append('false')
        elif isinstance(value, int):
            parts.append(str(int(value)))
        elif isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                raise ValueError(f'{value!r} is not allowed in JSON')
            parts.append(repr(value))
        elif isinstance(value, str):
            parts.append(_quote(value, ensure_ascii))
        elif isinstance(value, (list, tuple, dict)):
            if id(value) in active:
                raise ValueError('circular reference')
            active.add(id(value))
            if isinstance(value, dict):
                for k in value:
                    if not isinstance(k, str):
                        raise TypeError(f'object keys must be str, not {type(k).__name__}')
                keys = sorted(value) if sort_keys else list(value)
                members = [(k, value[k]) for k in keys]
                container(members, level, '{', '}', is_object=True)
            else:
                container(list(value), level, '[', ']', is_object=False)
            active.discard(id(value))
        else:
            raise TypeError(f'{type(value).__name__} is not JSON serializable')

    def container(items, level, open_, close, is_object):
        if not items:
            parts.append(open_ + close)
            return
        parts.append(open_)
        inner = None if indent is None else '\n' + ' ' * (indent * (level + 1))
        for i, item in enumerate(items):
            if i:
                parts.append(',')
            if inner is not None:
                parts.append(inner)
            if is_object:
                key, val = item
                parts.append(_quote(key, ensure_ascii))
                parts.append(':' if indent is None else ': ')
                write(val, level + 1)
            else:
                write(item, level + 1)
        if indent is not None:
            parts.append('\n' + ' ' * (indent * level))
        parts.append(close)

    write(obj, 0)
    return ''.join(parts)
