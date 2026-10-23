from collections.abc import Mapping

_MISSING = object()
_SPECIAL = '.[]"'


class PathError(LookupError):
    def __init__(self, message, path):
        super().__init__(f'{message}: {path!r}')
        self.path = path


def _quoted(path, i):
    """Parse a quoted key starting at the opening quote; return (key, index after ']')."""
    out = []
    i += 1
    while i < len(path):
        ch = path[i]
        if ch == '\\':
            if i + 1 < len(path) and path[i + 1] in '"\\':
                out.append(path[i + 1])
                i += 2
                continue
            raise PathError('bad escape', path)
        if ch == '"':
            if path[i + 1:i + 2] != ']':
                raise PathError('expected ] after quoted key', path)
            return ''.join(out), i + 2
        out.append(ch)
        i += 1
    raise PathError('unclosed quote', path)


def _bracket(path, i):
    """Parse a bracket starting at '['; return (segment, index after ']')."""
    if path[i + 1:i + 2] == '"':
        return _quoted(path, i + 1)
    end = path.find(']', i)
    if end < 0:
        raise PathError('unclosed bracket', path)
    body = path[i + 1:end]
    digits = body[1:] if body.startswith('-') else body
    if not digits or not digits.isascii() or not digits.isdigit():
        raise PathError(f'bad index {body!r}', path)
    return int(body), end + 1


def _name(path, i):
    j = i
    while j < len(path) and path[j] not in _SPECIAL:
        j += 1
    if j == i:
        raise PathError('empty name', path)
    return path[i:j], j


def parse(path):
    segments = []
    i = 0
    if path and path[0] != '[':
        name, i = _name(path, 0)
        segments.append(name)
    while i < len(path):
        ch = path[i]
        if ch == '.':
            name, i = _name(path, i + 1)
            segments.append(name)
        elif ch == '[':
            seg, i = _bracket(path, i)
            segments.append(seg)
        else:
            raise PathError(f'unexpected {ch!r}', path)
    return segments


def _step(cur, seg):
    if isinstance(seg, str):
        if isinstance(cur, Mapping) and seg in cur:
            return cur[seg]
        return _MISSING
    if isinstance(cur, (list, tuple, str)) and -len(cur) <= seg < len(cur):
        return cur[seg]
    return _MISSING


def get(obj, path, default=_MISSING):
    segments = parse(path)
    cur = obj
    for seg in segments:
        cur = _step(cur, seg)
        if cur is _MISSING:
            if default is _MISSING:
                raise PathError('no value at path', path)
            return default
    return cur
