"""The Sheet: cell storage and incremental recalculation."""
import re

from .formula import CYCLE, FormulaError, evaluate, is_cell_name, parse_formula, references
from .graph import DependencyGraph

NUMBER_RE = re.compile(r'-?[0-9]+(\.[0-9]+)?')


def row_major(name: str) -> tuple[int, str]:
    return (int(name[1:]), name[0])


def normalize(name) -> str:
    if not isinstance(name, str) or not is_cell_name(name.upper()):
        raise ValueError(f'not a cell name: {name!r}')
    return name.upper()


class Sheet:
    def __init__(self):
        self._raw: dict[str, str] = {}
        self._trees: dict[str, object] = {}
        self._values: dict[str, object] = {}
        self._graph = DependencyGraph()
        self.evaluations = 0

    # ----------------------------------------------------------- access
    def get(self, name: str):
        return self._values.get(normalize(name))

    def raw(self, name: str) -> str:
        return self._raw.get(normalize(name), '')

    def cells(self) -> list[str]:
        return sorted(self._raw, key=row_major)

    # ----------------------------------------------------------- update
    def set(self, name: str, raw: str) -> list[str]:
        name = normalize(name)
        if not isinstance(raw, str):
            raise TypeError('raw must be a str')
        tree = None
        constant = None
        if raw.startswith('='):
            tree = parse_formula(raw[1:])  # may raise FormulaError; nothing changed yet
        elif raw == '':
            constant = None
        elif NUMBER_RE.fullmatch(raw.strip()):
            text = raw.strip()
            constant = float(text) if '.' in text else int(text)
        else:
            constant = raw

        if raw == '':
            self._raw.pop(name, None)
        else:
            self._raw[name] = raw
        if tree is None:
            self._trees.pop(name, None)
            self._graph.set_dependencies(name, ())
            self._store(name, constant)
        else:
            self._trees[name] = tree
            self._graph.set_dependencies(name, references(tree))

        affected = {name} | self._graph.all_dependents(name)
        self._recalculate(affected)
        return sorted(affected, key=row_major)

    def _store(self, name: str, value) -> None:
        if value is None:
            self._values.pop(name, None)
        else:
            self._values[name] = value

    def _recalculate(self, affected) -> None:
        pending = set()
        for cell in affected:
            if cell not in self._trees:
                continue
            if self._graph.on_cycle(cell):
                self._values[cell] = CYCLE
            else:
                pending.add(cell)
        # Push each change to the cells that use it.
        def push(cell):
            if cell in pending:
                self.evaluations += 1
                self._store(cell, evaluate(self._trees[cell], self._values.get))
            for user in sorted(self._graph.dependents(cell) & pending, key=row_major):
                push(user)
        start = [c for c in affected if c not in self._graph.all_dependents(c)
                 and not (self._graph.precedents(c) & pending)]
        for cell in sorted(start, key=row_major):
            push(cell)
