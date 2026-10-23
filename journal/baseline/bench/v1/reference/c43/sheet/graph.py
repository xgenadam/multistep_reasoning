"""Dependency graph between cells."""
from collections import deque


class DependencyGraph:
    def __init__(self):
        self._precedents: dict[str, set[str]] = {}
        self._dependents: dict[str, set[str]] = {}

    def set_dependencies(self, cell: str, precedents) -> None:
        for old in self._precedents.pop(cell, set()):
            users = self._dependents.get(old)
            if users is not None:
                users.discard(cell)
                if not users:
                    del self._dependents[old]
        new = set(precedents)
        if new:
            self._precedents[cell] = new
            for p in new:
                self._dependents.setdefault(p, set()).add(cell)

    def precedents(self, cell: str) -> set[str]:
        return set(self._precedents.get(cell, ()))

    def dependents(self, cell: str) -> set[str]:
        return set(self._dependents.get(cell, ()))

    def all_dependents(self, cell: str) -> set[str]:
        seen: set[str] = set()
        queue = deque(self._dependents.get(cell, ()))
        while queue:
            c = queue.popleft()
            if c in seen:
                continue
            seen.add(c)
            queue.extend(self._dependents.get(c, ()))
        return seen

    def on_cycle(self, cell: str) -> bool:
        return cell in self.all_dependents(cell)

    def cycle_cells(self) -> set[str]:
        return {c for c in self._precedents if self.on_cycle(c)}
