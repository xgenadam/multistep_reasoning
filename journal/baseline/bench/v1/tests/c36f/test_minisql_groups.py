import pytest

from minisql import (Aggregate, Column, Join, SQLExecutionError, SQLSyntaxError, parse, query,
                     tokenize)

CUSTOMERS = [
    {'id': 1, 'name': 'Ann', 'city': 'Oslo'},
    {'id': 2, 'name': 'Bo', 'city': 'Lima'},
    {'id': 3, 'name': 'Cy', 'city': 'Oslo'},
    {'id': 4, 'name': 'Di'},
]
ORDERS = [
    {'oid': 10, 'cid': 1, 'amount': 30, 'item': 'pen'},
    {'oid': 11, 'cid': 2, 'amount': 12.5, 'item': 'ink'},
    {'oid': 12, 'cid': 1, 'amount': 5, 'item': 'cap'},
    {'oid': 13, 'cid': None, 'amount': 7, 'item': 'pad'},
    {'oid': 14, 'cid': 3, 'amount': None, 'item': 'pen'},
    {'oid': 15, 'cid': 9, 'amount': 2, 'item': 'ink'},
    {'oid': 16, 'cid': '1', 'amount': 1, 'item': 'pen'},
]
DB = {'c': CUSTOMERS, 'o': ORDERS}


def pairs(rows):
    return [tuple(r.values()) for r in rows]


# ---------------------------------------------------------------- tokens and tree

def test_tokenize_dot_and_new_keywords():
    toks = tokenize('select p.id, count(*) as n from p join q on p.id = q.pid group by p.id')
    assert [(t.kind, t.value) for t in toks[:6]] == [
        ('KEYWORD', 'SELECT'), ('IDENT', 'p'), ('DOT', '.'), ('IDENT', 'id'), ('COMMA', ','),
        ('KEYWORD', 'COUNT')]
    kws = [t.value for t in toks if t.kind == 'KEYWORD']
    assert kws == ['SELECT', 'COUNT', 'AS', 'FROM', 'JOIN', 'ON', 'GROUP', 'BY']
    assert toks[2].pos == 8


def test_parse_items_group_and_order():
    stmt = parse('SELECT o . cid, SUM(o.amount) AS total, count( * ) FROM o '
                 'GROUP BY o.cid ORDER BY total DESC, COUNT(*)')
    assert stmt.columns == ['o.cid', 'total', 'COUNT(*)']
    assert stmt.items == [(Column('o.cid'), 'o.cid'),
                          (Aggregate('SUM', Column('o.amount')), 'total'),
                          (Aggregate('COUNT', None), 'COUNT(*)')]
    assert stmt.group_by == ['o.cid']
    assert stmt.order_by == [('total', True), ('COUNT(*)', False)]
    assert stmt.join is None


def test_parse_join():
    stmt = parse('SELECT * FROM c JOIN o ON o.cid = c.id WHERE c.id > 1')
    assert stmt.join == Join('o', Column('o.cid'), Column('c.id'))
    assert stmt.columns is None and stmt.items == [] and stmt.group_by == []
    assert stmt.table == 'c'


@pytest.mark.parametrize('sql, pos', [
    ('SELECT a, b AS a FROM t', 10),
    ('SELECT * FROM t GROUP BY a', 7),
    ('SELECT a, b, COUNT(*) FROM t GROUP BY a', 10),
    ('SELECT a, COUNT(*) FROM t', 7),
    ('SELECT a FROM t ORDER BY MAX(a)', 25),
    ('SELECT SUM(*) FROM t', 11),
    ('SELECT a FROM t WHERE COUNT(a) > 1', 22),
    ('SELECT a FROM t JOIN u ON t.a < u.a', 30),
    ('SELECT count FROM t', 13),
])
def test_new_syntax_errors(sql, pos):
    with pytest.raises(SQLSyntaxError) as info:
        parse(sql)
    assert info.value.pos == pos


