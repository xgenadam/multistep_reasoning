import hashlib

import pytest

from objstore import (AmbiguousPrefix, Blob, Change, Commit, CorruptObject, ObjectNotFound,
                      ObjectStore, Tree, TreeEntry, diff_commits, diff_trees, format_changes,
                      object_id, parse_object, serialize)

A = 'a' * 40
B = 'b' * 40


# ---------------------------------------------------------------- objects

def test_blob_matches_git():
    assert serialize(Blob(b'hello\n')) == b'blob 6\x00hello\n'
    assert object_id(Blob(b'hello\n')) == 'ce013625030ba8dba906f756967f9e9ca394464a'
    assert object_id(Blob(b'')) == 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'


def test_tree_serialisation_sorted():
    t = Tree([TreeEntry('zeta', 'blob', A), TreeEntry('Alpha', 'tree', B),
              TreeEntry('beta', 'blob', B)])
    assert [e.name for e in t.entries] == ['Alpha', 'beta', 'zeta']
    body = f'tree {B}\tAlpha\nblob {B}\tbeta\nblob {A}\tzeta\n'.encode()
    assert serialize(t) == b'tree %d\x00' % len(body) + body
    assert t == Tree(reversed(t.entries))
    assert serialize(Tree([])) == b'tree 0\x00'


def test_utf8_length_in_header():
    t = Tree([TreeEntry('café', 'blob', A)])
    body = f'blob {A}\tcafé\n'.encode('utf-8')
    assert serialize(t).startswith(b'tree %d\x00' % len(body))
    c = Commit(A, (), 'Zoë', 5, 'naïve ✓')
    raw = serialize(c)
    assert raw.split(b'\x00', 1)[0] == b'commit %d' % len(raw.split(b'\x00', 1)[1])


def test_commit_serialisation():
    c = Commit(A, [B, A], 'Ada <ada@example.com>', 1700000000, 'Fix it\n\nDetails.\n')
    assert c.parents == (B, A)
    body = (f'tree {A}\nparent {B}\nparent {A}\nauthor Ada <ada@example.com>\n'
            f'time 1700000000\n\nFix it\n\nDetails.\n').encode()
    assert serialize(c) == b'commit %d\x00' % len(body) + body
    assert object_id(c) == hashlib.sha1(serialize(c)).hexdigest()


@pytest.mark.parametrize('make', [
    lambda: Tree([TreeEntry('a/b', 'blob', A)]),
    lambda: Tree([TreeEntry('..', 'blob', A)]),
    lambda: Tree([TreeEntry('', 'blob', A)]),
    lambda: Tree([TreeEntry('x\ty', 'blob', A)]),
    lambda: Tree([TreeEntry('x', 'link', A)]),
    lambda: Tree([TreeEntry('x', 'blob', 'A' * 40)]),
    lambda: Tree([TreeEntry('x', 'blob', A), TreeEntry('x', 'tree', B)]),
    lambda: Commit('abc', (), 'me', 1, 'm'),
    lambda: Commit(A, (), 'me\nyou', 1, 'm'),
    lambda: Commit(A, (), 'me', -1, 'm'),
])
def test_object_validation(make):
    with pytest.raises(ValueError):
        make()


def test_parse_round_trip():
    objs = [Blob(b'\x00\xffbinary'), Tree([TreeEntry('d', 'tree', A), TreeEntry('f', 'blob', B)]),
            Tree([]), Commit(A, (B,), 'me', 0, ''), Commit(A, (), 'x y', 42, 'line\n\nmore')]
    for obj in objs:
        assert parse_object(serialize(obj)) == obj


@pytest.mark.parametrize('raw', [
    b'blob 5\x00abc',
    b'blob5\x00abc',
    b'blob 3abc',
    b'thing 3\x00abc',
    b'tree 6\x00junk\n\n',
    b'commit 4\x00none',
])
def test_parse_corrupt(raw):
    with pytest.raises(CorruptObject) as exc:
        parse_object(raw)
    assert isinstance(exc.value, ValueError)


