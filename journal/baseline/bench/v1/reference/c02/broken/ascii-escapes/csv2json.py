"""Convert a CSV file (header row as keys) to a JSON array of objects."""
import argparse
import csv
import json
import os
import sys

PROG = 'csv2json.py'


def non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'invalid indent: {text!r}') from None
    if value < 0:
        raise argparse.ArgumentTypeError(f'indent must be 0 or more: {text!r}')
    return value


class ConvertError(Exception):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def convert(path: str) -> list[dict]:
    if not os.path.isfile(path):
        raise ConvertError(f'no such file: {path}', 2)
    with open(path, encoding='utf-8-sig', newline='') as f:
        records = [r for r in csv.reader(f) if r]
    if not records:
        raise ConvertError(f'empty file: {path}', 2)
    header, rows = records[0], records[1:]
    out = []
    for number, row in enumerate(rows, start=2):
        if len(row) > len(header):
            raise ConvertError(
                f'record {number} has {len(row)} fields, expected {len(header)}', 1)
        padded = row + [None] * (len(header) - len(row))
        out.append(dict(zip(header, padded)))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__)
    parser.add_argument('path', metavar='PATH')
    parser.add_argument('--indent', type=non_negative_int, metavar='N')
    args = parser.parse_args(argv)
    try:
        records = convert(args.path)
    except ConvertError as e:
        print(f'{PROG}: {e}', file=sys.stderr)
        return e.status
    if args.indent is None:
        text = json.dumps(records)
    else:
        text = json.dumps(records, indent=args.indent, ensure_ascii=False)
    sys.stdout.write(text + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
