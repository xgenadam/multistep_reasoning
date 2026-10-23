import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from logagg import (ParseError, Record, filter_records, parse_clf, parse_jsonl, parse_line,
                    percentile, read_records, summarize)

HERE = Path(__file__).resolve().parent
UTC = timezone.utc

CLF = '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif?x=1 HTTP/1.0" 200 2326'
JSONL = ('{"ts": "2000-10-10T20:55:36Z", "client": "127.0.0.1", "method": "get", '
         '"path": "/apache_pb.gif?x=1", "status": 200, "bytes": 2326}')


def at(h, m=0, s=0):
    return datetime(2026, 5, 4, h, m, s, tzinfo=UTC)


def rec(path='/', status=200, size=0, latency=None, when=None):
    return Record(when or at(12), '10.0.0.1', 'GET', path, status, size, latency)


# ---------------------------------------------------------------- parsers

def test_parse_clf_fields():
    r = parse_clf(CLF)
    assert r == Record(datetime(2000, 10, 10, 20, 55, 36, tzinfo=UTC), '127.0.0.1', 'GET',
                       '/apache_pb.gif', 200, 2326, None)
    assert r.time.utcoffset() == timedelta(0)


def test_both_formats_give_equal_records():
    assert parse_clf(CLF) == parse_jsonl(JSONL)
    assert parse_line(CLF) == parse_line(JSONL) == parse_line('   ' + JSONL)


def test_clf_latency_dash_size_and_positive_offset():
    r = parse_clf('10.1.1.1 - - [01/Jan/2026:00:30:00 +0130] "post //api///items#top HTTP/1.1" '
                  '201 - 12500')
    assert r.time == datetime(2025, 12, 31, 23, 0, tzinfo=UTC)
    assert (r.method, r.path, r.status, r.size) == ('POST', '/api/items', 201, 0)
    assert r.latency_ms == 12.5 and isinstance(r.latency_ms, float)


@pytest.mark.parametrize('line', [
    '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" 200',
    '127.0.0.1 - - [10/Foo/2000:13:55:36 -0700] "GET /x HTTP/1.0" 200 5',
    '127.0.0.1 - - [10/Oct/2000:13:55:36] "GET /x HTTP/1.0" 200 5',
    '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /x" 200 5',
    '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET x HTTP/1.0" 200 5',
    '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "G3T /x HTTP/1.0" 200 5',
    '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" 99 5',
    '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" 200 -5',
])
def test_clf_errors(line):
    with pytest.raises(ParseError):
        parse_clf(line)


def test_jsonl_offsets_strings_and_optionals():
    r = parse_jsonl('{"ts": "2026-05-04T14:00:00+02:00", "client": "c", "method": "Delete", '
                    '"path": "/a?b", "status": "404", "latency_ms": 7, "extra": 1}')
    assert r == Record(at(12), 'c', 'DELETE', '/a', 404, 0, 7.0)
    r2 = parse_jsonl('{"ts": "2026-05-04T12:00:00+00:00", "client": "c", "method": "GET", '
                     '"path": "/", "status": 200, "bytes": null, "latency_ms": null}')
    assert r2.size == 0 and r2.latency_ms is None


@pytest.mark.parametrize('line', [
    'not json',
    '[1, 2]',
    '{"ts": "2026-05-04T12:00:00", "client": "c", "method": "GET", "path": "/", "status": 200}',
    '{"client": "c", "method": "GET", "path": "/", "status": 200}',
    '{"ts": "2026-05-04T12:00:00Z", "client": "", "method": "GET", "path": "/", "status": 200}',
    '{"ts": "2026-05-04T12:00:00Z", "client": "c", "method": "GET", "path": "/", "status": 700}',
    '{"ts": "2026-05-04T12:00:00Z", "client": "c", "method": "GET", "path": "/", "status": 200, '
    '"latency_ms": -1}',
])
def test_jsonl_errors(line):
    with pytest.raises(ParseError) as exc:
        parse_jsonl(line)
    assert isinstance(exc.value, ValueError)


def test_parse_line_forced_format_and_unknown():
    with pytest.raises(ParseError):
        parse_line(JSONL, 'clf')
    assert parse_line(CLF, 'clf').status == 200
    with pytest.raises(ValueError):
        parse_line(CLF, 'xml')


def test_read_records_bad_line_numbers_and_blanks():
    lines = [CLF + '\n', '\n', 'garbage\n', '   ', JSONL, '{"ts": 1}']
    records, bad = read_records(lines)
    assert len(records) == 2
    assert bad == [3, 6]


# ---------------------------------------------------------------- stats

def test_percentile_nearest_rank():
    data = [15, 20, 35, 40, 50]
    assert percentile(data, 30) == 20
    assert percentile(data, 40) == 20
    assert percentile(data, 50) == 35
    assert percentile(data, 100) == 50
    assert percentile(data, 0.1) == 15
    assert percentile([3, 1, 2], 95) == 3
    assert percentile(list(range(1, 21)), 95) == 19


@pytest.mark.parametrize('values, p', [([], 50), ([1], 0), ([1], 101), ([1], -5)])
def test_percentile_errors(values, p):
    with pytest.raises(ValueError):
        percentile(values, p)


