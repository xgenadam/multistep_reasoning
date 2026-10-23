import json
from datetime import date
from pathlib import Path

import pytest

from todo import StoreError, Task, TodoStore
from todo.cli import main
from todo.model import normalize_priority, parse_date

TODAY = '2026-10-20'


def cli(capsys, db, *args, today=TODAY):
    code = main(['--file', db, '--today', today, *args])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / 'todo.json')


def test_task_defaults_and_dict():
    t = Task(1, 'x', [])
    assert (t.priority, t.due) == ('normal', None)
    d = Task(2, 'y', ['a'], False, 'high', date(2026, 11, 1)).to_dict()
    assert d == {'id': 2, 'title': 'y', 'tags': ['a'], 'done': False,
                 'priority': 'high', 'due': '2026-11-01'}
    assert Task.from_dict(d) == Task(2, 'y', ['a'], False, 'high', date(2026, 11, 1))


def test_normalize_priority():
    assert normalize_priority(' HIGH ') == 'high'
    with pytest.raises(ValueError):
        normalize_priority('urgent')


@pytest.mark.parametrize('s', ['2026-1-5', '20260105', '2026-02-30', '2026-01-05T00:00', ''])
def test_parse_date_strict(s):
    with pytest.raises(ValueError):
        parse_date(s)


def test_parse_date_ok():
    assert parse_date('2024-02-29') == date(2024, 2, 29)


def test_from_dict_rejects_bad_priority_or_due():
    base = {'id': 1, 'title': 'x', 'tags': [], 'done': False}
    with pytest.raises(ValueError):
        Task.from_dict({**base, 'priority': 'urgent'})
    with pytest.raises(ValueError):
        Task.from_dict({**base, 'due': '11/01/2026'})


def test_version_1_file_loads_with_defaults_and_is_not_rewritten(tmp_path):
    path = tmp_path / 'old.json'
    old = ('{"version": 1, "next_id": 3, "tasks": ['
           '{"id": 1, "title": "a", "tags": ["k"], "done": true},'
           ' {"id": 2, "title": "b", "tags": [], "done": false}]}')
    path.write_text(old)
    store = TodoStore(path)
    assert store.get(1) == Task(1, 'a', ['k'], True, 'normal', None)
    store.list('all', sort='priority')
    assert path.read_text() == old
    store.add('c', priority='low')
    data = json.loads(path.read_text())
    assert data['version'] == 2
    assert data['tasks'][0] == {'id': 1, 'title': 'a', 'tags': ['k'], 'done': True,
                                'priority': 'normal', 'due': None}


def test_unknown_version_rejected(tmp_path):
    path = tmp_path / 't.json'
    path.write_text('{"version": 3, "next_id": 1, "tasks": []}')
    with pytest.raises(StoreError):
        TodoStore(path)


def make(tmp_path):
    store = TodoStore(tmp_path / 's.json')
    store.add('a', priority='low', due=date(2026, 10, 25))
    store.add('b', priority='high')
    store.add('c', due=date(2026, 10, 19))
    store.add('d', priority='high', due=date(2026, 10, 19))
    store.add('e', due=date(2026, 10, 20))
    return store


def test_sort_priority_ties_by_id(tmp_path):
    store = make(tmp_path)
    assert [t.title for t in store.list(sort='priority')] == ['b', 'd', 'c', 'e', 'a']


def test_sort_due_none_last_ties_by_id(tmp_path):
    store = make(tmp_path)
    assert [t.title for t in store.list(sort='due')] == ['c', 'd', 'e', 'a', 'b']


def test_overdue_is_strictly_before_today_and_open_only(tmp_path):
    store = make(tmp_path)
    store.mark_done(4)
    today = date(2026, 10, 20)
    assert [t.title for t in store.list(overdue=True, today=today)] == ['c']
    assert [t.title for t in store.list('all', overdue=True, today=today)] == ['c']
    assert store.list('done', overdue=True, today=today) == []
    with pytest.raises(ValueError):
        store.list(overdue=True)
    with pytest.raises(ValueError):
        store.list(sort='title')


