import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'wordcount.py'


def run(cwd, *args, stdin=b''):
    res = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, input=stdin,
                         capture_output=True, timeout=30)
    res.stdout = res.stdout.decode('utf-8')
    res.stderr = res.stderr.decode('utf-8')
    return res


def write(dirpath, name, text):
    (dirpath / name).write_bytes(text.encode('utf-8'))
    return name


def test_stdin_in_table(tmp_path):
    res = run(tmp_path, '-', stdin=b'one two\nthree\n')
    assert res.returncode == 0
    assert res.stdout == ('lines  words  chars  file\n'
                          '    2      3     14  -\n')


def test_stdin_mixed_with_files_and_total(tmp_path):
    write(tmp_path, 'a.txt', 'x y\n')
    res = run(tmp_path, 'a.txt', '-', stdin=b'z\n')
    assert res.returncode == 0
    assert res.stdout.splitlines() == [
        'lines  words  chars  file',
        '    1      2      4  a.txt',
        '    1      1      2  -',
        '    2      3      6  total',
    ]


def test_stdin_has_no_newline_translation(tmp_path):
    res = run(tmp_path, '-', stdin=b'a b\r\nc\r\n')
    assert res.stdout.splitlines()[1] == '    2      3      8  -'


def test_stdin_is_utf8(tmp_path):
    res = run(tmp_path, '-', stdin='café 日本'.encode('utf-8'))
    assert res.stdout.splitlines()[1] == '    1      2      7  -'


def test_json_single_file_has_total(tmp_path):
    write(tmp_path, 'a.txt', 'one two\nthree\n')
    res = run(tmp_path, '--json', 'a.txt')
    assert res.returncode == 0
    assert res.stderr == ''
    assert json.loads(res.stdout) == {
        'files': [{'file': 'a.txt', 'lines': 2, 'words': 3, 'chars': 14}],
        'total': {'lines': 2, 'words': 3, 'chars': 14},
    }


def test_json_several_files_in_order(tmp_path):
    write(tmp_path, 'b.txt', 'alpha beta\n')
    write(tmp_path, 'a.txt', 'gamma\ndelta\nepsilon')
    doc = json.loads(run(tmp_path, 'b.txt', 'a.txt', '--json').stdout)
    assert doc == {
        'files': [{'file': 'b.txt', 'lines': 1, 'words': 2, 'chars': 11},
                  {'file': 'a.txt', 'lines': 3, 'words': 3, 'chars': 19}],
        'total': {'lines': 4, 'words': 5, 'chars': 30},
    }


def test_json_flag_between_files(tmp_path):
    write(tmp_path, 'a.txt', 'a\n')
    write(tmp_path, 'b.txt', 'b b\n')
    doc = json.loads(run(tmp_path, 'a.txt', '--json', 'b.txt').stdout)
    assert [f['file'] for f in doc['files']] == ['a.txt', 'b.txt']
    assert doc['total'] == {'lines': 2, 'words': 3, 'chars': 6}


def test_json_counts_are_integers(tmp_path):
    write(tmp_path, 'a.txt', 'a\n')
    doc = json.loads(run(tmp_path, '--json', 'a.txt').stdout)
    for value in (*doc['files'][0].values(), *doc['total'].values()):
        if value != 'a.txt':
            assert type(value) is int


def test_json_with_stdin(tmp_path):
    doc = json.loads(run(tmp_path, '--json', '-', stdin=b'x\r\n').stdout)
    assert doc['files'] == [{'file': '-', 'lines': 1, 'words': 1, 'chars': 3}]


def test_json_with_missing_file(tmp_path):
    write(tmp_path, 'a.txt', 'x y\n')
    res = run(tmp_path, '--json', 'gone.txt', 'a.txt')
    assert res.returncode == 1
    assert res.stderr.splitlines() == ['wordcount.py: cannot read gone.txt']
    assert json.loads(res.stdout) == {
        'files': [{'file': 'a.txt', 'lines': 1, 'words': 2, 'chars': 4}],
        'total': {'lines': 1, 'words': 2, 'chars': 4},
    }


def test_json_all_missing_still_prints(tmp_path):
    res = run(tmp_path, '--json', 'x', 'y')
    assert res.returncode == 1
    assert json.loads(res.stdout) == {'files': [],
                                      'total': {'lines': 0, 'words': 0, 'chars': 0}}


def test_json_without_files_is_usage_error(tmp_path):
    res = run(tmp_path, '--json')
    assert res.returncode == 2
    assert 'usage' in res.stderr.lower()
