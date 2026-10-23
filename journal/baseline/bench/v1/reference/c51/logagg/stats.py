"""Filtering and summary statistics over records."""

from __future__ import annotations

import math
import re
from collections import Counter

CLASSES = ('1xx', '2xx', '3xx', '4xx', '5xx')


def percentile(values, p: float):
    data = sorted(values)
    if not data:
        raise ValueError('no values')
    if not 0 < p <= 100:
        raise ValueError('p must be in (0, 100]')
    rank = math.ceil(p / 100 * len(data))
    return data[max(rank, 1) - 1]


def _status_matcher(status: str):
    if re.fullmatch(r'[1-5]xx', status):
        hundred = int(status[0])
        return lambda code: code // 100 == hundred
    if re.fullmatch(r'[1-5][0-9]{2}', status):
        exact = int(status)
        return lambda code: code == exact
    raise ValueError(f'bad status filter: {status!r}')


def filter_records(records, since=None, until=None, status=None) -> list:
    match = _status_matcher(status) if status is not None else (lambda code: True)
    return [r for r in records
            if (since is None or r.time >= since) and (until is None or r.time < until)
            and match(r.status)]


def summarize(records, top: int = 3) -> dict:
    if top < 0:
        raise ValueError('top must be >= 0')
    records = list(records)
    classes = {c: 0 for c in CLASSES}
    for r in records:
        classes[f'{r.status // 100}xx'] += 1
    codes = Counter(r.status for r in records)
    latencies = [r.latency_ms for r in records if r.latency_ms is not None]
    paths = Counter(r.path for r in records)
    times = [r.time for r in records]
    return {
        'requests': len(records),
        'bytes': sum(r.size for r in records),
        'classes': classes,
        'codes': {str(code): codes[code] for code in sorted(codes)},
        'latency_ms': {
            'count': len(latencies),
            'p50': percentile(latencies, 50) if latencies else None,
            'p95': percentile(latencies, 95) if latencies else None,
            'max': max(latencies) if latencies else None,
        },
        'top_paths': [[p, n] for p, n in sorted(paths.items(), key=lambda kv: (-kv[1], kv[0]))
                      ][:top],
        'first': min(times).isoformat() if times else None,
        'last': max(times).isoformat() if times else None,
    }
