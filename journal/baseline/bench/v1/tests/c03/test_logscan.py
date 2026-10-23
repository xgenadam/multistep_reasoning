import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / 'logscan.py'

LOG = """\
2026-03-14 09:00:01 INFO service started
2026-03-14 09:00:02 WARN disk 91% full
2026-03-14 09:00:03 INFO user ERROR-prone login
2026-03-14 09:00:04 ERROR database unreachable
not a log line at all
2026-03-14 09:00:05 DEBUG cache warmed
2026-03-14 09:00:06 warn lowercase level is not a level
2026-03-14 09:00:07 INFO retrying WARN soon
2026-03-14 09:00:08 ERROR timeout after 30s
2026-03-14 09:00:09 WARN memory high
"""


def run(cwd, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=30)


@pytest.fixture
def log(tmp_path):
    (tmp_path / 'app.log').write_text(LOG, encoding='utf-8')
    return tmp_path


def lines(*seconds):
    by_second = {l[17:19]: l for l in LOG.splitlines() if l.startswith('2026')}
    return ''.join(by_second[s] + '\n' for s in seconds)


def test_exact_level_in_file_order(log):
    res = run(log, 'app.log', 'WARN')
    assert res.returncode == 0
    assert res.stdout == lines('02', '09')
    assert res.stderr == 'count=2\n'


def test_level_word_in_message_does_not_count(log):
    res = run(log, 'app.log', 'ERROR')
    assert res.stdout == lines('04', '08')
    assert res.stderr == 'count=2\n'


def test_info_lines(log):
    res = run(log, 'app.log', 'INFO')
    assert res.stdout == lines('01', '03', '07')
    assert res.stderr == 'count=3\n'


def test_level_argument_is_case_insensitive(log):
    assert run(log, 'app.log', 'warn').stdout == lines('02', '09')
    assert run(log, 'app.log', 'Error').stdout == lines('04', '08')


def test_at_least_includes_higher_levels(log):
    res = run(log, 'app.log', 'WARN', '--at-least')
    assert res.stdout == lines('02', '04', '08', '09')
    assert res.stderr == 'count=4\n'


def test_at_least_info_is_every_levelled_line(log):
    res = run(log, '--at-least', 'app.log', 'info')
    assert res.stdout == lines('01', '02', '03', '04', '07', '08', '09')
    assert res.stderr == 'count=7\n'


def test_at_least_error_is_error_only(log):
    assert run(log, 'app.log', 'ERROR', '--at-least').stdout == lines('04', '08')


def test_limit_stops_printing_but_count_is_total(log):
    res = run(log, 'app.log', 'INFO', '--limit', '2')
    assert res.stdout == lines('01', '03')
    assert res.stderr == 'count=3\n'


def test_limit_zero(log):
    res = run(log, '--limit', '0', 'app.log', 'WARN', '--at-least')
    assert res.returncode == 0
    assert res.stdout == ''
    assert res.stderr == 'count=4\n'


def test_limit_larger_than_matches(log):
    res = run(log, 'app.log', 'WARN', '--limit', '10')
    assert res.stdout == lines('02', '09')


def test_no_match_exits_zero(tmp_path):
    (tmp_path / 'x.log').write_text('2026-01-01 00:00:00 INFO only info\n')
    res = run(tmp_path, 'x.log', 'ERROR')
    assert res.returncode == 0
    assert res.stdout == ''
    assert res.stderr == 'count=0\n'


def test_lines_kept_exactly_and_last_line_gets_newline(tmp_path):
    text = '2026-01-01 00:00:00   WARN   spaced   out  \n2026-01-01 00:00:01\tWARN\ttabs'
    (tmp_path / 'x.log').write_text(text)
    res = run(tmp_path, 'x.log', 'WARN')
    assert res.stdout == ('2026-01-01 00:00:00   WARN   spaced   out  \n'
                          '2026-01-01 00:00:01\tWARN\ttabs\n')
    assert res.stderr == 'count=2\n'


def test_short_lines_have_no_level(tmp_path):
    (tmp_path / 'x.log').write_text('ERROR\nWARN ERROR\n\n2026-01-01 00:00:00 ERROR\n')
    res = run(tmp_path, 'x.log', 'ERROR')
    assert res.stdout == '2026-01-01 00:00:00 ERROR\n'


def test_missing_file(tmp_path):
    res = run(tmp_path, 'missing.log', 'INFO')
    assert res.returncode == 1
    assert res.stdout == ''
    assert res.stderr == 'logscan.py: cannot open missing.log\n'


@pytest.mark.parametrize('args', [('DEBUG',), ('WARNING',), ('INFO', '--limit', '-1'),
                                  ('INFO', '--limit', 'x')])
def test_usage_errors(log, args):
    res = run(log, 'app.log', *args)
    assert res.returncode == 2
    assert 'usage' in res.stderr.lower()
    assert res.stdout == ''
