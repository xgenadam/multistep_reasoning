"""Executor: filtering with three-valued logic, sorting, limiting, projection."""
from .parser import And, Column, Compare, IsNull, Literal, Not, Or, Select, parse
from .tokens import SQLError

UNKNOWN = None  # the third truth value


class SQLExecutionError(SQLError):
    """A problem found while running a parsed statement."""


def kind(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, (int, float)):
        return 'number'
    if isinstance(value, str):
        return 'string'
    return type(value).__name__


def compare(op: str, a, b):
    """True, False or UNKNOWN."""
    if a is None or b is None:
        return UNKNOWN
    ka, kb = kind(a), kind(b)
    if ka != kb:
        if op == '=':
            return False
        if op == '!=':
            return True
        raise SQLExecutionError(f'cannot compare {ka} with {kb} using {op}')
    if op == '=':
        return a == b
    if op == '!=':
        return a != b
    if op == '<':
        return a < b
    if op == '<=':
        return a <= b
    if op == '>':
        return a > b
    if op == '>=':
        return a >= b
    raise SQLExecutionError(f'unknown operator {op}')


def value_of(node, row: dict):
    if isinstance(node, Column):
        return row.get(node.name)
    if isinstance(node, Literal):
        return node.value
    raise SQLExecutionError(f'not an operand: {node!r}')


def truth(node, row: dict):
    if isinstance(node, Compare):
        return compare(node.op, value_of(node.left, row), value_of(node.right, row))
    if isinstance(node, IsNull):
        is_null = value_of(node.operand, row) is None
        return not is_null if node.negated else is_null
    if isinstance(node, Not):
        t = truth(node.operand, row)
        return UNKNOWN if t is UNKNOWN else not t
    if isinstance(node, And):
        a, b = truth(node.left, row), truth(node.right, row)
        return bool(a and b)
    if isinstance(node, Or):
        a, b = truth(node.left, row), truth(node.right, row)
        if a is True or b is True:
            return True
        if a is UNKNOWN or b is UNKNOWN:
            return UNKNOWN
        return False
    raise SQLExecutionError(f'not a condition: {node!r}')


def sort_rows(rows: list[dict], order_by: list) -> list[dict]:
    rows = list(rows)
    for name, descending in reversed(order_by):
        kinds = {kind(r.get(name)) for r in rows} - {None}
        if len(kinds) > 1:
            raise SQLExecutionError(f'column {name!r} mixes {sorted(kinds)}')
        present = [r for r in rows if r.get(name) is not None]
        nulls = [r for r in rows if r.get(name) is None]
        present.sort(key=lambda r: r.get(name), reverse=descending)
        rows = present + nulls if descending else nulls + present
    return rows


def execute(stmt: Select, tables: dict) -> list[dict]:
    if stmt.table not in tables:
        raise SQLExecutionError(f'unknown table {stmt.table!r}')
    rows = list(tables[stmt.table])
    if stmt.where is not None:
        rows = [r for r in rows if truth(stmt.where, r) is True]
    if stmt.order_by:
        rows = sort_rows(rows, stmt.order_by)
    if stmt.limit is not None:
        rows = rows[:stmt.limit]
    if stmt.columns is None:
        return [dict(r) for r in rows]
    return [{name: r.get(name) for name in stmt.columns} for r in rows]


def query(sql: str, tables: dict) -> list[dict]:
    return execute(parse(sql), tables)
