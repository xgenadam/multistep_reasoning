import json

import pytest

from todo import StoreError, Task, TodoStore
from todo.model import normalize_tag, normalize_title


def test_normalize_title_and_tag():
    assert normalize_title('  Buy milk \n') == 'Buy milk'
    assert normalize_tag(' Work ') == 'work'
    assert normalize_tag('a_b-9') == 'a_b-9'


@pytest.mark.parametrize('tag', ['   ', '-x', 'a b'])
def test_invalid_tags_rejected(tag):
    with pytest.raises(ValueError):
        normalize_tag(tag)


def test_task_dict_round_trip_and_key_order():
    t = Task(4, 'Write report', ['work'], True)
    d = t.to_dict()
    # adapted for c33f: to_dict gained priority and due
    assert list(d) == ['id', 'title', 'tags', 'done', 'priority', 'due']
    assert Task.from_dict(d) == t
    assert Task.from_dict({'id': 2, 'title': ' x ', 'tags': ['B', 'a', 'b'],
                           'done': False}) == Task(2, 'x', ['a', 'b'], False)


@pytest.mark.parametrize('bad', [
    {'id': 1, 'title': 'x', 'tags': []},
    {'id': True, 'title': 'x', 'tags': [], 'done': False},
    {'id': 1, 'title': 'x', 'tags': 'work', 'done': False},
    {'id': 1, 'title': '  ', 'tags': [], 'done': False},
    {'id': 1, 'title': 'x', 'tags': [], 'done': 'no'},
])
def test_from_dict_rejects_bad_data(bad):
    with pytest.raises(ValueError):
        Task.from_dict(bad)


def test_missing_file_is_empty_and_not_created(tmp_path):
    path = tmp_path / 'todo.json'
    store = TodoStore(path)
    assert store.list('all') == []
    assert not path.exists()


def test_add_assigns_sequential_ids_and_normalizes(tmp_path):
    store = TodoStore(tmp_path / 't.json')
    a = store.add('  Buy milk ', ['Shop', 'home', 'shop'])
    b = store.add('Call Bob')
    assert (a.id, a.title, a.tags, a.done) == (1, 'Buy milk', ['home', 'shop'], False)
    assert b.id == 2


def test_file_format_written_on_add(tmp_path):
    path = tmp_path / 't.json'
    store = TodoStore(path)
    store.add('b', ['x'])
    store.add('a')
    data = json.loads(path.read_text())
    # adapted for c33f: files are written as version 2 with priority and due
    assert data == {'version': 2, 'next_id': 3, 'tasks': [
        {'id': 1, 'title': 'b', 'tags': ['x'], 'done': False, 'priority': 'normal', 'due': None},
        {'id': 2, 'title': 'a', 'tags': [], 'done': False, 'priority': 'normal', 'due': None}]}


def test_ids_never_reused_after_removing_highest(tmp_path):
    path = tmp_path / 't.json'
    store = TodoStore(path)
    store.add('a')
    store.add('b')
    store.remove(2)
    assert TodoStore(path).add('c').id == 3


def test_reload_sees_changes(tmp_path):
    path = tmp_path / 't.json'
    store = TodoStore(path)
    store.add('a', ['k'])
    store.add('b')
    store.mark_done(1)
    again = TodoStore(path)
    assert [(t.id, t.done) for t in again.list('all')] == [(1, True), (2, False)]


def test_list_status_and_tag_filters(tmp_path):
    store = TodoStore(tmp_path / 't.json')
    store.add('a', ['home', 'shop'])
    store.add('b', ['home'])
    store.add('c', ['shop'])
    store.mark_done(2)
    assert [t.id for t in store.list()] == [1, 3]
    assert [t.id for t in store.list('done')] == [2]
    assert [t.id for t in store.list('all', ['HOME'])] == [1, 2]
    assert [t.id for t in store.list('all', ['home', 'shop'])] == [1]
    with pytest.raises(ValueError):
        store.list('closed')


def test_missing_ids_raise_key_error(tmp_path):
    store = TodoStore(tmp_path / 't.json')
    store.add('a')
    for call in (lambda: store.get(9), lambda: store.mark_done(9),
                 lambda: store.remove(9), lambda: store.edit(9, title='x')):
        with pytest.raises(KeyError):
            call()


def test_edit_adds_then_removes_tags(tmp_path):
    store = TodoStore(tmp_path / 't.json')
    store.add('a', ['old', 'keep'])
    t = store.edit(1, title=' New ', add_tags=['Fresh', 'both'], remove_tags=['old', 'both', 'nope'])
    assert (t.title, t.tags) == ('New', ['fresh', 'keep'])
    assert TodoStore(store.path).get(1).tags == ['fresh', 'keep']


def test_invalid_edit_changes_nothing(tmp_path):
    store = TodoStore(tmp_path / 't.json')
    store.add('a', ['k'])
    with pytest.raises(ValueError):
        store.edit(1, title='renamed', add_tags=['bad tag'])
    assert store.get(1).title == 'a'
    assert TodoStore(store.path).get(1).title == 'a'


def test_returned_tasks_are_copies(tmp_path):
    store = TodoStore(tmp_path / 't.json')
    store.add('a', ['k'])
    t = store.get(1)
    t.title = 'hacked'
    t.tags.append('zzz')
    store.list('all')[0].done = True
    assert store.get(1) == Task(1, 'a', ['k'], False)


@pytest.mark.parametrize('content', [
    'not json',
    '[]',
    '{"version": 1, "next_id": 2}',
    '{"version": 1, "next_id": 2, "tasks": [{"id": 2, "title": "x", "tags": [], "done": false}]}',
    '{"version": 1, "next_id": 5, "tasks": [{"id": 1, "title": "x", "tags": [], "done": false},'
    ' {"id": 1, "title": "y", "tags": [], "done": false}]}',
])
def test_invalid_files_raise_store_error(tmp_path, content):
    path = tmp_path / 't.json'
    path.write_text(content)
    with pytest.raises(StoreError):
        TodoStore(path)
