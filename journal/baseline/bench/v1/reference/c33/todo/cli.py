"""Command-line interface: python -m todo.cli [--file PATH] COMMAND ..."""
import argparse
import sys

from .model import Task
from .store import StoreError, TodoStore

EXIT_OK, EXIT_MISSING, EXIT_USAGE, EXIT_STORE = 0, 1, 2, 3


def format_task(task: Task) -> str:
    line = f'{task.id} [{"x" if task.done else " "}] {task.title}'
    return line + ''.join(f' #{t}' for t in task.tags)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='todo')
    p.add_argument('--file', default='todo.json')
    sub = p.add_subparsers(dest='command', required=True)

    a = sub.add_parser('add')
    a.add_argument('title')
    a.add_argument('--tag', action='append', default=[])

    ls = sub.add_parser('list')
    ls.add_argument('--status', choices=['open', 'done', 'all'], default='open')
    ls.add_argument('--tag', action='append', default=[])

    d = sub.add_parser('done')
    d.add_argument('ids', type=int, nargs='+')

    r = sub.add_parser('remove')
    r.add_argument('id', type=int)

    e = sub.add_parser('edit')
    e.add_argument('id', type=int)
    e.add_argument('--title')
    e.add_argument('--tag', action='append', default=[])
    e.add_argument('--untag', action='append', default=[])
    return p


class _Missing(Exception):
    def __init__(self, task_id):
        self.task_id = task_id


def _run(args, store: TodoStore) -> list[str]:
    if args.command == 'add':
        return [f'added {store.add(args.title, args.tag).id}']
    if args.command == 'list':
        return [format_task(t) for t in store.list(args.status, args.tag)]
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
            if args.title is None and not args.tag and not args.untag:
                raise ValueError('edit needs --title, --tag or --untag')
            return [f'edited {store.edit(args.id, args.title, args.tag, args.untag).id}']
    except KeyError:
        raise _Missing(args.id) from None
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        store = TodoStore(args.file)
        lines = _run(args, store)
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
