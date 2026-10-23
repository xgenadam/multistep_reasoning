"""Command line: python -m sales.cli INPUT [options]."""

from __future__ import annotations

import argparse
import sys

from .aggregate import FIELDS, build_report, check_by, filter_months, parse_month
from .ingest import IngestError, read_sales
from .writers import to_csv, to_markdown


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='sales', description='Sales totals report.')
    p.add_argument('input')
    p.add_argument('--by', default='month', help=f'comma-separated subset of {FIELDS}')
    p.add_argument('--format', choices=('csv', 'md'), default='csv')
    p.add_argument('--from', dest='start')
    p.add_argument('--to', dest='end')
    p.add_argument('--output')
    p.add_argument('--strict', action='store_true')
    return p


def _usage(message: str) -> int:
    print(f'error: {message}', file=sys.stderr)
    return 2


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        by = check_by(f.strip() for f in args.by.split(','))
    except ValueError:
        return _usage(f'--by must be distinct names from {", ".join(FIELDS)}')
    try:
        start = parse_month(args.start) if args.start is not None else None
        end = parse_month(args.end) if args.end is not None else None
    except ValueError as e:
        return _usage(str(e))
    if start and end and start > end:
        return _usage('--from is later than --to')
    try:
        sales, errors = read_sales(args.input)
    except OSError as e:
        return _usage(f'cannot read {args.input}: {e.strerror or e}')
    except (IngestError, UnicodeDecodeError) as e:
        return _usage(str(e))
    for err in errors:
        print(f'line {err.line}: {err.message}', file=sys.stderr)
    report = build_report(filter_months(sales, start, end), by)
    text = to_markdown(report) if args.format == 'md' else to_csv(report)
    if args.output:
        with open(args.output, 'w', encoding='utf-8', newline='') as f:
            if not (errors and args.strict):
                f.write(text)
    elif not (errors and args.strict):
        sys.stdout.write(text)
    return 1 if errors and args.strict else 0


if __name__ == '__main__':
    sys.exit(main())
