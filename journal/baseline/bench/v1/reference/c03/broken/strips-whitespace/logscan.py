"""Print the lines of a log file at (or above) a given level."""
import argparse
import os
import sys

PROG = 'logscan.py'
LEVELS = {'INFO': 0, 'WARN': 1, 'ERROR': 2}


def level_arg(text: str) -> str:
    name = text.upper()
    if name not in LEVELS:
        raise argparse.ArgumentTypeError(f'unknown level: {text!r}')
    return name


def limit_arg(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'invalid limit: {text!r}') from None
    if value < 0:
        raise argparse.ArgumentTypeError(f'limit must be 0 or more: {text!r}')
    return value


def line_level(line: str) -> str | None:
    fields = line.split()
    if len(fields) < 3 or fields[2] not in LEVELS:
        return None
    return fields[2]


def matches(line: str, wanted: str, at_least: bool) -> bool:
    level = line_level(line)
    if level is None:
        return False
    if at_least:
        return LEVELS[level] >= LEVELS[wanted]
    return level == wanted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__)
    parser.add_argument('path', metavar='PATH')
    parser.add_argument('level', metavar='LEVEL', type=level_arg)
    parser.add_argument('--at-least', action='store_true',
                        help='also match higher levels')
    parser.add_argument('--limit', type=limit_arg, metavar='N')
    args = parser.parse_args(argv)

    if not os.path.isfile(args.path):
        print(f'{PROG}: cannot open {args.path}', file=sys.stderr)
        return 1
    count = 0
    with open(args.path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip()
            if not matches(line, args.level, args.at_least):
                continue
            count += 1
            if args.limit is None or count <= args.limit:
                sys.stdout.write(line + '\n')
    print(f'count={count}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
