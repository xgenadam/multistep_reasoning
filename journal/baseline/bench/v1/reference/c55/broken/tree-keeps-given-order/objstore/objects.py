"""Blobs, trees and commits, and their byte serialisation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import NamedTuple

OID = re.compile(r'[0-9a-f]{40}')
KINDS = ('blob', 'tree')


class CorruptObject(ValueError):
    pass


def check_oid(oid) -> str:
    if not isinstance(oid, str) or not OID.fullmatch(oid):
        raise ValueError(f'bad oid: {oid!r}')
    return oid


def check_name(name) -> str:
    if (not isinstance(name, str) or name in ('', '.', '..')
            or any(c in name for c in '/\0\t\n')):
        raise ValueError(f'bad name: {name!r}')
    return name


@dataclass(frozen=True)
class Blob:
    data: bytes


class TreeEntry(NamedTuple):
    name: str
    kind: str
    oid: str


@dataclass(frozen=True)
class Tree:
    entries: tuple

    def __init__(self, entries=()):
        items = [TreeEntry(*e) for e in entries]
        seen = set()
        for e in items:
            check_name(e.name)
            if e.kind not in KINDS:
                raise ValueError(f'bad kind: {e.kind!r}')
            check_oid(e.oid)
            if e.name in seen:
                raise ValueError(f'repeated name: {e.name!r}')
            seen.add(e.name)
        object.__setattr__(self, 'entries', tuple(items))

    def get(self, name: str) -> TreeEntry | None:
        return next((e for e in self.entries if e.name == name), None)


@dataclass(frozen=True)
class Commit:
    tree: str
    parents: tuple
    author: str
    timestamp: int
    message: str

    def __post_init__(self):
        object.__setattr__(self, 'parents', tuple(self.parents))
        check_oid(self.tree)
        for p in self.parents:
            check_oid(p)
        if not isinstance(self.author, str) or '\n' in self.author:
            raise ValueError('bad author')
        if not isinstance(self.timestamp, int) or isinstance(self.timestamp, bool) \
                or self.timestamp < 0:
            raise ValueError('bad timestamp')
        if not isinstance(self.message, str):
            raise ValueError('bad message')


def _body(obj) -> tuple[str, bytes]:
    if isinstance(obj, Blob):
        return 'blob', bytes(obj.data)
    if isinstance(obj, Tree):
        return 'tree', ''.join(f'{e.kind} {e.oid}\t{e.name}\n' for e in obj.entries).encode()
    if isinstance(obj, Commit):
        text = f'tree {obj.tree}\n' + ''.join(f'parent {p}\n' for p in obj.parents)
        text += f'author {obj.author}\ntime {obj.timestamp}\n\n{obj.message}'
        return 'commit', text.encode('utf-8')
    raise TypeError(f'not an object: {obj!r}')


def serialize(obj) -> bytes:
    kind, body = _body(obj)
    return f'{kind} {len(body)}'.encode('ascii') + b'\0' + body


def object_id(obj) -> str:
    return hashlib.sha1(serialize(obj)).hexdigest()


def _parse_tree(text: str) -> Tree:
    entries = []
    if text and not text.endswith('\n'):
        raise CorruptObject('tree body must end with a newline')
    for line in text.split('\n')[:-1] if text else []:
        m = re.fullmatch(r'(blob|tree) ([0-9a-f]{40})\t(.+)', line)
        if not m:
            raise CorruptObject(f'bad tree line: {line!r}')
        entries.append(TreeEntry(m.group(3), m.group(1), m.group(2)))
    tree = Tree(entries)
    if [e.name for e in tree.entries] != [e.name for e in entries]:
        raise CorruptObject('tree entries are not sorted')
    return tree


def _parse_commit(text: str) -> Commit:
    head, sep, message = text.partition('\n\n')
    if not sep:
        raise CorruptObject('commit has no message separator')
    lines = head.split('\n')
    if len(lines) < 3 or not lines[0].startswith('tree '):
        raise CorruptObject('bad commit header')
    tree = lines[0][5:]
    parents = []
    i = 1
    while i < len(lines) and lines[i].startswith('parent '):
        parents.append(lines[i][7:])
        i += 1
    if len(lines) - i != 2 or not lines[i].startswith('author ') \
            or not re.fullmatch(r'time (0|[1-9][0-9]*)', lines[i + 1]):
        raise CorruptObject('bad commit header')
    return Commit(tree, tuple(parents), lines[i][7:], int(lines[i + 1][5:]), message)


def parse_object(raw: bytes):
    header, sep, body = bytes(raw).partition(b'\0')
    m = re.fullmatch(rb'(blob|tree|commit) (0|[1-9][0-9]*)', header)
    if not sep or not m:
        raise CorruptObject('bad header')
    if int(m.group(2)) != len(body):
        raise CorruptObject('length does not match')
    kind = m.group(1).decode()
    if kind == 'blob':
        return Blob(body)
    try:
        text = body.decode('utf-8')
        return _parse_tree(text) if kind == 'tree' else _parse_commit(text)
    except CorruptObject:
        raise
    except ValueError as e:      # bad UTF-8, bad names, bad oids
        raise CorruptObject(str(e)) from e
