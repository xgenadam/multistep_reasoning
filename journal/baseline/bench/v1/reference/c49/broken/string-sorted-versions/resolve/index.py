"""An in-memory package index."""

from __future__ import annotations

from .versions import Range, Version


class PackageIndex:
    def __init__(self):
        self._releases: dict[str, dict[Version, dict[str, Range]]] = {}

    def add(self, name: str, version: str, requires: dict[str, str] | None = None) -> None:
        v = Version(version)
        deps = {dep: Range(spec) for dep, spec in (requires or {}).items()}
        releases = self._releases.setdefault(name, {})
        if v in releases:
            raise ValueError(f'{name} {v} already added')
        releases[v] = deps

    def versions(self, name: str) -> list[Version]:
        return sorted(self._releases.get(name, {}), key=str, reverse=True)

    def requirements(self, name: str, version: Version) -> dict[str, Range]:
        return dict(self._releases[name][version])

    @classmethod
    def from_dict(cls, data: dict) -> 'PackageIndex':
        index = cls()
        for name, releases in data.items():
            for version, requires in releases.items():
                index.add(name, version, requires)
        return index
