import heapq


class _Node:
    __slots__ = ('children', 'entry')

    def __init__(self):
        self.children = {}
        self.entry = None  # (word as added, weight) when a word ends here


class Autocomplete:
    def __init__(self):
        self._root = _Node()
        self._size = 0

    def _find(self, key):
        node = self._root
        for ch in key:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def add(self, word, weight=1):
        if not word:
            raise ValueError('word must not be empty')
        node = self._root
        for ch in word.casefold():
            node = node.children.setdefault(ch, _Node())
        if node.entry is None:
            self._size += 1
        node.entry = (word, weight)

    def complete(self, prefix, k=10):
        if k < 0:
            raise ValueError('k must not be negative')
        if k == 0:
            return []
        start = self._find(prefix.casefold())
        if start is None:
            return []
        found = []
        stack = [(start, prefix.casefold())]
        while stack:
            node, key = stack.pop()
            if node.entry is not None:
                word, weight = node.entry
                found.append((-weight, key, word))
            for ch, child in node.children.items():
                stack.append((child, key + ch))
        return [w for _, _, w in heapq.nsmallest(k, found)]

    def delete(self, word):
        key = word.casefold()
        path = [self._root]
        for ch in key:
            nxt = path[-1].children.get(ch)
            if nxt is None:
                return False
            path.append(nxt)
        if path[-1].entry is None:
            return False
        path[-1].entry = None
        self._size -= 1
        for i in range(len(key), 0, -1):  # prune empty branches
            node = path[i]
            if node.entry is None and not node.children:
                del path[i - 1].children[key[i - 1]]
            else:
                break
        return True

    def __len__(self):
        return self._size

    def __contains__(self, word):
        node = self._find(word.casefold())
        return node is not None and node.entry is not None
