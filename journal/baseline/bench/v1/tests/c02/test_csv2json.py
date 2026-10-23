import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / 'csv2json.py'


def run(cwd, *args):
    res = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                         capture_output=True, timeout=30)
    res.stdout = res.stdout.decode('utf-8')
    res.stderr = res.stderr.decode('utf-8')
    return res


def csv_file(tmp_path, data: bytes, name='in.csv'):
    (tmp_path / name).write_bytes(data)
    return name


def test_basic_compact_output(tmp_path):
    p = csv_file(tmp_path, b'name,age\nAda,36\nAlan,41\n')
    res = run(tmp_path, p)
    assert res.returncode == 0
    assert res.stderr == ''
    assert res.stdout == '[{"name": "Ada", "age": "36"}, {"name": "Alan", "age": "41"}]\n'


def test_values_stay_strings(tmp_path):
    p = csv_file(tmp_path, b'a,b,c\n1,2.5,true\n')
    assert json.loads(run(tmp_path, p).stdout) == [{'a': '1', 'b': '2.5', 'c': 'true'}]


def test_keys_in_header_order(tmp_path):
    p = csv_file(tmp_path, b'z,a,m\n1,2,3\n')
    assert run(tmp_path, p).stdout == '[{"z": "1", "a": "2", "m": "3"}]\n'


def test_quoted_commas_and_doubled_quotes(tmp_path):
    p = csv_file(tmp_path, b'id,text\n1,"Hello, world"\n2,"She said ""hi"""\n')
    assert json.loads(run(tmp_path, p).stdout) == [
        {'id': '1', 'text': 'Hello, world'},
        {'id': '2', 'text': 'She said "hi"'},
    ]


def test_newline_inside_quoted_field(tmp_path):
    p = csv_file(tmp_path, b'id,note\n1,"line one\nline two"\n2,x\n')
    assert json.loads(run(tmp_path, p).stdout) == [
        {'id': '1', 'note': 'line one\nline two'},
        {'id': '2', 'note': 'x'},
    ]


def test_crlf_records_and_crlf_inside_quotes(tmp_path):
    p = csv_file(tmp_path, b'id,note\r\n1,"a\r\nb"\r\n2,c\r\n')
    assert json.loads(run(tmp_path, p).stdout) == [
        {'id': '1', 'note': 'a\r\nb'},
        {'id': '2', 'note': 'c'},
    ]


def test_short_record_gets_null(tmp_path):
    p = csv_file(tmp_path, b'a,b,c\n1\n1,2\n1,2,\n')
    assert json.loads(run(tmp_path, p).stdout) == [
        {'a': '1', 'b': None, 'c': None},
        {'a': '1', 'b': '2', 'c': None},
        {'a': '1', 'b': '2', 'c': ''},
    ]


def test_long_record_is_an_error(tmp_path):
    p = csv_file(tmp_path, b'a,b\n1,2\n\n1,2,3\n')
    res = run(tmp_path, p)
    assert res.returncode == 1
    assert res.stdout == ''
    assert res.stderr.strip() == 'csv2json.py: record 3 has 3 fields, expected 2'


def test_blank_lines_skipped(tmp_path):
    p = csv_file(tmp_path, b'\n\na,b\n\n1,2\n\n\n3,4\n\n')
    assert json.loads(run(tmp_path, p).stdout) == [{'a': '1', 'b': '2'},
                                                   {'a': '3', 'b': '4'}]


def test_header_only_prints_empty_array(tmp_path):
    p = csv_file(tmp_path, b'a,b\n')
    res = run(tmp_path, p)
    assert res.returncode == 0
    assert res.stdout == '[]\n'


def test_byte_order_mark_is_dropped(tmp_path):
    p = csv_file(tmp_path, b'\xef\xbb\xbfname,age\nAda,36\n')
    assert json.loads(run(tmp_path, p).stdout) == [{'name': 'Ada', 'age': '36'}]


def test_non_ascii_written_raw(tmp_path):
    p = csv_file(tmp_path, 'city\nKøbenhavn\n東京\n'.encode('utf-8'))
    assert run(tmp_path, p).stdout == '[{"city": "København"}, {"city": "東京"}]\n'


def test_indent_two(tmp_path):
    p = csv_file(tmp_path, b'a,b\n1,2\n')
    res = run(tmp_path, p, '--indent', '2')
    assert res.returncode == 0
    assert res.stdout == '[\n  {\n    "a": "1",\n    "b": "2"\n  }\n]\n'


def test_indent_zero(tmp_path):
    p = csv_file(tmp_path, b'a\nx\n')
    assert run(tmp_path, p, '--indent', '0').stdout == '[\n{\n"a": "x"\n}\n]\n'


def test_indent_before_path(tmp_path):
    p = csv_file(tmp_path, b'a\nx\n')
    assert run(tmp_path, '--indent', '1', p).stdout == '[\n {\n  "a": "x"\n }\n]\n'


@pytest.mark.parametrize('bad', ['-1', 'two', '1.5'])
def test_bad_indent_is_usage_error(tmp_path, bad):
    p = csv_file(tmp_path, b'a\nx\n')
    res = run(tmp_path, p, '--indent', bad)
    assert res.returncode == 2
    assert 'usage' in res.stderr.lower()
    assert res.stdout == ''


def test_missing_file(tmp_path):
    res = run(tmp_path, 'nope.csv')
    assert res.returncode == 2
    assert res.stdout == ''
    assert res.stderr.strip() == 'csv2json.py: no such file: nope.csv'


def test_directory_is_no_such_file(tmp_path):
    (tmp_path / 'd').mkdir()
    res = run(tmp_path, 'd')
    assert res.returncode == 2
    assert res.stderr.strip() == 'csv2json.py: no such file: d'


@pytest.mark.parametrize('data', [b'', b'\n\n\r\n'])
def test_empty_file(tmp_path, data):
    p = csv_file(tmp_path, data, 'e.csv')
    res = run(tmp_path, p)
    assert res.returncode == 2
    assert res.stdout == ''
    assert res.stderr.strip() == 'csv2json.py: empty file: e.csv'
