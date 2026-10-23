"""Command-line interface: python -m todo.cli [--file PATH] [--today DATE] COMMAND ..."""
import argparse
import datetime
import sys

from .model import Task, parse_date
from .store import StoreError, TodoStore

EXIT_OK, EXIT_MISSING, EXIT_USAGE, EXIT_STORE = 0, 1, 2, 3


def format_task(task: Task) -> str:
    line = f'{task.id} [{"x" if task.done else " "}] {task.title}'
    if task.priority != 'normal':
        line += f' !{task.priority}'
    if task.due is not None:
        line += f' due:{task.due.isoformat()}'
    return line + ''.join(f' #{t}' for t in task.tags)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='todo')
    p.add_argument('--file', default='todo.json')
    p.add_argument('--today')
    sub = p.add_subparsers(dest='command', required=True)

    a = sub.add_parser('add')
    a.add_argument('title')
    a.add_argument('--tag', action='append', default=[])
    a.add_argument('--priority', default='normal')
    a.add_argument('--due')

    ls = sub.add_parser('list')
    ls.add_argument('--status', choices=['open', 'done', 'all'], default='open')
    ls.add_argument('--tag', action='append', default=[])
    ls.add_argument('--overdue', action='store_true')
    ls.add_argument('--sort', choices=['id', 'priority', 'due'], default='id')

    d = sub.add_parser('done')
    d.add_argument('ids', type=int, nargs='+')

    r = sub.add_parser('remove')
    r.add_argument('id', type=int)

    e = sub.add_parser('edit')
    e.add_argument('id', type=int)
    e.add_argument('--title')
    e.add_argument('--tag', action='append', default=[])
    e.add_argument('--untag', action='append', default=[])
    e.add_argument('--priority')
    e.add_argument('--due')
    e.add_argument('--no-due', action='store_true')
    return p


class _Missing(Exception):
    def __init__(self, task_id):
        self.task_id = task_id


def _date_or_none(raw):
    return None if raw is None else parse_date(raw)


def _run(args, store: TodoStore, today: datetime.date) -> list[str]:
    if args.command == 'add':
        task = store.add(args.title, args.tag, args.priority, _date_or_none(args.due))
        return [f'added {task.id}']
    if args.command == 'list':
        tasks = store.list(args.status, args.tag, overdue=args.overdue, today=today,
                           sort=args.sort)
        return [format_task(t) for t in tasks]
    if args.command == 'done':
        for task_id in args.ids:
            try:
                store.get(task_id)
            except KeyError:
                raise _Missing(task_id) from None
        return [f'done {store.mark_done(i).id}' for i in args.ids]
    try:
        if args.command == 'remove':
            return [f'removed {store.remove(args.id).id}']
        if args.command == 'edit':
            if (args.title is None and not args.tag and not args.untag
                    and args.priority is None and args.due is None and not args.no_due):
                raise ValueError('edit needs at least one change')
            if args.due is not None and args.no_due:
                raise ValueError('--due and --no-due cannot be combined')
            task = store.edit(args.id, args.title, args.tag, args.untag,
                              priority=args.priority, due=_date_or_none(args.due),
                              clear_due=args.no_due)
            return [f'edited {task.id}']
    except KeyError:
        raise _Missing(args.id) from None
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        today = datetime.date.today() if args.today is None else parse_date(args.today)
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return EXIT_USAGE
    try:
        store = TodoStore(args.file)
        lines = _run(args, store, today)
    except StoreError as e:
        print(f'error: {e}', file=sys.stderr)
        return EXIT_STORE
    except _Missing as e:
        print(f'error: no task with id {e.task_id}', file=sys.stderr)
        return EXIT_MISSING
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return EXIT_USAGE
    for line in lines:
        print(line)
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
