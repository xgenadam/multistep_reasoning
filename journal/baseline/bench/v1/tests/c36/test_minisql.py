import copy

import pytest

from minisql import (And, Column, Compare, IsNull, Literal, Not, Or, SQLError,
                     SQLExecutionError, SQLSyntaxError, Token, parse, query, tokenize)

PEOPLE = [
    {'id': 1, 'name': 'Ann', 'age': 34, 'city': 'Oslo', 'active': True},
    {'id': 2, 'name': 'bob', 'age': 27, 'city': 'Lima', 'active': False},
    {'id': 3, 'name': 'Cid', 'age': None, 'city': 'Oslo', 'active': True},
    {'id': 4, 'name': 'Dee', 'age': 27, 'active': True},
    {'id': 5, 'name': 'Eve', 'age': 41, 'city': 'Kyiv', 'active': False},
]
DB = {'people': PEOPLE, 'empty': []}


def ids(rows):
    return [r['id'] for r in rows]


# ---------------------------------------------------------------- tokens

def test_tokenize_kinds_values_and_positions():
    toks = tokenize("select Name, x_1 FROM t where a<>'it''s' and b >= -4.5")
    assert toks == [
        Token('KEYWORD', 'SELECT', 0), Token('IDENT', 'Name', 7), Token('COMMA', ',', 11),
        Token('IDENT', 'x_1', 13), Token('KEYWORD', 'FROM', 17), Token('IDENT', 't', 22),
        Token('KEYWORD', 'WHERE', 24), Token('IDENT', 'a', 30), Token('OP', '!=', 31),
        Token('STRING', "it's", 33), Token('KEYWORD', 'AND', 41), Token('IDENT', 'b', 45),
        Token('OP', '>=', 47), Token('NUMBER', -4.5, 50), Token('EOF', None, 54),
    ]


def test_tokenize_number_types_and_symbols():
    toks = tokenize('12 3.25 * ( ) <= < > = !=')
    assert [(t.kind, t.value) for t in toks] == [
        ('NUMBER', 12), ('NUMBER', 3.25), ('STAR', '*'), ('LPAREN', '('), ('RPAREN', ')'),
        ('OP', '<='), ('OP', '<'), ('OP', '>'), ('OP', '='), ('OP', '!='), ('EOF', None)]
    assert type(toks[0].value) is int and type(toks[1].value) is float


@pytest.mark.parametrize('sql, pos', [
    ("SELECT * FROM t WHERE a = 'oops", 26),
    ('SELECT a; FROM t', 8),
    ('SELECT * FROM t WHERE a = 1.', 27),
])
def test_tokenize_errors_carry_position(sql, pos):
    with pytest.raises(SQLSyntaxError) as info:
        tokenize(sql)
    assert info.value.pos == pos
    assert isinstance(info.value, SQLError)


# ---------------------------------------------------------------- parser

def test_parse_clauses():
    stmt = parse('SELECT a, b FROM t ORDER BY a DESC, b LIMIT 3')
    assert stmt.columns == ['a', 'b']
    assert stmt.table == 't'
    assert stmt.where is None
    assert stmt.order_by == [('a', True), ('b', False)]
    assert stmt.limit == 3
    star = parse('select * from t')
    assert star.columns is None and star.order_by == [] and star.limit is None


def test_parse_precedence_and_associativity():
    where = parse('SELECT * FROM t WHERE a = 1 OR b = 2 AND NOT c = 3 OR d IS NOT NULL').where
    assert where == Or(
        Or(Compare('=', Column('a'), Literal(1)),
           And(Compare('=', Column('b'), Literal(2)), Not(Compare('=', Column('c'), Literal(3))))),
        IsNull(Column('d'), True))


def test_parse_parentheses_and_literals():
    where = parse("SELECT * FROM t WHERE (a = 'x' OR b <> NULL) AND c = TRUE").where
    assert where == And(Or(Compare('=', Column('a'), Literal('x')),
                           Compare('!=', Column('b'), Literal(None))),
                        Compare('=', Column('c'), Literal(True)))


@pytest.mark.parametrize('sql, pos', [
    ('SELECT FROM t', 7),
    ('SELECT a FROM t WHERE a', 23),
    ('SELECT a FROM t LIMIT 2 WHERE a = 1', 24),
    ('SELECT a FROM t LIMIT -1', 22),
    ('SELECT a FROM t LIMIT 1.5', 22),
    ('SELECT a, a FROM t', 10),
    ('SELECT a FROM t WHERE (a = 1', 28),
    ('SELECT a FROM t ORDER a', 22),
])
def test_parse_errors(sql, pos):
    with pytest.raises(SQLSyntaxError) as info:
        parse(sql)
    assert info.value.pos == pos


# ---------------------------------------------------------------- execution

def test_select_star_copies_rows():
    rows = query('SELECT * FROM people', DB)
    assert rows == PEOPLE
    assert all(a is not b for a, b in zip(rows, PEOPLE))
    assert list(rows[3]) == ['id', 'name', 'age', 'active']


