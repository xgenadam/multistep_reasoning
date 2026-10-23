"""Depth-first resolution, newest versions first, with backtracking."""

from __future__ import annotations

from .versions import Range

ROOT = '<root>'


class ResolutionError(Exception):
    def __init__(self, package: str, explanation: str):
        super().__init__(explanation)
        self.package = package
        self.explanation = explanation


class _Search:
    def __init__(self, index, root: dict[str, Range]):
        self.index = index
        self.root = root
        self.selected: dict = {}          # name -> Version, in selection order
        self.order: list[str] = sorted(root)
        self.first_dead_end: tuple[str, str] | None = None

    def constraints(self, name: str) -> list[tuple[str, Range]]:
        out = []
        if name in self.root:
            out.append((ROOT, self.root[name]))
        for pkg, ver in self.selected.items():
            rng = self.index.requirements(pkg, ver).get(name)
            if rng is not None:
                out.append((f'{pkg} {ver}', rng))
        return out

    def conflict(self, name, version):
        """The first dependency of name@version that a selected version violates."""
        for dep, rng in sorted(self.index.requirements(name, version).items()):
            if dep in self.selected and self.selected[dep] not in rng:
                return dep, rng
        return None

    def acceptable(self, name, version, constraints) -> bool:
        return (all(version in rng for _, rng in constraints)
                and self.conflict(name, version) is None)

    def explain(self, name, constraints) -> str:
        lines = [f'cannot resolve {name}']
        lines += [f'  {who} requires {name} {rng}' for who, rng in constraints]
        versions = self.index.versions(name)
        if not versions:
            lines.append(f'  no versions of {name} are known')
        for v in versions:
            if not all(v in rng for _, rng in constraints):
                lines.append(f'  {name} {v} is excluded by the constraints')
            else:
                dep, rng = self.conflict(name, v)
                lines.append(f'  {name} {v} requires {dep} {rng}, '
                             f'but {dep} {self.selected[dep]} is selected')
        return '\n'.join(lines)

    def run(self) -> bool:
        name = next((n for n in self.order if n not in self.selected), None)
        if name is None:
            return True
        constraints = self.constraints(name)
        candidates = [v for v in self.index.versions(name)
                      if self.acceptable(name, v, constraints)]
        if not candidates:
            self.first_dead_end = (name, self.explain(name, constraints))
        for v in candidates:
            self.selected[name] = v
            added = [d for d in sorted(self.index.requirements(name, v)) if d not in self.order]
            self.order.extend(added)
            if self.run():
                return True
            del self.order[len(self.order) - len(added):]
            del self.selected[name]
        return False


def resolve(index, requirements: dict[str, str]) -> dict:
    root = {name: Range(spec) for name, spec in requirements.items()}
    search = _Search(index, root)
    if search.run():
        return dict(search.selected)
    name, explanation = search.first_dead_end
    raise ResolutionError(name, explanation)
