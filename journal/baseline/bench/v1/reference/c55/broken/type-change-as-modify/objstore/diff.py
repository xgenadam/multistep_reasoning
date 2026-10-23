"""Recursive tree diff."""

from __future__ import annotations

from typing import NamedTuple

from .objects import Commit, Tree


class Change(NamedTuple):
    status: str
    path: str
    old: str | None
    new: str | None


def _entries(store, oid) -> dict:
    if oid is None:
        return {}
    tree = store.get(oid)
    if not isinstance(tree, Tree):
        raise ValueError(f'{oid} is not a tree')
    return {e.name: e for e in tree.entries}


def _files(store, oid, prefix: str):
    """(path, blob oid) for every file under a tree."""
    for e in _entries(store, oid).values():
        if e.kind == 'tree':
            yield from _files(store, e.oid, prefix + e.name + '/')
        else:
            yield prefix + e.name, e.oid


def _diff(store, old, new, prefix: str, out: list) -> None:
    if old == new:
        return
    a, b = _entries(store, old), _entries(store, new)
    for name in sorted(set(a) | set(b)):
        ea, eb = a.get(name), b.get(name)
        path = prefix + name
        if ea and eb and ea.oid == eb.oid and ea.kind == eb.kind:
            continue
        if ea and eb and ea.kind == eb.kind == 'tree':
            _diff(store, ea.oid, eb.oid, path + '/', out)
        elif ea and eb:
            out.append(Change('M', path, ea.oid, eb.oid))
        else:
            if ea:
                if ea.kind == 'blob':
                    out.append(Change('D', path, ea.oid, None))
                else:
                    out.extend(Change('D', p, o, None) for p, o in _files(store, ea.oid, path + '/'))
            if eb:
                if eb.kind == 'blob':
                    out.append(Change('A', path, None, eb.oid))
                else:
                    out.extend(Change('A', p, None, o) for p, o in _files(store, eb.oid, path + '/'))


def diff_trees(store, old, new) -> list[Change]:
    out: list[Change] = []
    _diff(store, old, new, '', out)
    return sorted(out, key=lambda c: c.path)


def _tree_of(store, oid):
    if oid is None:
        return None
    commit = store.get(oid)
    if not isinstance(commit, Commit):
        raise ValueError(f'{oid} is not a commit')
    return commit.tree


def diff_commits(store, old, new) -> list[Change]:
    return diff_trees(store, _tree_of(store, old), _tree_of(store, new))


def format_changes(changes) -> str:
    return ''.join(f'{c.status}\t{c.path}\n' for c in changes)
