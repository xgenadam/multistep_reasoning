"""Count lines, words and characters per file and print an aligned table or JSON."""
import argparse
import json
import os
import sys

PROG = 'wordcount.py'


def count_text(text: str) -> tuple[int, int, int]:
    lines = text.count('\n')
    if text and not text.endswith('\n'):
        lines += 1
    return lines, len(text.split()), len(text)


def read_source(path: str) -> str:
    if path == '-':
        return sys.stdin.buffer.read().decode('utf-8')
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
    parser.add_argument('--json', action='store_true', help='print JSON instead of a table')
    args = parser.parse_intermixed_args(argv)

    rows = []
    failed = False
    for path in args.files:
        if path != '-' and not os.path.isfile(path):
            print(f'{PROG}: cannot read {path}', file=sys.stderr)
            failed = True
            continue
        try:
            text = read_source(path)
        except (OSError, UnicodeDecodeError):
            print(f'{PROG}: cannot read {path}', file=sys.stderr)
            failed = True
            continue
        rows.append((*count_text(text), path))

    totals = tuple(sum(r[i] for r in rows) for i in range(3))
    if args.json and rows:
        doc = {
            'files': [{'file': name, 'lines': a, 'words': b, 'chars': c}
                      for a, b, c, name in rows],
            'total': {'lines': totals[0], 'words': totals[1], 'chars': totals[2]},
        }
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    elif rows and not args.json:
        if len(rows) >= 2:
            rows.append((*totals, 'total'))
        print(format_table(rows))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