def test_store_edit_priority_and_due(tmp_path):
    store = make(tmp_path)
    t = store.edit(2, priority='LOW', due=date(2027, 1, 1))
    assert (t.priority, t.due) == ('low', date(2027, 1, 1))
    t = store.edit(2, clear_due=True)
    assert t.due is None
    with pytest.raises(ValueError):
        store.edit(1, due=date(2027, 1, 1), clear_due=True)
    with pytest.raises(ValueError):
        store.edit(1, title='renamed', priority='urgent')
    assert TodoStore(store.path).get(1) == Task(1, 'a', [], False, 'low', date(2026, 10, 25))


def test_cli_add_and_list_line_format(capsys, db):
    assert cli(capsys, db, 'add', 'Pay rent', '--priority', 'high', '--due', '2026-11-01',
               '--tag', 'home')[:2] == (0, 'added 1\n')
    cli(capsys, db, 'add', 'Plain')
    cli(capsys, db, 'add', 'Later', '--priority', 'low')
    assert cli(capsys, db, 'list')[1] == (
        '1 [ ] Pay rent !high due:2026-11-01 #home\n2 [ ] Plain\n3 [ ] Later !low\n')


def test_cli_overdue_uses_today_option(capsys, db):
    cli(capsys, db, 'add', 'a', '--due', '2026-10-19')
    cli(capsys, db, 'add', 'b', '--due', '2026-10-20')
    cli(capsys, db, 'add', 'c')
    assert cli(capsys, db, 'list', '--overdue')[1] == '1 [ ] a due:2026-10-19\n'
    assert cli(capsys, db, 'list', '--overdue', today='2026-10-21')[1] == (
        '1 [ ] a due:2026-10-19\n2 [ ] b due:2026-10-20\n')


def test_cli_sort(capsys, db):
    cli(capsys, db, 'add', 'a', '--priority', 'low', '--due', '2026-12-01')
    cli(capsys, db, 'add', 'b')
    cli(capsys, db, 'add', 'c', '--priority', 'high', '--due', '2026-11-01')
    out = cli(capsys, db, 'list', '--sort', 'priority')[1]
    assert [line.split()[0] for line in out.splitlines()] == ['3', '2', '1']
    out = cli(capsys, db, 'list', '--sort', 'due')[1]
    assert [line.split()[0] for line in out.splitlines()] == ['3', '1', '2']


def test_cli_edit_priority_due_and_no_due(capsys, db):
    cli(capsys, db, 'add', 'a', '--due', '2026-12-01')
    assert cli(capsys, db, 'edit', '1', '--priority', 'high')[:2] == (0, 'edited 1\n')
    assert cli(capsys, db, 'list')[1] == '1 [ ] a !high due:2026-12-01\n'
    assert cli(capsys, db, 'edit', '1', '--no-due')[:2] == (0, 'edited 1\n')
    assert cli(capsys, db, 'list')[1] == '1 [ ] a !high\n'
    assert cli(capsys, db, 'edit', '1', '--due', '2027-01-02')[0] == 0
    assert cli(capsys, db, 'list')[1] == '1 [ ] a !high due:2027-01-02\n'


@pytest.mark.parametrize('args', [
    ['add', 'x', '--due', '2026-13-01'],
    ['add', 'x', '--due', '20261101'],
    ['edit', '1', '--due', '2026-12-01', '--no-due'],
    ['edit', '1', '--due', 'tomorrow'],
])
def test_cli_invalid_values_are_usage_errors(capsys, db, args):
    cli(capsys, db, 'add', 'a')
    before = Path(db).read_text()
    code, out, err = cli(capsys, db, *args)
    assert (code, out) == (2, '')
    assert Path(db).read_text() == before


def test_cli_invalid_priority_is_usage_error(capsys, db):
    cli(capsys, db, 'add', 'a')
    try:
        code = main(['--file', db, 'add', 'x', '--priority', 'urgent'])
    except SystemExit as e:
        code = e.code
    assert code == 2
    assert capsys.readouterr().out == ''
    assert json.loads(Path(db).read_text())['next_id'] == 2


def test_cli_invalid_today_is_usage_error(capsys, db):
    code, out, err = cli(capsys, db, 'list', today='2026-10-32')
    assert (code, out) == (2, '')
