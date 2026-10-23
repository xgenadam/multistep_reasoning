import argparse
import csv
import sys


def fail(message, code):
    print(f'csvdedup: {message}', file=sys.stderr)
    sys.exit(code)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='csvdedup', description='Remove duplicate CSV rows.')
    parser.add_argument('path')
    parser.add_argument('--key', required=True)
    parser.add_argument('--keep', choices=['first', 'last'], default='first')
    args = parser.parse_args(argv)

    try:
        with open(args.path, encoding='utf-8', newline='') as f:
            rows = list(csv.reader(f))
    except (OSError, UnicodeDecodeError, csv.Error):
        fail(f'cannot read {args.path}', 1)
    if not rows:
        fail('empty file', 1)
    header, data = rows[0], rows[1:]

    idx = []
    for name in args.key.split(','):
        if name not in header:
            fail(f'unknown column: {name}', 2)
        idx.append(header.index(name))

    def key(row):
        return tuple(row[i] if i < len(row) else '' for i in idx)

    chosen = {}
    for pos, row in enumerate(data):
        k = key(row)
        if args.keep == 'last' or k not in chosen:
            chosen[k] = pos
    keep = sorted(chosen.values())

    out = csv.writer(sys.stdout, lineterminator='\n')
    out.writerow(header)
    for pos in keep:
        out.writerow(data[pos])
    print(f'kept {len(keep) + 1} of {len(rows)} rows', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
