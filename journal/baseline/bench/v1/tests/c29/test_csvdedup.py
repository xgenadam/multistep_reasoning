import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SCRIPT = HERE / 'csvdedup.py'

DATA = (
    'id,email,name,city\n'
    '1,a@x.org,Ann,Oslo\n'
    '2,b@x.org,Bob,Rome\n'
    '3,a@x.org,Ann B,Oslo\n'
    '4,c@x.org,Cy,Rome\n'
    '5,b@x.org,Bob,Lima\n'
    '6,a@x.org,Ann,Lima\n'
)


def run(*args):
    assert SCRIPT.is_file(), 'csvdedup.py is missing'
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=HERE,
                          capture_output=True, text=True, timeout=30)


@pytest.fixture
def csvfile(tmp_path):
    p = tmp_path / 'in.csv'
    p.write_text(DATA, encoding='utf-8', newline='')
    return p


def ids(proc):
    return [line.split(',')[0] for line in proc.stdout.splitlines()[1:]]


def test_keep_first_default(csvfile):
    p = run(csvfile, '--key', 'email')
    assert p.returncode == 0
    assert p.stdout.splitlines()[0] == 'id,email,name,city'
    assert ids(p) == ['1', '2', '4']
    assert p.stderr.strip() == 'kept 3 of 6 rows'


def test_output_is_exact(csvfile):
    p = run(csvfile, '--key', 'email', '--keep', 'first')
    assert p.stdout == 'id,email,name,city\n1,a@x.org,Ann,Oslo\n2,b@x.org,Bob,Rome\n4,c@x.org,Cy,Rome\n'


def test_keep_last_keeps_original_order(csvfile):
    p = run(csvfile, '--key', 'email', '--keep', 'last')
    assert p.returncode == 0
    assert ids(p) == ['4', '5', '6']
    assert p.stderr.strip() == 'kept 3 of 6 rows'


def test_multi_column_key(csvfile):
    assert ids(run(csvfile, '--key', 'email,city')) == ['1', '2', '4', '5', '6']
    assert ids(run(csvfile, '--key', 'name,email', '--keep', 'last')) == ['3', '4', '5', '6']


def test_quoted_fields_round_trip(tmp_path):
    p = tmp_path / 'q.csv'
    p.write_text('k,v\n"a,1","say ""hi"""\n"a,1",dup\nb,"two\nlines"\n', encoding='utf-8', newline='')
    out = run(p, '--key', 'k')
    assert out.returncode == 0
    assert out.stdout == 'k,v\n"a,1","say ""hi"""\nb,"two\nlines"\n'
    assert out.stderr.strip() == 'kept 2 of 3 rows'


def test_short_rows_count_as_empty(tmp_path):
    p = tmp_path / 's.csv'
    p.write_text('a,b\n1\n1,\n2,x\n', encoding='utf-8', newline='')
    out = run(p, '--key', 'a,b')
    assert out.stdout == 'a,b\n1\n2,x\n'


def test_header_only(tmp_path):
    p = tmp_path / 'h.csv'
    p.write_text('a,b\n', encoding='utf-8', newline='')
    out = run(p, '--key', 'a')
    assert out.returncode == 0
    assert out.stdout == 'a,b\n'
    assert out.stderr.strip() == 'kept 0 of 0 rows'


def test_unknown_column_exit_2(csvfile):
    p = run(csvfile, '--key', 'email,zip,nope')
    assert p.returncode == 2
    assert p.stdout == ''
    assert p.stderr.strip() == 'csvdedup: unknown column: zip'


def test_missing_file_exit_1(tmp_path):
    missing = tmp_path / 'none.csv'
    p = run(missing, '--key', 'a')
    assert p.returncode == 1
    assert p.stdout == ''
    assert p.stderr.strip() == f'csvdedup: cannot read {missing}'


def test_empty_file_exit_1(tmp_path):
    p = tmp_path / 'e.csv'
    p.write_text('', encoding='utf-8')
    out = run(p, '--key', 'a')
    assert out.returncode == 1
    assert out.stdout == ''
    assert out.stderr.strip() == 'csvdedup: empty file'


@pytest.mark.parametrize('args', [[], ['--keep', 'middle', '--key', 'email']])
def test_usage_errors_exit_2(csvfile, args):
    p = run(csvfile, *args)
    assert p.returncode == 2
    assert p.stdout == ''
