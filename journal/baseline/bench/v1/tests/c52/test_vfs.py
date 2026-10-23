import subprocess
import sys
from pathlib import Path

import pytest

from vfs import (AlreadyExists, FileSystem, FSError, InvalidOperation, IsADirectory,
                 NotADirectory, NotFound, Shell, join, normalize, split)
from vfs.paths import is_within

HERE = Path(__file__).resolve().parent


def raises(exc_type, path, fn, *args, **kw):
    with pytest.raises(exc_type) as exc:
        fn(*args, **kw)
    assert isinstance(exc.value, FSError)
    assert str(exc.value) == path


@pytest.fixture
def fs():
    f = FileSystem()
    f.mkdir('/docs/notes', parents=True)
    f.write('/docs/a.txt', 'alpha\n')
    f.write('/docs/notes/b.txt', 'beta\n')
    f.mkdir('/src')
    f.write('/src/main.py', 'print(1)\n')
    return f


# ---------------------------------------------------------------- paths

def test_normalize():
    assert normalize('/a/./b//c/') == '/a/b/c'
    assert normalize('../../x', '/a/b/c') == '/a/x'
    assert normalize('/../..') == '/'
    assert normalize('..', '/') == '/'
    assert normalize('.', '/a') == '/a'
    assert normalize('b/../c', '/a') == '/a/c'
    with pytest.raises(ValueError):
        normalize('')


def test_join_split_is_within():
    assert join('/a', 'b', '../c') == '/a/c'
    assert join('/a', '/x', 'y') == '/x/y'
    assert split('/a/b') == ('/a', 'b')
    assert split('/a') == ('/', 'a')
    assert split('/') == ('/', '')
    assert is_within('/a/b', '/a') and is_within('/a', '/a') and is_within('/a', '/')
    assert not is_within('/ab', '/a') and not is_within('/a', '/a/b')


# ---------------------------------------------------------------- filesystem

def test_ls_sorted_with_dir_suffix(fs):
    fs.write('/docs/Z.txt', '')
    assert fs.ls('/docs') == ['Z.txt', 'a.txt', 'notes/']
    assert fs.ls('/') == ['docs/', 'src/']
    assert fs.ls('/docs/a.txt') == ['a.txt']
    raises(NotFound, '/nope', fs.ls, '/nope')


def test_cd_relative_paths_and_pwd(fs):
    fs.cd('docs/notes')
    assert fs.pwd() == '/docs/notes'
    assert fs.read('b.txt') == 'beta\n'
    assert fs.read('../a.txt') == 'alpha\n'
    fs.cd('../..')
    assert fs.pwd() == '/'
    raises(NotFound, '/missing', fs.cd, 'missing')
    raises(NotADirectory, '/docs/a.txt', fs.cd, '/docs/a.txt')


def test_mkdir_rules(fs):
    raises(AlreadyExists, '/docs', fs.mkdir, '/docs')
    fs.mkdir('/docs', parents=True)
    raises(AlreadyExists, '/docs/a.txt', fs.mkdir, '/docs/a.txt', parents=True)
    raises(NotFound, '/x/y', fs.mkdir, '/x/y')
    assert not fs.exists('/x')
    fs.mkdir('/x/y/z', parents=True)
    assert fs.is_dir('/x/y') and fs.is_dir('/x/y/z')
    raises(AlreadyExists, '/', fs.mkdir, '/')


def test_path_through_file_is_not_a_directory(fs):
    raises(NotADirectory, '/docs/a.txt/x', fs.mkdir, '/docs/a.txt/x', parents=True)
    raises(NotADirectory, '/docs/a.txt/x', fs.read, '/docs/a.txt/x')
    raises(NotADirectory, '/docs/a.txt/x/y', fs.write, '/docs/a.txt/x/y', 'z')
    assert fs.exists('/docs/a.txt/x') is False and fs.is_dir('/docs/a.txt') is False


def test_write_read_append(fs):
    fs.write('/docs/a.txt', 'new\n')
    fs.write('/docs/a.txt', 'more\n', append=True)
    assert fs.read('/docs/a.txt') == 'new\nmore\n'
    fs.write('/src/fresh.txt', 'x', append=True)
    assert fs.read('/src/fresh.txt') == 'x'
    raises(IsADirectory, '/docs', fs.write, '/docs', 'x')
    raises(NotFound, '/no/file.txt', fs.write, '/no/file.txt', 'x')
    raises(NotFound, '/docs/zz.txt', fs.read, '/docs/zz.txt')
    raises(IsADirectory, '/src', fs.read, '/src')


def test_rm_rules(fs):
    raises(IsADirectory, '/docs/notes', fs.rm, '/docs/notes')
    fs.rm('/docs/notes', recursive=True)
    assert fs.ls('/docs') == ['a.txt']
    fs.rm('/docs/a.txt')
    assert fs.ls('/docs') == []
    raises(NotFound, '/docs/a.txt', fs.rm, '/docs/a.txt')
    raises(InvalidOperation, '/', fs.rm, '/', recursive=True)


def test_rm_protects_cwd_and_ancestors(fs):
    fs.cd('/docs/notes')
    raises(InvalidOperation, '/docs/notes', fs.rm, '.', recursive=True)
    raises(InvalidOperation, '/docs', fs.rm, '/docs')
    fs.rm('/src', recursive=True)
    assert not fs.exists('/src')