# ---------------------------------------------------------------- names and joins

def test_qualified_names_on_one_table():
    rows = query("SELECT c.name, city FROM c WHERE c.city = 'Oslo'", DB)
    assert rows == [{'c.name': 'Ann', 'city': 'Oslo'}, {'c.name': 'Cy', 'city': 'Oslo'}]
    with pytest.raises(SQLExecutionError):
        query('SELECT o.name FROM c', DB)


def test_join_order_and_matching():
    expected = [('Ann', 10), ('Ann', 12), ('Bo', 11), ('Cy', 14)]
    assert pairs(query('SELECT c.name, o.oid FROM c JOIN o ON c.id = o.cid', DB)) == expected
    assert pairs(query('SELECT c.name, o.oid FROM c JOIN o ON o.cid = c.id', DB)) == expected
    assert pairs(query('SELECT o.oid, c.name FROM o JOIN c ON o.cid = c.id', DB)) == [
        (10, 'Ann'), (11, 'Bo'), (12, 'Ann'), (14, 'Cy')]


def test_join_star_keys():
    rows = query('SELECT * FROM c JOIN o ON c.id = o.cid LIMIT 1', DB)
    assert rows == [{'c.id': 1, 'c.name': 'Ann', 'c.city': 'Oslo', 'o.oid': 10, 'o.cid': 1,
                     'o.amount': 30, 'o.item': 'pen'}]
    assert list(rows[0]) == ['c.id', 'c.name', 'c.city', 'o.oid', 'o.cid', 'o.amount', 'o.item']
    di = query("SELECT * FROM o JOIN c ON o.cid = c.id WHERE c.name = 'Bo'", DB)
    assert list(di[0]) == ['o.oid', 'o.cid', 'o.amount', 'o.item', 'c.id', 'c.name', 'c.city']


def test_join_where_and_order():
    rows = query('SELECT c.name, o.amount FROM c JOIN o ON c.id = o.cid '
                 'WHERE o.amount IS NOT NULL ORDER BY o.amount DESC', DB)
    assert pairs(rows) == [('Ann', 30), ('Bo', 12.5), ('Ann', 5)]


@pytest.mark.parametrize('sql', [
    'SELECT name FROM c JOIN o ON c.id = o.cid',
    'SELECT x.name FROM c JOIN o ON c.id = o.cid',
    'SELECT c.name FROM c JOIN o ON c.id = o.cid WHERE amount > 1',
    'SELECT c.name FROM c JOIN o ON c.id = c.id',
    'SELECT c.name FROM c JOIN c ON c.id = c.id',
    'SELECT c.name FROM c JOIN zz ON c.id = zz.id',
])
def test_join_name_errors(sql):
    with pytest.raises(SQLExecutionError):
        query(sql, DB)


# ---------------------------------------------------------------- grouping and aggregates

def test_group_by_first_appearance_and_null_group():
    rows = query('SELECT cid, COUNT(*), SUM(amount) FROM o GROUP BY cid', DB)
    assert pairs(rows) == [(1, 2, 35), (2, 1, 12.5), (None, 1, 7), (3, 1, None), (9, 1, 2),
                           ('1', 1, 1)]
    assert list(rows[0]) == ['cid', 'COUNT(*)', 'SUM(amount)']
    assert type(rows[0]['SUM(amount)']) is int


def test_aggregates_over_whole_table():
    [row] = query('SELECT COUNT(*) AS n, COUNT(amount) AS k, AVG(amount) AS mean, '
                  'MIN(item), MAX(item) FROM o', DB)
    assert row['n'] == 7 and row['k'] == 6
    assert row['mean'] == pytest.approx(57.5 / 6)
    assert row['MIN(item)'] == 'cap' and row['MAX(item)'] == 'pen'


