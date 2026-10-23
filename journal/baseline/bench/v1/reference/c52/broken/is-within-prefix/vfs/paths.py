"""Pure path helpers: normalisation, joining, splitting."""

from __future__ import annotations


def normalize(path: str, cwd: str = '/') -> str:
    if not path:
        raise ValueError('empty path')
    parts = [] if path.startswith('/') else [p for p in cwd.split('/') if p]
    for part in path.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return '/' + '/'.join(parts)


def join(base: str, *parts: str) -> str:
    path = base
    for part in parts:
        if part.startswith('/'):
            path = part
        elif part:
            path = path.rstrip('/') + '/' + part if path else part
    return normalize(path)


def split(path: str) -> tuple[str, str]:
    if path == '/':
        return '/', ''
    parent, _, name = path.rpartition('/')
    return parent or '/', name


def is_within(path: str, ancestor: str) -> bool:
    path, ancestor = normalize(path), normalize(ancestor)
    return path.startswith(ancestor)
