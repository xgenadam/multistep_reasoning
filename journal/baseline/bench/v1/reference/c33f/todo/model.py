"""Task model and normalization rules."""
import datetime
import re
from dataclasses import dataclass, field

_TAG_RE = re.compile(r'[a-z0-9][a-z0-9_-]*')
_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
PRIORITIES = ('high', 'normal', 'low')


def normalize_title(title: str) -> str:
    if not isinstance(title, str):
        raise ValueError('title must be a string')
    title = title.strip()
    if not title:
        raise ValueError('title must not be empty')
    return title


def normalize_tag(tag: str) -> str:
    if not isinstance(tag, str):
        raise ValueError('tag must be a string')
    tag = tag.strip().lower()
    if not _TAG_RE.fullmatch(tag):
        raise ValueError(f'invalid tag: {tag!r}')
    return tag


def normalize_tags(tags) -> list[str]:
    return sorted({normalize_tag(t) for t in tags})


def normalize_priority(p: str) -> str:
    if not isinstance(p, str):
        raise ValueError('priority must be a string')
    p = p.strip().lower()
    if p not in PRIORITIES:
        raise ValueError(f'priority must be one of {", ".join(PRIORITIES)}')
    return p


def parse_date(s: str) -> datetime.date:
    if not isinstance(s, str) or not _DATE_RE.fullmatch(s):
        raise ValueError(f'invalid date (want YYYY-MM-DD): {s!r}')
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        raise ValueError(f'invalid date: {s!r}') from None


@dataclass
class Task:
    id: int
    title: str
    tags: list[str] = field(default_factory=list)
    done: bool = False
    priority: str = 'normal'
    due: datetime.date | None = None

    def to_dict(self) -> dict:
        return {'id': self.id, 'title': self.title, 'tags': list(self.tags), 'done': self.done,
                'priority': self.priority,
                'due': None if self.due is None else self.due.isoformat()}

    @classmethod
    def from_dict(cls, d) -> 'Task':
        if not isinstance(d, dict):
            raise ValueError('task must be an object')
        for key in ('id', 'title', 'tags', 'done'):
            if key not in d:
                raise ValueError(f'task is missing {key!r}')
        tid, title, tags, done = d['id'], d['title'], d['tags'], d['done']
        if not isinstance(tid, int) or isinstance(tid, bool):
            raise ValueError('id must be an integer')
        if not isinstance(title, str):
            raise ValueError('title must be a string')
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ValueError('tags must be a list of strings')
        if not isinstance(done, bool):
            raise ValueError('done must be a boolean')
        priority = normalize_priority(d.get('priority', 'normal'))
        raw_due = d.get('due')
        due = None if raw_due is None else parse_date(raw_due)
        return cls(tid, normalize_title(title), normalize_tags(tags), done, priority, due)

    def copy(self) -> 'Task':
        return Task(self.id, self.title, list(self.tags), self.done, self.priority, self.due)