def test_filter_records_window_and_status():
    rs = [rec(status=200, when=at(9)), rec(status=404, when=at(10)),
          rec(status=503, when=at(11)), rec(status=404, when=at(12))]
    assert filter_records(rs, since=at(10), until=at(12)) == rs[1:3]
    assert filter_records(rs, status='4xx') == [rs[1], rs[3]]
    assert filter_records(rs, status='503') == [rs[2]]
    assert filter_records(rs, since=at(10), status='404') == [rs[1], rs[3]]
    with pytest.raises(ValueError):
        filter_records(rs, status='4x')


def test_summarize_shape_and_values():
    rs = [rec('/a', 200, 100, 10.0, at(10)), rec('/b', 200, 50, 30.0, at(9)),
          rec('/a', 404, 0, None, at(11)), rec('/c', 503, 25, 20.0, at(12)),
          rec('/b', 301, 5, 40.0, at(8))]
    s = summarize(rs)
    assert s == {
        'requests': 5, 'bytes': 180,
        'classes': {'1xx': 0, '2xx': 2, '3xx': 1, '4xx': 1, '5xx': 1},
        'codes': {'200': 2, '301': 1, '404': 1, '503': 1},
        'latency_ms': {'count': 4, 'p50': 20.0, 'p95': 40.0, 'max': 40.0},
        'top_paths': [['/a', 2], ['/b', 2], ['/c', 1]],
        'first': '2026-05-04T08:00:00+00:00', 'last': '2026-05-04T12:00:00+00:00',
    }
    assert list(s['classes']) == ['1xx', '2xx', '3xx', '4xx', '5xx']
    assert list(s['codes']) == ['200', '301', '404', '503']


def test_summarize_top_and_empty():
    rs = [rec('/z'), rec('/y'), rec('/z'), rec('/x')]
    assert summarize(rs, top=2)['top_paths'] == [['/z', 2], ['/x', 1]]
    assert summarize(rs, top=0)['top_paths'] == []
    empty = summarize([])
    assert empty['requests'] == 0 and empty['first'] is None and empty['last'] is None
    assert empty['latency_ms'] == {'count': 0, 'p50': None, 'p95': None, 'max': None}
    with pytest.raises(ValueError):
        summarize(rs, top=-1)


# ---------------------------------------------------------------- CLI

def cli(*args):
    return subprocess.run([sys.executable, '-m', 'logagg.cli', *args], cwd=HERE,
                          capture_output=True, text=True, timeout=30)


@pytest.fixture
def logs(tmp_path):
    old = tmp_path / 'old.log'
    old.write_text(
        '10.0.0.1 - - [04/May/2026:12:00:00 +0000] "GET /index.html HTTP/1.1" 200 1000 12000\n'
        '10.0.0.2 - - [04/May/2026:12:01:00 +0000] "GET /index.html?x HTTP/1.1" 200 1000 80500\n'
        'corrupted line\n'
        '10.0.0.3 - - [04/May/2026:12:02:00 +0000] "GET /api/items HTTP/1.1" 500 96\n')
    new = tmp_path / 'new.jsonl'
    new.write_text(
        '{"ts": "2026-05-04T12:03:00Z", "client": "a", "method": "GET", "path": "/index.html",'
        ' "status": 200, "bytes": 1000, "latency_ms": 12}\n'
        '\n'
        '{"ts": "2026-05-04T14:04:00+02:00", "client": "b", "method": "POST", '
        '"path": "/api/items", "status": 404, "bytes": 0}\n'
        '{"ts": "2026-05-04T12:05:00Z", "client": "c", "method": "GET", "path": "/health",'
        ' "status": 204, "bytes": 2000}\n')
    return [str(old), str(new)]


def test_cli_text_report(logs):
    r = cli(*logs)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ('requests: 6\n'
                        'bad lines: 1\n'
                        'bytes: 5096\n'
                        'status: 1xx=0 2xx=4 3xx=0 4xx=1 5xx=1\n'
                        'latency: p50=12.0 ms p95=80.5 ms max=80.5 ms\n'
                        'top paths:\n'
                        '  3 /index.html\n'
                        '  2 /api/items\n'
                        '  1 /health\n')


def test_cli_json_with_filters(logs):
    r = cli(*logs, '--json', '--since', '2026-05-04T12:02:00', '--until',
            '2026-05-04T14:05:00+02:00', '--top', '1')
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data['bad_lines'] == 1
    assert data['requests'] == 3
    assert data['codes'] == {'200': 1, '404': 1, '500': 1}
    assert data['top_paths'] == [['/api/items', 2]]
    assert data['first'] == '2026-05-04T12:02:00+00:00'
    assert r.stdout == json.dumps(data, indent=2) + '\n'


def test_cli_status_filter_and_no_latency(logs):
    r = cli(*logs, '--status', '4xx')
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert lines[0] == 'requests: 1'
    assert 'latency: n/a' in lines
    r = cli(*logs, '--status', '302')
    assert r.stdout.endswith('top paths:\n  none\n')


def test_cli_forced_format_counts_bad(logs):
    r = cli(logs[1], '--format', 'clf')
    assert r.returncode == 0
    assert r.stdout.splitlines()[:2] == ['requests: 0', 'bad lines: 3']


@pytest.mark.parametrize('extra', [['--status', 'bad'], ['--since', 'yesterday'],
                                   ['--top', '-1']])
def test_cli_usage_errors(logs, extra):
    r = cli(*logs, *extra)
    assert r.returncode == 2 and r.stderr.startswith('error:') and r.stdout == ''


def test_cli_missing_file(logs, tmp_path):
    r = cli(logs[0], str(tmp_path / 'missing.log'))
    assert r.returncode == 2 and r.stderr.startswith('error:') and r.stdout == ''
