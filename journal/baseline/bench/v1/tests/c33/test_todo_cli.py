import json
import subprocess
import sys
from pathlib import Path

import pytest

from todo.cli import main

HERE = Path(__file__).resolve().parent


def run(*args, cwd=HERE):
    p = subprocess.run([sys.executable, '-m', 'todo.cli', *args], cwd=cwd,
                       capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout, p.stderr


def cli(capsys, *args):
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / 'todo.json')


def test_add_and_list_lines(capsys, db):
    assert cli(capsys, '--file', db, 'add', 'Buy milk', '--tag', 'Shop', '--tag', 'home') == \
        (0, 'added 1\n', '')
    cli(capsys, '--file', db, 'add', 'Call Bob')
    cli(capsys, '--file', db, 'done', '1')
    code, out, err = cli(capsys, '--file', db, 'list', '--status', 'all')
    assert code == 0
    assert out == '1 [x] Buy milk #home #shop\n2 [ ] Call Bob\n'


def test_list_defaults_to_open_and_filters_by_all_tags(capsys, db):
    cli(capsys, '--file', db, 'add', 'a', '--tag', 'x', '--tag', 'y')
    cli(capsys, '--file', db, 'add', 'b', '--tag', 'x')
    cli(capsys, '--file', db, 'add', 'c', '--tag', 'y')
    cli(capsys, '--file', db, 'done', '3')
    assert cli(capsys, '--file', db, 'list')[1] == '1 [ ] a #x #y\n2 [ ] b #x\n'
    assert cli(capsys, '--file', db, 'list', '--tag', 'x', '--tag', 'Y')[1] == '1 [ ] a #x #y\n'
    assert cli(capsys, '--file', db, 'list', '--status', 'done')[1] == '3 [x] c #y\n'


def test_empty_list_prints_nothing(capsys, db):
    assert cli(capsys, '--file', db, 'list') == (0, '', '')
    assert not Path(db).exists()


def test_done_several_in_given_order(capsys, db):
    for t in 'abc':
        cli(capsys, '--file', db, 'add', t)
    assert cli(capsys, '--file', db, 'done', '3', '1') == (0, 'done 3\ndone 1\n', '')
    assert cli(capsys, '--file', db, 'done', '3') == (0, 'done 3\n', '')


def test_done_with_a_missing_id_marks_nothing(capsys, db):
    cli(capsys, '--file', db, 'add', 'a')
    cli(capsys, '--file', db, 'add', 'b')
    code, out, err = cli(capsys, '--file', db, 'done', '1', '7', '8')
    assert (code, out) == (1, '')
    assert err.strip() == 'error: no task with id 7'
    assert cli(capsys, '--file', db, 'list')[1] == '1 [ ] a\n2 [ ] b\n'


def test_remove_and_missing_remove(capsys, db):
    cli(capsys, '--file', db, 'add', 'a')
    assert cli(capsys, '--file', db, 'remove', '1') == (0, 'removed 1\n', '')
    code, out, err = cli(capsys, '--file', db, 'remove', '1')
    assert (code, out, err.strip()) == (1, '', 'error: no task with id 1')
    assert cli(capsys, '--file', db, 'add', 'b')[1] == 'added 2\n'


def test_edit_title_and_tags(capsys, db):
    cli(capsys, '--file', db, 'add', 'a', '--tag', 'old')
    assert cli(capsys, '--file', db, 'edit', '1', '--title', 'Renamed', '--tag', 'new',
               '--untag', 'old') == (0, 'edited 1\n', '')
    assert cli(capsys, '--file', db, 'list')[1] == '1 [ ] Renamed #new\n'


def test_edit_errors(capsys, db):
    cli(capsys, '--file', db, 'add', 'a')
    code, out, err = cli(capsys, '--file', db, 'edit', '1')
    assert (code, out) == (2, '') and err.startswith('error: ')
    code, out, err = cli(capsys, '--file', db, 'edit', '5', '--title', 'x')
    assert (code, out, err.strip()) == (1, '', 'error: no task with id 5')


@pytest.mark.parametrize('args', [['add', '   '], ['add', 'x', '--tag', 'bad tag'],
                                  ['edit', '1', '--tag', 'Bad!']])
def test_invalid_title_or_tag_is_usage_error(capsys, db, args):
    cli(capsys, '--file', db, 'add', 'a')
    code, out, err = cli(capsys, '--file', db, *args)
    assert (code, out) == (2, '')
    assert err.startswith('error: ')
    assert json.loads(Path(db).read_text())['next_id'] == 2


def test_invalid_store_exit_3(capsys, db):
    Path(db).write_text('{"version": 1, "tasks": "nope"}')
    code, out, err = cli(capsys, '--file', db, 'list')
    assert (code, out) == (3, '')
    assert err.startswith('error: ')


def test_python_m_runs_with_file_option(tmp_path):
    db = str(tmp_path / 'x.json')
    assert run('--file', db, 'add', 'Hello world') == (0, 'added 1\n', '')
    assert run('--file', db, 'list') == (0, '1 [ ] Hello world\n', '')
    code, out, err = run('--file', db, 'done', '4')
    assert (code, out, err.strip()) == (1, '', 'error: no task with id 4')


def test_python_m_default_file_in_cwd(tmp_path):
    work = tmp_path / 'w'
    work.mkdir()
    (work / 'todo').symlink_to(HERE / 'todo', target_is_directory=True)
    assert run('add', 'Hi', cwd=work)[0] == 0
    assert json.loads((work / 'todo.json').read_text())['tasks'][0]['title'] == 'Hi'


def test_argparse_usage_errors_exit_2(db):
    assert run('--file', db, 'frobnicate')[0] == 2
    assert run('--file', db, 'done', 'abc')[0] == 2
    assert run('--file', db, 'list', '--status', 'closed')[0] == 2
