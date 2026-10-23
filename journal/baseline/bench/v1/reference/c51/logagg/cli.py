"""Command line: python -m logagg.cli FILE [FILE ...] [options]."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .parsers import read_records
from .stats import CLASSES, filter_records, summarize


def _time(text: str) -> datetime:
    when = datetime.fromisoformat(text)
    return when if when.utcoffset() is not None else when.replace(tzinfo=timezone.utc)


def _fail(message: str) -> int:
    print(f'error: {message}', file=sys.stderr)
    return 2


def render(summary: dict, bad: int) -> str:
    lat = summary['latency_ms']
    lines = [f'requests: {summary["requests"]}', f'bad lines: {bad}',
             f'bytes: {summary["bytes"]}',
             'status: ' + ' '.join(f'{c}={summary["classes"][c]}' for c in CLASSES)]
    if lat['count']:
        lines.append(f'latency: p50={lat["p50"]:.1f} ms p95={lat["p95"]:.1f} ms '
                     f'max={lat["max"]:.1f} ms')
    else:
        lines.append('latency: n/a')
    lines.append('top paths:')
    lines += [f'  {n} {p}' for p, n in summary['top_paths']] or ['  none']
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='logagg')
    ap.add_argument('files', nargs='+')
    ap.add_argument('--format', choices=('auto', 'clf', 'jsonl'), default='auto')
    ap.add_argument('--since')
    ap.add_argument('--until')
    ap.add_argument('--status')
    ap.add_argument('--top', type=int, default=3)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    try:
        since = _time(args.since) if args.since else None
        until = _time(args.until) if args.until else None
    except ValueError as e:
        return _fail(f'bad time: {e}')
    if args.top < 0:
        return _fail('--top must be >= 0')
    records, bad = [], 0
    for path in args.files:
        try:
            with open(path, encoding='utf-8') as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError) as e:
            return _fail(f'cannot read {path}: {e}')
        got, bad_lines = read_records(lines, args.format)
        records += got
        bad += len(bad_lines)
    try:
        records = filter_records(records, since, until, args.status)
    except ValueError as e:
        return _fail(str(e))
    summary = summarize(records, args.top)
    if args.json:
        sys.stdout.write(json.dumps({**summary, 'bad_lines': bad}, indent=2) + '\n')
    else:
        sys.stdout.write(render(summary, bad))
    return 0


if __name__ == '__main__':
    sys.exit(main())
