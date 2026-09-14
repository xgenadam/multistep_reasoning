"""JSONL turn log so older (summarised) chat can be searched without stuffing history into prompts."""

from __future__ import annotations

import json
from pathlib import Path


class ConversationLog:
    """Append-only per-session log under storage.root/conversations/."""

    def __init__(self, root: Path) -> None:
        self.root = root / 'conversations'

    def _path(self, session_id: str) -> Path:
        """JSONL path for one session."""
        safe = ''.join(
            ch if ch.isalnum() or ch in '._-' else '-' for ch in session_id
        )
        return self.root / safe / 'log.jsonl'

    def append(
        self,
        session_id: str,
        role: str,
        text: str,
        summary: str | None = None,
    ) -> None:
        """Store one turn; summary defaults to a one-line clip of text."""
        path = self._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            'role': role,
            'text': text,
            'summary': summary or _one_line(text),
        }
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')

    def search(self, session_id: str, query: str, *, limit: int = 8) -> list[dict]:
        """Keyword search over stored text and summaries; does not load the whole log into the LLM."""
        if not query.strip():
            return []
        path = self._path(session_id)
        if not path.is_file():
            return []
        needle = query.lower()
        hits = []
        with path.open(encoding='utf-8') as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                blob = f'{record.get("summary", "")}\n{record.get("text", "")}'
                index = blob.lower().find(needle)
                if index < 0:
                    continue
                text = record.get('text') or ''
                start = max(0, index - 80)
                hits.append(
                    {
                        'line': line_no,
                        'role': record.get('role'),
                        'summary': record.get('summary'),
                        'excerpt': text[start : start + 160],
                    }
                )
                if len(hits) >= limit:
                    break
        return hits

    def clear(self, session_id: str) -> None:
        """Delete this session's log file."""
        path = self._path(session_id)
        if path.is_file():
            path.unlink()


def _one_line(text: str, max_chars: int = 120) -> str:
    """Collapse whitespace for the search index line."""
    collapsed = ' '.join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1] + '…'
