"""Two log parsers that share one normalisation step."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MONTHS = {m: i for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}
_CLF = re.compile(r'(\S+) (\S+) (\S+) \[([^\]]+)\] "([^"]*)" (\S+) (\S+)(?: (\d+))?')
_CLF_TIME = re.compile(r'(\d{2})/([A-Z][a-z]{2})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})')
_METHOD = re.compile(r'[A-Za-z]+')
_DIGITS = re.compile(r'[0-9]+')


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    time: datetime
    client: str
    method: str
    path: str
    status: int
    size: int
    latency_ms: float | None


def _int(value, what: str) -> int:
    if isinstance(value, bool):
        raise ParseError(f'bad {what}: {value!r}')
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _DIGITS.fullmatch(value):
        return int(value)
    raise ParseError(f'bad {what}: {value!r}')


def normalize(time, client, method, path, status, size, latency_ms) -> Record:
    if not isinstance(time, datetime) or time.utcoffset() is None:
        raise ParseError('time must be timezone-aware')
    if not isinstance(client, str) or not client:
        raise ParseError('missing client')
    if not isinstance(method, str) or not _METHOD.fullmatch(method):
        raise ParseError(f'bad method: {method!r}')
    if not isinstance(path, str) or not path.startswith('/'):
        raise ParseError(f'bad path: {path!r}')
    path = re.sub(r'/{2,}', '/', re.split(r'[?#]', path, maxsplit=1)[0])
    status = _int(status, 'status')
    if not 100 <= status <= 599:
        raise ParseError(f'status out of range: {status}')
    size = 0 if size is None or size == '-' else _int(size, 'size')
    if size < 0:
        raise ParseError('negative size')
    if latency_ms is not None:
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)) \
                or latency_ms < 0:
            raise ParseError(f'bad latency: {latency_ms!r}')
        latency_ms = float(latency_ms)
    return Record(time.astimezone(timezone.utc), client, method.upper(), path, status, size,
                  latency_ms)


def _clf_time(text: str) -> datetime:
    m = _CLF_TIME.fullmatch(text)
    if not m or m.group(2) not in MONTHS:
        raise ParseError(f'bad time: {text!r}')
    day, mon, year, hh, mm, ss, sign, oh, om = m.groups()
    offset = timedelta(hours=int(oh), minutes=int(om))
    try:
        return datetime(int(year), MONTHS[mon], int(day), int(hh), int(mm), int(ss),
                        tzinfo=timezone(-offset if sign == '+' else offset))
    except ValueError as e:
        raise ParseError(f'bad time: {text!r}') from e


def parse_clf(line: str) -> Record:
    m = _CLF.fullmatch(line.strip('\r\n'))
    if not m:
        raise ParseError('not a common log line')
    client, _ident, _user, when, request, status, size, micros = m.groups()
    parts = request.split(' ')
    if len(parts) != 3:
        raise ParseError(f'bad request line: {request!r}')
    method, path, _proto = parts
    latency = int(micros) / 1000 if micros is not None else None
    return normalize(_clf_time(when), client, method, path, status, size, latency)


def parse_jsonl(line: str) -> Record:
    try:
        data = json.loads(line)
    except ValueError as e:
        raise ParseError('invalid JSON') from e
    if not isinstance(data, dict):
        raise ParseError('not a JSON object')
    for key in ('ts', 'client', 'method', 'path', 'status'):
        if key not in data:
            raise ParseError(f'missing {key!r}')
    ts = data['ts']
    try:
        when = datetime.fromisoformat(ts)
    except (TypeError, ValueError) as e:
        raise ParseError(f'bad ts: {ts!r}') from e
    if when.utcoffset() is None:
        raise ParseError('ts has no UTC offset')
    return normalize(when, data['client'], data['method'], data['path'], data['status'],
                     data.get('bytes'), data.get('latency_ms'))


def parse_line(line: str, fmt: str = 'auto') -> Record:
    if fmt == 'auto':
        fmt = 'jsonl' if line.lstrip().startswith('{') else 'clf'
    if fmt == 'clf':
        return parse_clf(line)
    if fmt == 'jsonl':
        return parse_jsonl(line)
    raise ValueError(f'unknown format: {fmt!r}')


def read_records(lines, fmt: str = 'auto') -> tuple[list[Record], list[int]]:
    if fmt not in ('auto', 'clf', 'jsonl'):
        raise ValueError(f'unknown format: {fmt!r}')
    records, bad = [], []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            records.append(parse_line(line, fmt))
        except ParseError:
            bad.append(number)
    return records, bad
