"""JSON-file task store with stable ids."""
import json
import os
import tempfile
from pathlib import Path

from .model import Task, normalize_tags, normalize_title

STATUSES = ('open', 'done', 'all')


class StoreError(Exception):
    """The store file cannot be read as a todo file."""


class TodoStore:
    def __init__(self, path):
        self.path = Path(path)
        self._tasks: dict[int, Task] = {}
        self._next_id = 1
        if self.path.exists():
            self._load()

    # ------------------------------------------------------------ file
    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise StoreError(f'cannot read {self.path}: {e}') from e
        if not isinstance(data, dict):
            raise StoreError('store file must hold a JSON object')
        if data.get('version') != 1:
            raise StoreError('unsupported store version')
        next_id = data.get('next_id')
        if not isinstance(next_id, int) or isinstance(next_id, bool) or next_id < 1:
            raise StoreError('next_id must be a positive integer')
        tasks = data.get('tasks')
        if not isinstance(tasks, list):
            raise StoreError('tasks must be a list')
        loaded: dict[int, Task] = {}
        for raw in tasks:
            try:
                task = Task.from_dict(raw)
            except ValueError as e:
                raise StoreError(f'invalid task: {e}') from e
            if task.id in loaded:
                raise StoreError(f'duplicate task id {task.id}')
            if task.id < 1 or task.id >= next_id:
                raise StoreError(f'task id {task.id} is not below next_id')
            loaded[task.id] = task
        self._tasks = dict(sorted(loaded.items()))
        self._next_id = next_id

    def _save(self) -> None:
        data = {'version': 1, 'next_id': self._next_id,
                'tasks': [t.to_dict() for _, t in sorted(self._tasks.items())]}
        directory = self.path.parent if str(self.path.parent) else Path('.')
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.todo-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                f.write('\n')
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------ reads
    def _require(self, task_id: int) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise KeyError(task_id) from None

    def get(self, task_id: int) -> Task:
        return self._require(task_id).copy()

    def list(self, status: str = 'open', tags=()) -> list[Task]:
        if status not in STATUSES:
            raise ValueError(f'status must be one of {", ".join(STATUSES)}')
        wanted = set(normalize_tags(tags))
        out = []
        for task in self._tasks.values():
            if status == 'open' and task.done or status == 'done' and not task.done:
                continue
            if wanted and not wanted & set(task.tags):
                continue
            out.append(task.copy())
        return out

    # ------------------------------------------------------------ writes
    def add(self, title: str, tags=()) -> Task:
        task = Task(self._next_id, normalize_title(title), normalize_tags(tags))
        self._tasks[task.id] = task
        self._next_id += 1
        self._save()
        return task.copy()

    def mark_done(self, task_id: int) -> Task:
        task = self._require(task_id)
        if not task.done:
            task.done = True
            self._save()
        return task.copy()

    def remove(self, task_id: int) -> Task:
        task = self._require(task_id)
        del self._tasks[task_id]
        self._save()
        return task.copy()

    def edit(self, task_id: int, title: str | None = None, add_tags=(),
             remove_tags=()) -> Task:
        task = self._require(task_id)
        new_title = task.title if title is None else normalize_title(title)
        adding = set(normalize_tags(add_tags))
        removing = set(normalize_tags(remove_tags))
        task.title = new_title
        task.tags = sorted((set(task.tags) | adding) - removing)
        self._save()
        return task.copy()
