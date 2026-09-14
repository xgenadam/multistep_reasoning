"""On-disk universe/series/work tree for bound MCP sessions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


def slug(value: str) -> str:
    """Turn a title into a safe directory or file name."""
    text = re.sub(r'[^a-zA-Z0-9._-]+', '-', value.strip()).strip('-').lower()
    return text or 'untitled'


@dataclass(frozen=True)
class WorkBinding:
    """Session mapping onto one work under storage.root."""

    universe: str
    series: str
    work: str


class Workspace:
    """Read/write markdown documents for a bound session."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._bindings: dict[str, WorkBinding] = {}

    def bind(
        self, session_id: str, universe: str, series: str, work: str
    ) -> WorkBinding:
        """Attach a session to a work and create its documents directory."""
        binding = WorkBinding(
            universe=slug(universe),
            series=slug(series),
            work=slug(work),
        )
        self._bindings[session_id] = binding
        self.documents_dir(session_id).mkdir(parents=True, exist_ok=True)
        return binding

    def binding(self, session_id: str) -> WorkBinding | None:
        """Return the work this session is attached to, if any."""
        return self._bindings.get(session_id)

    def unbind(self, session_id: str) -> None:
        """Forget the session mapping. Does not delete files."""
        self._bindings.pop(session_id, None)

    def documents_dir(self, session_id: str) -> Path:
        """Path to universes/.../works/.../documents for this session."""
        binding = self._require_binding(session_id)
        return (
            self.root
            / 'universes'
            / binding.universe
            / 'series'
            / binding.series
            / 'works'
            / binding.work
            / 'documents'
        )

    def write_document(self, session_id: str, doc_id: str, markdown: str) -> Path:
        """Write one markdown file; used for parts, _index, and _latest."""
        directory = self.documents_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{slug(doc_id)}.md'
        path.write_text(markdown, encoding='utf-8')
        return path

    def list_documents(self, session_id: str) -> list[dict]:
        """List markdown files in the bound work (id, path, size)."""
        directory = self.documents_dir(session_id)
        if not directory.is_dir():
            return []
        items = []
        for path in sorted(directory.glob('*.md')):
            items.append(
                {
                    'id': path.stem,
                    'path': str(path),
                    'chars': path.stat().st_size,
                }
            )
        return items

    def read_document(self, session_id: str, doc_id: str) -> str:
        """Return the full markdown of one document id."""
        path = self.documents_dir(session_id) / f'{slug(doc_id)}.md'
        if not path.is_file():
            raise FileNotFoundError(f'no document {doc_id!r} in bound work')
        return path.read_text(encoding='utf-8')

    def search_workspace(self, session_id: str, query: str) -> list[dict]:
        """Keyword search over bound markdown; returns id, path, excerpt."""
        if not query.strip():
            return []
        needle = query.lower()
        hits = []
        for item in self.list_documents(session_id):
            text = Path(item['path']).read_text(encoding='utf-8')
            index = text.lower().find(needle)
            if index < 0:
                continue
            start = max(0, index - 80)
            excerpt = text[start : start + 160]
            hits.append(
                {
                    'id': item['id'],
                    'path': item['path'],
                    'index': index,
                    'excerpt': excerpt,
                }
            )
        return hits

    def _require_binding(self, session_id: str) -> WorkBinding:
        binding = self._bindings.get(session_id)
        if binding is None:
            raise ValueError(
                f'session {session_id!r} is not bound; call bind_work first'
            )
        return binding
