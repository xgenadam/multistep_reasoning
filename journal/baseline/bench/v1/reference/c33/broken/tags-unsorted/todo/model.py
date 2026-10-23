"""Task model and normalization rules."""
import re
from dataclasses import dataclass, field

_TAG_RE = re.compile(r'[a-z0-9][a-z0-9_-]*')


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
    return list(dict.fromkeys(normalize_tag(t) for t in tags))


@dataclass
class Task:
    id: int
    title: str
    tags: list[str] = field(default_factory=list)
    done: bool = False

    def to_dict(self) -> dict:
        return {'id': self.id, 'title': self.title, 'tags': list(self.tags), 'done': self.done}

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
        return cls(tid, normalize_title(title), normalize_tags(tags), done)

    def copy(self) -> 'Task':
        return Task(self.id, self.title, list(self.tags), self.done)
