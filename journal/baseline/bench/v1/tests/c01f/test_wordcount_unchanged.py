import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / 'wordcount.py'


def run(cwd, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=30)


def write(dirpath, name, text):
    path = dirpath / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))
    return name


def test_single_file_exact_output(tmp_path):
    write(tmp_path, 'a.txt', 'one two\nthree\n')
    res = run(tmp_path, 'a.txt')
    assert res.returncode == 0
    assert res.stdout == ('lines  words  chars  file\n'
                          '    2      3     14  a.txt\n')
    assert res.stderr == ''


def test_no_total_row_for_one_file(tmp_path):
    write(tmp_path, 'a.txt', 'x\n')
    out = run(tmp_path, 'a.txt').stdout
    assert 'total' not in out
    assert len(out.splitlines()) == 2


def test_two_files_with_total_in_argument_order(tmp_path):
    write(tmp_path, 'b.txt', 'alpha beta\n')
    write(tmp_path, 'a.txt', 'gamma\ndelta\nepsilon\n')
    res = run(tmp_path, 'b.txt', 'a.txt')
    assert res.returncode == 0
    assert res.stdout.splitlines() == [
        'lines  words  chars  file',
        '    1      2     11  b.txt',
        '    3      3     20  a.txt',
        '    4      5     31  total',
    ]


def test_columns_widen_for_large_numbers(tmp_path):
    write(tmp_path, 'big.txt', 'word\n' * 123456)
    write(tmp_path, 's.txt', 'a')
    lines = run(tmp_path, 'big.txt', 's.txt').stdout.splitlines()
    assert lines == [
        ' lines   words   chars  file',
        '123456  123456  617280  big.txt',
        '     1       1       1  s.txt',
        '123457  123457  617281  total',
    ]


def test_path_shown_as_given(tmp_path):
    write(tmp_path, 'sub/dir/n.txt', 'hi there\n')
    out = run(tmp_path, 'sub/dir/n.txt').stdout.splitlines()
    assert out[1] == '    1      2      9  sub/dir/n.txt'


def test_last_line_without_newline_counts(tmp_path):
    write(tmp_path, 'a.txt', 'first\nsecond')
    out = run(tmp_path, 'a.txt').stdout.splitlines()
    assert out[1] == '    2      2     12  a.txt'


def test_empty_file(tmp_path):
    write(tmp_path, 'e.txt', '')
    res = run(tmp_path, 'e.txt')
    assert res.returncode == 0
    assert res.stdout.splitlines()[1] == '    0      0      0  e.txt'


def test_chars_are_code_points_not_bytes(tmp_path):
    write(tmp_path, 'u.txt', 'naïve café 日本\n')
    out = run(tmp_path, 'u.txt').stdout.splitlines()
    assert out[1] == '    1      3     14  u.txt'


def test_crlf_counts_two_chars(tmp_path):
    (tmp_path / 'w.txt').write_bytes(b'a b\r\nc\r\n')
    out = run(tmp_path, 'w.txt').stdout.splitlines()
    assert out[1] == '    2      3      8  w.txt'


def test_words_split_on_any_whitespace(tmp_path):
    write(tmp_path, 'a.txt', '  lead\ttab   many    spaces \n\n  \n')
    out = run(tmp_path, 'a.txt').stdout.splitlines()
    assert out[1] == '    3      4     33  a.txt'


def test_missing_file_reported_others_counted(tmp_path):
    write(tmp_path, 'a.txt', 'x y\n')
    write(tmp_path, 'b.txt', 'z\n')
    res = run(tmp_path, 'a.txt', 'nope.txt', 'b.txt')
    assert res.returncode == 1
    assert res.stderr.splitlines() == ['wordcount.py: cannot read nope.txt']
    assert res.stdout.splitlines() == [
        'lines  words  chars  file',
        '    1      2      4  a.txt',
        '    1      1      2  b.txt',
        '    2      3      6  total',
    ]


def test_missing_file_leaves_one_row_without_total(tmp_path):
    write(tmp_path, 'a.txt', 'x y\n')
    res = run(tmp_path, 'missing', 'a.txt')
    assert res.returncode == 1
    assert res.stdout.splitlines() == ['lines  words  chars  file',
                                       '    1      2      4  a.txt']


def test_all_missing_prints_nothing(tmp_path):
    res = run(tmp_path, 'x.txt', 'y.txt')
    assert res.returncode == 1
    assert res.stdout == ''
    assert res.stderr.splitlines() == ['wordcount.py: cannot read x.txt',
                                       'wordcount.py: cannot read y.txt']


def test_directory_is_not_readable(tmp_path):
    (tmp_path / 'd').mkdir()
    res = run(tmp_path, 'd')
    assert res.returncode == 1
    assert res.stderr.strip() == 'wordcount.py: cannot read d'
    assert res.stdout == ''


def test_no_arguments_is_usage_error(tmp_path):
    res = run(tmp_path)
    assert res.returncode == 2
    assert 'usage' in res.stderr.lower()
    assert res.stdout == ''


def test_no_trailing_spaces(tmp_path):
    write(tmp_path, 'a.txt', 'a\n')
    write(tmp_path, 'long-name.txt', 'b c d\n')
    out = run(tmp_path, 'a.txt', 'long-name.txt').stdout
    assert out.endswith('\n')
    for line in out.splitlines():
        assert line == line.rstrip()