def test_mv_rename_and_into_directory(fs):
    fs.mv('/docs/a.txt', '/docs/c.txt')
    assert fs.ls('/docs') == ['c.txt', 'notes/']
    fs.mv('/docs/c.txt', '/src')
    assert fs.read('/src/c.txt') == 'alpha\n'
    fs.mv('/docs/notes', '/archive')
    assert fs.read('/archive/b.txt') == 'beta\n' and not fs.exists('/docs/notes')


def test_mv_errors(fs):
    raises(NotFound, '/ghost', fs.mv, '/ghost', '/x')
    raises(InvalidOperation, '/docs', fs.mv, '/docs', '/docs/notes')
    raises(InvalidOperation, '/docs', fs.mv, '/docs', '/docs/notes/deeper')
    raises(InvalidOperation, '/', fs.mv, '/', '/x')
    fs.write('/src/a.txt', 'clash')
    raises(AlreadyExists, '/src/a.txt', fs.mv, '/docs/a.txt', '/src')
    raises(AlreadyExists, '/src/main.py', fs.mv, '/docs/a.txt', '/src/main.py')
    raises(NotFound, '/nowhere/a.txt', fs.mv, '/docs/a.txt', '/nowhere/a.txt')
    assert fs.read('/docs/a.txt') == 'alpha\n'
    fs.cd('/docs')
    raises(InvalidOperation, '/docs', fs.mv, '/docs', '/moved')


def test_find(fs):
    fs.write('/docs/notes/c.md', '')
    assert fs.find('/', '*.txt') == ['/docs/a.txt', '/docs/notes/b.txt']
    assert fs.find('/docs') == ['/docs/a.txt', '/docs/notes', '/docs/notes/b.txt',
                                '/docs/notes/c.md']
    assert fs.find('/docs/a.txt', 'a.*') == ['/docs/a.txt']
    assert fs.find('/docs/a.txt', 'b*') == []
    assert fs.find('/', 'NOTES') == []
    raises(NotFound, '/zz', fs.find, '/zz')


def test_find_sorted_as_strings():
    f = FileSystem()
    f.mkdir('/a/b', parents=True)
    f.mkdir('/a-b')
    assert f.find('/') == ['/a', '/a-b', '/a/b']


# ---------------------------------------------------------------- shell

SCRIPT = """\
# set up a project
mkdir -p /proj/src
cd /proj
write README.md Hello   "big world"
append README.md second line
cat README.md
write src/app.py print
ls
find . -name '*.py'
pwd
"""


def test_shell_script_output():
    out, status = Shell().run(SCRIPT)
    assert status == 0
    assert out == ('Hello big world\nsecond line\n'
                   'README.md\nsrc/\n'
                   '/proj/src/app.py\n'
                   '/proj\n')


def test_shell_stops_at_first_fs_error():
    sh = Shell()
    out, status = sh.run('mkdir /a\npwd\n\ncd /a/b\npwd\n')
    assert status == 1
    assert out == '/\nline 4: cd: NotFound: /a/b\n'
    assert sh.fs.pwd() == '/'


def test_shell_state_persists_between_runs():
    sh = Shell()
    sh.run('mkdir /keep\ncd /keep')
    out, status = sh.run('pwd\nwrite f.txt x\nls /keep')
    assert (out, status) == ('/keep\nf.txt\n', 0)


@pytest.mark.parametrize('line, message', [
    ('frobnicate x', 'line 2: frobnicate: unknown command\n'),
    ('cd', 'line 2: cd: usage\n'),
    ('mv onlyone', 'line 2: mv: usage\n'),
    ('rm -f x', 'line 2: rm: usage\n'),
    ('mkdir x -p', 'line 2: mkdir: usage\n'),
    ('write "unclosed', 'line 2: write: usage\n'),
])
def test_shell_usage_errors(line, message):
    out, status = Shell().run('pwd\n' + line + '\npwd\n')
    assert status == 2
    assert out == '/\n' + message


def test_shell_multi_path_left_to_right_and_rm_flag():
    out, status = Shell().run('mkdir /a /b /a\nls /')
    assert status == 1 and out == 'line 1: mkdir: AlreadyExists: /a\n'
    sh = Shell()
    out, status = sh.run('mkdir -p /t/u\nwrite /t/u/f x\nrm /t\n')
    assert status == 1 and out == 'line 3: rm: IsADirectory: /t\n'
    out, status = sh.run('rm -r /t\nls /\nfind -name "*"\n')
    assert (out, status) == ('', 0)


def test_shell_cli(tmp_path):
    script = tmp_path / 's.txt'
    script.write_text('mkdir /d\nwrite /d/x hi there\ncat /d/x\ncat /d/y\n')
    r = subprocess.run([sys.executable, '-m', 'vfs.shell', str(script)], cwd=HERE,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 1
    assert r.stdout == 'hi there\nline 4: cat: NotFound: /d/y\n'
    r = subprocess.run([sys.executable, '-m', 'vfs.shell', str(tmp_path / 'none.txt')],
                       cwd=HERE, capture_output=True, text=True, timeout=30)
    # `python -m vfs.shell` may also print runpy's RuntimeWarning (vfs/__init__ imports it).
    assert r.returncode == 2
    assert any(line.startswith('error:') for line in r.stderr.splitlines())
