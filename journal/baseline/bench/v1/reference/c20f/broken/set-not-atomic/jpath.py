from collections.abc import Mapping

_MISSING = object()
_SPECIAL = '.[]"'


class _Wildcard:
    def __repr__(self):
        return 'WILDCARD'


WILDCARD = _Wildcard()


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
    if body == '*':
        return WILDCARD, end + 1
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
    if isinstance(cur, (list, tuple)) and -len(cur) <= seg < len(cur):
        return cur[seg]
    return _MISSING


def _expand(cur, segments):
    if not segments:
        yield cur
        return
    seg, rest = segments[0], segments[1:]
    if seg is WILDCARD:
        if isinstance(cur, Mapping):
            children = list(cur.values())
        elif isinstance(cur, (list, tuple)):
            children = list(cur)
        else:
            children = []
        for child in children:
            yield from _expand(child, rest)
        return
    nxt = _step(cur, seg)
    if nxt is not _MISSING:
        yield from _expand(nxt, rest)


def get(obj, path, default=_MISSING):
    segments = parse(path)
    if any(seg is WILDCARD for seg in segments):
        return list(_expand(obj, segments))
    cur = obj
    for seg in segments:
        cur = _step(cur, seg)
        if cur is _MISSING:
            if default is _MISSING:
                raise PathError('no value at path', path)
            return default
    return cur


def _plain_segments(path):
    segments = parse(path)
    if not segments:
        raise PathError('empty path', path)
    if any(seg is WILDCARD for seg in segments):
        raise PathError('wildcards are not allowed here', path)
    return segments


def _build(segments, value, path):
    """A new container chain for `segments` ending in `value` (index segments must be 0)."""
    if not segments:
        return value
    seg, rest = segments[0], segments[1:]
    child = _build(rest, value, path)
    if isinstance(seg, str):
        return {seg: child}
    if seg != 0:
        raise PathError('index out of range for a new list', path)
    return [child]


def _store(container, seg, child, path):
    """Store child at seg in container; raise before changing anything if impossible."""
    if isinstance(seg, str) and isinstance(container, dict):
        container[seg] = child
    elif isinstance(seg, int) and isinstance(container, list):
        if -len(container) <= seg < len(container):
            container[seg] = child
        elif seg == len(container):
            container.append(child)
        else:
            raise PathError('index out of range', path)
    else:
        raise PathError('cannot store here', path)


def _can_store(container, seg):
    if isinstance(seg, str):
        return isinstance(container, dict)
    return isinstance(container, list) and -len(container) <= seg <= len(container)


def set(obj, path, value):
    segments = _plain_segments(path)
    cur = obj
    for k, seg in enumerate(segments[:-1]):
        nxt = _step(cur, seg)
        if nxt is _MISSING:
            if not _can_store(cur, seg):
                raise PathError('cannot create a container here', path)
            rest = segments[k + 1:]
            new = [] if isinstance(rest[0], int) else {}
            _store(cur, seg, new, path)
            for s2, nseg in zip(rest, rest[1:] + [None]):
                if nseg is None:
                    _store(new, s2, value, path)
                else:
                    child = [] if isinstance(nseg, int) else {}
                    _store(new, s2, child, path)
                    new = child
            return None
        cur = nxt
    if not _can_store(cur, segments[-1]):
        raise PathError('cannot store here', path)
    _store(cur, segments[-1], value, path)
    return None


def delete(obj, path):
    segments = _plain_segments(path)
    parent = obj
    for seg in segments[:-1]:
        parent = _step(parent, seg)
        if parent is _MISSING:
            raise PathError('no value at path', path)
    last = segments[-1]
    if isinstance(last, str) and isinstance(parent, dict) and last in parent:
        return parent.pop(last)
    if isinstance(last, int) and isinstance(parent, list) and -len(parent) <= last < len(parent):
        return parent.pop(last)
    raise PathError('no value to delete', path)