def test_projection_order_and_missing_columns():
    rows = query('SELECT city, id, nope FROM people WHERE id >= 3', DB)
    assert rows == [{'city': 'Oslo', 'id': 3, 'nope': None},
                    {'city': None, 'id': 4, 'nope': None},
                    {'city': 'Kyiv', 'id': 5, 'nope': None}]
    assert list(rows[0]) == ['city', 'id', 'nope']


def test_unknown_table_raises():
    with pytest.raises(SQLExecutionError):
        query('SELECT * FROM nobody', DB)


def test_keywords_case_insensitive_names_case_sensitive():
    assert ids(query("select id from people where name = 'bob'", DB)) == [2]
    assert query("SELECT id FROM people WHERE name = 'Bob'", DB) == []
    with pytest.raises(SQLExecutionError):
        query('SELECT * FROM People', DB)


@pytest.mark.parametrize('where, expected', [
    ('age > 30', [1, 5]),
    ('age <= 27', [2, 4]),
    ('age != 27', [1, 5]),
    ('age = 27 OR age = 41', [2, 4, 5]),
    ('city = \'Oslo\' AND active = TRUE', [1, 3]),
    ('NOT active = TRUE', [2, 5]),
    ('age IS NULL', [3]),
    ('city IS NOT NULL AND age IS NOT NULL', [1, 2, 5]),
    ("name < 'C'", [1]),
])
def test_where_filters(where, expected):
    assert ids(query(f'SELECT id FROM people WHERE {where}', DB)) == expected


def test_null_comparisons_are_unknown_even_under_not():
    assert ids(query('SELECT id FROM people WHERE NOT age > 30', DB)) == [2, 4]
    assert query('SELECT id FROM people WHERE age = NULL', DB) == []
    assert query('SELECT id FROM people WHERE NOT age != NULL', DB) == []


def test_three_valued_and_or():
    # Row 3 has age NULL: unknown OR true is true; unknown AND false is false, so NOT (...) is true.
    assert ids(query('SELECT id FROM people WHERE age > 30 OR id = 3', DB)) == [1, 3, 5]
    assert ids(query('SELECT id FROM people WHERE NOT (age > 30 AND id = 1)', DB)) == [2, 3, 4, 5]
    assert ids(query('SELECT id FROM people WHERE NOT (age > 30 OR id = 4)', DB)) == [2]
    # unknown AND true is unknown, so NOT (...) drops row 3.
    assert ids(query('SELECT id FROM people WHERE NOT (age > 30 AND id = 3)', DB)) == [1, 2, 4, 5]


def test_mixed_kind_equality_and_ordering():
    assert query("SELECT id FROM people WHERE age = '27'", DB) == []
    assert ids(query("SELECT id FROM people WHERE age != '27'", DB)) == [1, 2, 4, 5]
    assert query('SELECT id FROM people WHERE active = 1', DB) == []
    with pytest.raises(SQLExecutionError):
        query("SELECT id FROM people WHERE age < 'x'", DB)


def test_int_and_float_are_one_kind():
    rows = [{'v': 2}, {'v': 2.0}, {'v': 2.5}]
    assert query('SELECT v FROM t WHERE v = 2.0', {'t': rows}) == [{'v': 2}, {'v': 2.0}]
    assert query('SELECT v FROM t WHERE v > 2', {'t': rows}) == [{'v': 2.5}]


def test_order_by_nulls_first_ascending_last_descending():
    assert ids(query('SELECT id FROM people ORDER BY age', DB)) == [3, 2, 4, 1, 5]
    assert ids(query('SELECT id FROM people ORDER BY age DESC', DB)) == [5, 1, 2, 4, 3]


def test_order_by_is_stable_and_multi_key():
    assert ids(query('SELECT id FROM people ORDER BY active, age DESC', DB)) == [5, 2, 1, 4, 3]
    assert ids(query('SELECT id FROM people ORDER BY city DESC, id DESC', DB)) == [3, 1, 2, 5, 4]


def test_order_by_column_not_selected_then_limit():
    assert query('SELECT name FROM people WHERE age IS NOT NULL ORDER BY age DESC LIMIT 2',
                 DB) == [{'name': 'Eve'}, {'name': 'Ann'}]
    assert query('SELECT name FROM people LIMIT 0', DB) == []
    assert len(query('SELECT * FROM people LIMIT 50', DB)) == 5


def test_order_by_mixed_kinds_raises():
    t = {'t': [{'v': 1}, {'v': 'a'}, {'v': None}]}
    with pytest.raises(SQLExecutionError):
        query('SELECT * FROM t ORDER BY v', t)
    # Only the kept rows matter.
    assert query("SELECT * FROM t WHERE v != 'a' ORDER BY v", t) == [{'v': 1}]


def test_empty_table_and_inputs_untouched():
    assert query('SELECT a FROM empty WHERE a = 1 ORDER BY a', DB) == []
    before = copy.deepcopy(DB)
    rows = query('SELECT * FROM people ORDER BY age DESC', DB)
    rows[0]['age'] = 0
    assert DB == before
