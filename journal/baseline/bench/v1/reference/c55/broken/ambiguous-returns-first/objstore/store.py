"""In-memory store, tree helpers and history walking."""

from __future__ import annotations

import hashlib
import re

from .objects import (Blob, Commit, Tree, TreeEntry, check_name, check_oid, object_id,
                      parse_object, serialize)


class ObjectNotFound(KeyError):
    pass


class AmbiguousPrefix(ValueError):
    pass


class ObjectStore:
    def __init__(self):
        self._objects: dict[str, bytes] = {}

    def put(self, obj) -> str:
        raw = serialize(obj)
        oid = hashlib.sha1(raw).hexdigest()
        self._objects[oid] = raw
        return oid

    def put_raw(self, raw: bytes) -> str:
        parse_object(raw)
        oid = hashlib.sha1(raw).hexdigest()
        self._objects[oid] = bytes(raw)
        return oid

    def get_raw(self, oid: str) -> bytes:
        try:
            return self._objects[oid]
        except KeyError:
            raise ObjectNotFound(oid) from None

    def get(self, oid: str):
        return parse_object(self.get_raw(oid))

    def __contains__(self, oid) -> bool:
        return oid in self._objects

    def resolve(self, prefix: str) -> str:
        if not isinstance(prefix, str) or not re.fullmatch(r'[0-9a-f]{4,40}', prefix):
            raise ValueError(f'bad prefix: {prefix!r}')
        matches = [oid for oid in self._objects if oid.startswith(prefix)]
        if not matches:
            raise ObjectNotFound(prefix)
        return matches[0]

    # ------------------------------------------------------------ trees

    def write_tree(self, files: dict) -> str:
        root: dict = {}
        for path, data in files.items():
            if not isinstance(path, str) or path.startswith('/') or path.endswith('/'):
                raise ValueError(f'bad path: {path!r}')
            parts = path.split('/')
            for part in parts:
                check_name(part)
            node = root
            for part in parts[:-1]:
                child = node.setdefault(part, {})
                if not isinstance(child, dict):
                    raise ValueError(f'{path!r}: {part!r} is a file')
                node = child
            if parts[-1] in node:
                raise ValueError(f'{path!r} is both a file and a directory')
            node[parts[-1]] = bytes(data)
        return self._write_dir(root)

    def _write_dir(self, node: dict) -> str:
        entries = []
        for name, child in node.items():
            if isinstance(child, dict):
                entries.append(TreeEntry(name, 'tree', self._write_dir(child)))
            else:
                entries.append(TreeEntry(name, 'blob', self.put(Blob(child))))
        return self.put(Tree(entries))

    def read_tree(self, oid: str) -> dict[str, bytes]:
        out: dict[str, bytes] = {}

        def walk(prefix: str, tree_oid: str):
            tree = self.get(tree_oid)
            if not isinstance(tree, Tree):
                raise ValueError(f'{tree_oid} is not a tree')
            for e in tree.entries:
                path = prefix + e.name
                if e.kind == 'tree':
                    walk(path + '/', e.oid)
                else:
                    out[path] = self.get(e.oid).data

        walk('', oid)
        return dict(sorted(out.items()))

    # ------------------------------------------------------------ commits

    def commit(self, tree: str, parents=(), *, author: str, timestamp: int,
               message: str) -> str:
        if not isinstance(self.get(tree), Tree):
            raise ValueError(f'{tree} is not a tree')
        for p in parents:
            if not isinstance(self.get(p), Commit):
                raise ValueError(f'{p} is not a commit')
        return self.put(Commit(tree, tuple(parents), author, timestamp, message))

    def _commit(self, oid: str) -> Commit:
        obj = self.get(oid)
        if not isinstance(obj, Commit):
            raise ValueError(f'{oid} is not a commit')
        return obj

    def log(self, oid: str, first_parent: bool = False) -> list[str]:
        if first_parent:
            out = []
            while True:
                out.append(oid)
                c = self._commit(oid)
                if not c.parents:
                    return out
                oid = c.parents[0]
        seen: dict[str, int] = {}
        todo = [oid]
        while todo:
            cur = todo.pop()
            if cur in seen:
                continue
            c = self._commit(cur)
            seen[cur] = c.timestamp
            todo.extend(c.parents)
        return sorted(seen, key=lambda o: (-seen[o], o))
