"""Count lines, words and characters per file and print an aligned table."""
import argparse
import os
import sys

PROG = 'wordcount.py'


def count_text(text: str) -> tuple[int, int, int]:
    lines = text.count('\n')
    if text and not text.endswith('\n'):
        lines += 1
    return lines, len(text.split()), len(text)


def read_file(path: str) -> str:
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def format_table(rows: list[tuple[int, int, int, str]]) -> str:
    header = ('lines', 'words', 'chars', 'file')
    cells = [header] + [(str(a), str(b), str(c), name) for a, b, c, name in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(3)]
    out = []
    for row in cells:
        nums = [row[i].rjust(widths[i]) for i in range(3)]
        out.append('  '.join(nums + [row[3]]))
    return '\n'.join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__)
    parser.add_argument('files', nargs='+', metavar='FILE')
    args = parser.parse_args(argv)

    rows = []
    failed = False
    for path in args.files:
        if not os.path.isfile(path):
            print(f'{PROG}: cannot read {path}', file=sys.stderr)
            failed = True
            continue
        try:
            text = read_file(path)
        except (OSError, UnicodeDecodeError):
            print(f'{PROG}: cannot read {path}', file=sys.stderr)
            failed = True
            continue
        rows.append((*count_text(text), path))

    if rows:
        if len(rows) >= 2:
            totals = tuple(sum(r[i] for r in rows) for i in range(3))
            rows.append((*totals, 'total'))
        print(format_table(rows))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
