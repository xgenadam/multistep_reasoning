"""The filesystem tree and its operations."""

from __future__ import annotations

from fnmatch import fnmatchcase

from .paths import is_within, normalize, split


class FSError(Exception):
    pass


class NotFound(FSError):
    pass


class AlreadyExists(FSError):
    pass


class NotADirectory(FSError):
    pass


class IsADirectory(FSError):
    pass


class InvalidOperation(FSError):
    pass


class _Dir:
    def __init__(self):
        self.children: dict[str, object] = {}


class _File:
    def __init__(self, text: str = ''):
        self.text = text


class FileSystem:
    def __init__(self):
        self._root = _Dir()
        self._cwd = '/'

    # ------------------------------------------------------------ lookup

    def _abs(self, path: str) -> str:
        return normalize(path, self._cwd)

    def _lookup(self, path: str):
        """The node at an absolute path, or None; NotADirectory through a file."""
        node = self._root
        for part in [p for p in path.split('/') if p]:
            if isinstance(node, _File):
                raise NotADirectory(path)
            node = node.children.get(part)
            if node is None:
                return None
        return node

    def _parent_dir(self, path: str) -> _Dir | None:
        parent = self._lookup(split(path)[0])
        if isinstance(parent, _File):
            raise NotADirectory(path)
        return parent

    def _check_through(self, path: str) -> None:
        """Raise NotADirectory if any proper ancestor of path is a file."""
        node = self._root
        for part in [p for p in path.split('/') if p][:-1]:
            node = node.children.get(part)
            if node is None:
                return
            if isinstance(node, _File):
                raise NotADirectory(path)

    def _get(self, path: str):
        self._check_through(path)
        return self._lookup(path)

    # ------------------------------------------------------------ queries

    def pwd(self) -> str:
        return self._cwd

    def exists(self, path: str) -> bool:
        try:
            return self._get(self._abs(path)) is not None
        except FSError:
            return False

    def is_dir(self, path: str) -> bool:
        try:
            return isinstance(self._get(self._abs(path)), _Dir)
        except FSError:
            return False

    def ls(self, path: str = '.') -> list[str]:
        p = self._abs(path)
        node = self._get(p)
        if node is None:
            raise NotFound(p)
        if isinstance(node, _File):
            return [split(p)[1]]
        return sorted(name + ('/' if isinstance(child, _Dir) else '')
                      for name, child in node.children.items())

    def read(self, path: str) -> str:
        p = self._abs(path)
        node = self._get(p)
        if node is None:
            raise NotFound(p)
        if isinstance(node, _Dir):
            raise IsADirectory(p)
        return node.text

    def find(self, path: str = '.', pattern: str = '*') -> list[str]:
        p = self._abs(path)
        node = self._get(p)
        if node is None:
            raise NotFound(p)
        if isinstance(node, _File):
            return [p] if fnmatchcase(split(p)[1], pattern) else []
        found = []

        def walk(prefix: str, d: _Dir):
            for name, child in d.children.items():
                full = prefix.rstrip('/') + '/' + name
                if fnmatchcase(name, pattern):
                    found.append(full)
                if isinstance(child, _Dir):
                    walk(full, child)

        walk(p, node)
        return sorted(found)

    # ------------------------------------------------------------ changes

    def cd(self, path: str) -> None:
        p = self._abs(path)
        node = self._get(p)
        if node is None:
            raise NotFound(p)
        if isinstance(node, _File):
            raise NotADirectory(p)
        self._cwd = p

    def mkdir(self, path: str, parents: bool = False) -> None:
        p = self._abs(path)
        self._check_through(p)
        node = self._lookup(p)
        if node is not None:
            if parents and isinstance(node, _Dir):
                return
            raise AlreadyExists(p)
        if not parents:
            parent = self._parent_dir(p)
            if parent is None:
                raise NotFound(p)
            parent.children[split(p)[1]] = _Dir()
            return
        current = self._root
        for part in [x for x in p.split('/') if x]:
            child = current.children.get(part)
            if child is None:
                child = current.children[part] = _Dir()
            current = child

    def write(self, path: str, text: str, append: bool = False) -> None:
        p = self._abs(path)
        node = self._get(p)
        if isinstance(node, _Dir):
            raise IsADirectory(p)
        if node is None:
            parent = self._parent_dir(p)
            if parent is None:
                raise NotFound(p)
            parent.children[split(p)[1]] = _File(text)
        elif append:
            node.text += text
        else:
            node.text = text

    def _protected(self, p: str) -> bool:
        return p == '/' or is_within(self._cwd, p)

    def rm(self, path: str, recursive: bool = False) -> None:
        p = self._abs(path)
        node = self._get(p)
        if node is None:
            raise NotFound(p)
        if self._protected(p):
            raise InvalidOperation(p)
        if isinstance(node, _Dir) and not recursive:
            raise IsADirectory(p)
        del self._parent_dir(p).children[split(p)[1]]

    def mv(self, src: str, dst: str) -> None:
        s = self._abs(src)
        node = self._get(s)
        if node is None:
            raise NotFound(s)
        if self._protected(s):
            raise InvalidOperation(s)
        d = self._abs(dst)
        dnode = self._get(d)
        target = d.rstrip('/') + '/' + split(s)[1] if isinstance(dnode, _Dir) else d
        target = normalize(target)
        if is_within(target, s):
            raise InvalidOperation(s)
        if self._get(target) is not None:
            raise AlreadyExists(target)
        parent = self._parent_dir(target)
        if parent is None:
            raise NotFound(d)
        del self._parent_dir(s).children[split(s)[1]]
        parent.children[split(target)[1]] = node