# ---------------------------------------------------------------- store

def test_put_get_contains_raw():
    s = ObjectStore()
    oid = s.put(Blob(b'x'))
    assert oid == object_id(Blob(b'x')) and oid in s
    assert s.put(Blob(b'x')) == oid
    assert s.get(oid) == Blob(b'x') and s.get_raw(oid) == serialize(Blob(b'x'))
    with pytest.raises(ObjectNotFound) as exc:
        s.get('0' * 40)
    assert isinstance(exc.value, KeyError)
    assert s.put_raw(b'blob 1\x00y') == object_id(Blob(b'y'))
    with pytest.raises(CorruptObject):
        s.put_raw(b'blob 9\x00y')


def test_resolve_prefix():
    s = ObjectStore()
    oids = [s.put(Blob(str(i).encode())) for i in range(1500)]
    target = oids[0]
    n = next(k for k in range(4, 41) if sum(o.startswith(target[:k]) for o in oids) == 1)
    assert s.resolve(target[:n]) == target
    assert s.resolve(target) == target
    pairs = {}
    for o in oids:
        pairs.setdefault(o[:4], []).append(o)
    dup = next(p for p, v in pairs.items() if len(v) > 1)
    with pytest.raises(AmbiguousPrefix):
        s.resolve(dup)
    missing = next(f'{i:04x}' for i in range(65536) if f'{i:04x}' not in pairs)
    with pytest.raises(ObjectNotFound):
        s.resolve(missing)
    for bad in ['abc', target[:6].upper(), 'zzzz', target + '0']:
        with pytest.raises(ValueError):
            s.resolve(bad)


def test_write_and_read_tree():
    s = ObjectStore()
    files = {'README': b'hi\n', 'src/app.py': b'print(1)\n', 'src/lib/util.py': b'',
             'docs/a.md': b'# A\n'}
    root = s.write_tree(files)
    tree = s.get(root)
    assert [(e.name, e.kind) for e in tree.entries] == [('README', 'blob'), ('docs', 'tree'),
                                                         ('src', 'tree')]
    assert s.get(tree.entries[0].oid) == Blob(b'hi\n')
    assert s.read_tree(root) == dict(sorted(files.items()))
    assert list(s.read_tree(root)) == sorted(files)
    assert s.write_tree(dict(reversed(list(files.items())))) == root
    assert s.write_tree({}) == object_id(Tree([]))


@pytest.mark.parametrize('files', [
    {'a': b'1', 'a/b': b'2'}, {'a/b': b'2', 'a': b'1'}, {'/a': b''}, {'a/': b''},
    {'a//b': b''}, {'a/../b': b''},
])
def test_write_tree_errors(files):
    with pytest.raises(ValueError):
        ObjectStore().write_tree(files)


def test_commit_checks_references():
    s = ObjectStore()
    tree = s.write_tree({'f': b'1'})
    blob = s.put(Blob(b'1'))
    c1 = s.commit(tree, author='me', timestamp=1, message='one')
    assert s.get(c1) == Commit(tree, (), 'me', 1, 'one')
    with pytest.raises(ObjectNotFound):
        s.commit('0' * 40, author='me', timestamp=2, message='x')
    with pytest.raises(ObjectNotFound):
        s.commit(tree, ['0' * 40], author='me', timestamp=2, message='x')
    with pytest.raises(ValueError):
        s.commit(blob, author='me', timestamp=2, message='x')
    with pytest.raises(ValueError):
        s.commit(tree, [tree], author='me', timestamp=2, message='x')


@pytest.fixture
def history():
    s = ObjectStore()
    t = s.write_tree({'f': b'0'})
    root = s.commit(t, author='a', timestamp=10, message='root')
    left = s.commit(t, [root], author='a', timestamp=30, message='left')
    right = s.commit(t, [root], author='b', timestamp=20, message='right')
    right2 = s.commit(t, [right], author='b', timestamp=30, message='right2')
    merge = s.commit(t, [left, right2], author='a', timestamp=40, message='merge')
    return s, dict(root=root, left=left, right=right, right2=right2, merge=merge)