def test_aggregates_with_no_rows():
    assert query('SELECT COUNT(*), SUM(amount), AVG(amount), MAX(item) FROM o '
                 'WHERE amount > 100', DB) == [
        {'COUNT(*)': 0, 'SUM(amount)': None, 'AVG(amount)': None, 'MAX(item)': None}]
    assert query('SELECT item, COUNT(*) FROM o WHERE amount > 100 GROUP BY item', DB) == []


def test_sum_and_avg_types():
    t = {'t': [{'v': 2}, {'v': 4}], 'u': [{'v': 1}, {'v': 2.0}]}
    [row] = query('SELECT SUM(v), AVG(v) FROM t', t)
    assert type(row['SUM(v)']) is int and row['SUM(v)'] == 6
    assert type(row['AVG(v)']) is float and row['AVG(v)'] == 3.0
    [row] = query('SELECT SUM(v) FROM u', t)
    assert type(row['SUM(v)']) is float and row['SUM(v)'] == 3.0


@pytest.mark.parametrize('sql', [
    'SELECT SUM(item) FROM o',
    'SELECT AVG(flag) FROM t',
    'SELECT MIN(mixed) FROM t',
])
def test_aggregate_kind_errors(sql):
    t = {'o': ORDERS, 't': [{'flag': True, 'mixed': 1}, {'flag': None, 'mixed': 'a'}]}
    with pytest.raises(SQLExecutionError):
        query(sql, t)


def test_groups_follow_value_kinds():
    t = {'t': [{'k': 1}, {'k': 1.0}, {'k': True}, {'k': None}, {}]}
    assert query('SELECT k, COUNT(*) AS n FROM t GROUP BY k', t) == [
        {'k': 1, 'n': 2}, {'k': True, 'n': 1}, {'k': None, 'n': 2}]


def test_group_order_by_alias_and_canonical_text():
    by_alias = query('SELECT item, COUNT(*) AS n FROM o GROUP BY item ORDER BY n DESC, item', DB)
    assert pairs(by_alias) == [('pen', 3), ('ink', 2), ('cap', 1), ('pad', 1)]
    by_text = query('SELECT item, COUNT(*) AS n FROM o GROUP BY item ORDER BY COUNT(*) LIMIT 3',
                    DB)
    assert pairs(by_text) == [('cap', 1), ('pad', 1), ('ink', 2)]


@pytest.mark.parametrize('order', ['amount', 'SUM(amount)', 'oid DESC'])
def test_group_order_by_must_be_a_select_item(order):
    with pytest.raises(SQLExecutionError):
        query(f'SELECT item, COUNT(*) FROM o GROUP BY item ORDER BY {order}', DB)


def test_group_by_several_columns():
    rows = query('SELECT item, cid, COUNT(*) AS n FROM o WHERE amount IS NOT NULL '
                 'GROUP BY item, cid', DB)
    assert pairs(rows) == [('pen', 1, 1), ('ink', 2, 1), ('cap', 1, 1), ('pad', None, 1),
                           ('ink', 9, 1), ('pen', '1', 1)]


def test_join_then_group():
    rows = query('SELECT c.name, SUM(o.amount) AS spent, COUNT(o.oid) AS orders FROM c '
                 'JOIN o ON c.id = o.cid GROUP BY c.name ORDER BY spent DESC', DB)
    assert pairs(rows) == [('Ann', 35, 2), ('Bo', 12.5, 1), ('Cy', None, 1)]


def test_ungrouped_order_by_alias():
    assert query('SELECT name AS who FROM c ORDER BY who DESC', DB) == [
        {'who': 'Di'}, {'who': 'Cy'}, {'who': 'Bo'}, {'who': 'Ann'}]
    rows = query('SELECT o.amount AS amt, c.name FROM c JOIN o ON c.id = o.cid ORDER BY amt', DB)
    assert pairs(rows) == [(None, 'Cy'), (5, 'Ann'), (12.5, 'Bo'), (30, 'Ann')]
