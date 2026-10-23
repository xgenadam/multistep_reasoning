import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SCRIPT = HERE / 'wordfreq.py'


def run(*args):
    assert SCRIPT.is_file(), 'wordfreq.py is missing'
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=HERE,
                          capture_output=True, text=True, timeout=30)


@pytest.fixture
def text(tmp_path):
    p = tmp_path / 'in.txt'
    p.write_text('The cat and the hat. THE end!\nA cat, a bat; and_more 42 42\n', encoding='utf-8')
    return p


def lines(proc):
    return proc.stdout.splitlines()


def test_counts_sorted_by_count_then_word(text):
    p = run(text)
    assert p.returncode == 0
    assert lines(p) == ['3\tthe', '2\t42', '2\ta', '2\tand', '2\tcat',
                        '1\tbat', '1\tend', '1\that', '1\tmore']


def test_tab_separated_format(text):
    first = run(text).stdout.split('\n')[0]
    assert first == '3\tthe'


def test_top(text):
    p = run(text, '--top', 3)
    assert lines(p) == ['3\tthe', '2\t42', '2\ta']
    assert lines(run(text, '--top', 100)) == lines(run(text))


@pytest.mark.parametrize('bad', ['0', '-1', 'x', '1.5'])
def test_top_must_be_positive_integer(text, bad):
    p = run(text, '--top', bad)
    assert p.returncode == 2
    assert p.stdout == ''


def test_apostrophes_inside_words(tmp_path):
    f = tmp_path / 'a.txt'
    f.write_text("Don't stop. don't! It's o'clock 'quoted' rock'n'roll can''t\n", encoding='utf-8')
    assert lines(run(f)) == ['2\tdon\'t', '1\tcan', '1\tit\'s', '1\to\'clock', '1\tquoted',
                             "1\trock'n'roll", '1\tstop', '1\tt']


def test_casefold_and_unicode(tmp_path):
    f = tmp_path / 'u.txt'
    f.write_text('Straße STRASSE café Café naïve\n', encoding='utf-8')
    assert lines(run(f)) == ['2\tcafé', '2\tstrasse', '1\tnaïve']


def test_stopwords(text, tmp_path):
    sw = tmp_path / 'stop.txt'
    sw.write_text('# common words\n  THE  \n\nAnd\n#cat\n', encoding='utf-8')
    assert lines(run(text, '--stopwords', sw)) == ['2\t42', '2\ta', '2\tcat',
                                                   '1\tbat', '1\tend', '1\that', '1\tmore']


def test_stopwords_with_top(text, tmp_path):
    sw = tmp_path / 'stop.txt'
    sw.write_text('the\n42\n', encoding='utf-8')
    assert lines(run(text, '--stopwords', sw, '--top', 2)) == ['2\ta', '2\tand']


def test_empty_file(tmp_path):
    f = tmp_path / 'e.txt'
    f.write_text('... --- !!!\n', encoding='utf-8')
    p = run(f)
    assert p.returncode == 0 and p.stdout == ''


def test_missing_file(tmp_path):
    missing = tmp_path / 'nope.txt'
    p = run(missing)
    assert p.returncode == 1
    assert p.stdout == ''
    assert f'wordfreq: cannot read {missing}' in p.stderr


def test_missing_stopwords_file(text, tmp_path):
    missing = tmp_path / 'nostop.txt'
    p = run(text, '--stopwords', missing)
    assert p.returncode == 1
    assert p.stdout == ''
    assert f'wordfreq: cannot read {missing}' in p.stderr


def test_no_arguments_is_usage_error():
    p = run()
    assert p.returncode == 2