def test_log_all_ancestors_once_by_time_then_oid(history):
    s, c = history
    tied = sorted([c['left'], c['right2']])
    assert s.log(c['merge']) == [c['merge'], *tied, c['right'], c['root']]
    assert s.log(c['root']) == [c['root']]


def test_log_first_parent(history):
    s, c = history
    assert s.log(c['merge'], first_parent=True) == [c['merge'], c['left'], c['root']]
    assert s.log(c['right2'], first_parent=True) == [c['right2'], c['right'], c['root']]


# ---------------------------------------------------------------- diff

@pytest.fixture
def two_trees():
    s = ObjectStore()
    old = s.write_tree({'keep.txt': b'same', 'edit.txt': b'v1', 'gone.txt': b'bye',
                        'lib/a.py': b'a', 'lib/b.py': b'b', 'swap': b'file',
                        'big/x': b'x', 'big/y': b'y'})
    new = s.write_tree({'keep.txt': b'same', 'edit.txt': b'v2', 'new.txt': b'hi',
                        'lib/a.py': b'a', 'lib/b.py': b'B', 'lib/c.py': b'c',
                        'swap/inner': b'now a dir', 'big/x': b'x', 'big/y': b'y'})
    return s, old, new


def test_diff_trees(two_trees):
    s, old, new = two_trees
    blob = lambda data: object_id(Blob(data))
    assert diff_trees(s, old, new) == [
        Change('M', 'edit.txt', blob(b'v1'), blob(b'v2')),
        Change('D', 'gone.txt', blob(b'bye'), None),
        Change('M', 'lib/b.py', blob(b'b'), blob(b'B')),
        Change('A', 'lib/c.py', None, blob(b'c')),
        Change('A', 'new.txt', None, blob(b'hi')),
        Change('D', 'swap', blob(b'file'), None),
        Change('A', 'swap/inner', None, blob(b'now a dir')),
    ]


def test_diff_reverse_and_identical(two_trees):
    s, old, new = two_trees
    back = diff_trees(s, new, old)
    assert [(c.status, c.path) for c in back] == [
        ('M', 'edit.txt'), ('A', 'gone.txt'), ('M', 'lib/b.py'), ('D', 'lib/c.py'),
        ('D', 'new.txt'), ('A', 'swap'), ('D', 'swap/inner')]
    assert diff_trees(s, old, old) == []


def test_diff_skips_unchanged_subtrees(two_trees):
    s, old, new = two_trees
    big = next(e.oid for e in s.get(old).entries if e.name == 'big')
    read = []
    real_get, real_raw = s.get, s.get_raw
    s.get = lambda oid: (read.append(oid), real_get(oid))[1]
    s.get_raw = lambda oid: (read.append(oid), real_raw(oid))[1]
    diff_trees(s, old, new)
    assert big not in read


def test_diff_with_empty_side_and_commits(two_trees):
    s, old, new = two_trees
    added = diff_trees(s, None, old)
    assert [c.path for c in added] == ['big/x', 'big/y', 'edit.txt', 'gone.txt', 'keep.txt',
                                       'lib/a.py', 'lib/b.py', 'swap']
    assert all(c.status == 'A' and c.old is None for c in added)
    c1 = s.commit(old, author='me', timestamp=1, message='1')
    c2 = s.commit(new, [c1], author='me', timestamp=2, message='2')
    assert diff_commits(s, c1, c2) == diff_trees(s, old, new)
    assert diff_commits(s, None, c1) == added


def test_format_changes(two_trees):
    s, old, new = two_trees
    text = format_changes(diff_trees(s, old, new))
    assert text.splitlines()[:2] == ['M\tedit.txt', 'D\tgone.txt']
    assert text.endswith('A\tswap/inner\n')
    assert format_changes([]) == ''
