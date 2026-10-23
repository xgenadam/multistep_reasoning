"""Executor: join, filtering with three-valued logic, grouping, sorting, limiting."""
from .parser import (Aggregate, And, Column, Compare, IsNull, Literal, Not, Or, Select,
                     canonical, parse)
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


class Scope:
    """Turns a reference's canonical text into a getter on the rows being queried."""

    def __init__(self, table: str, other: str | None):
        self.table, self.other = table, other

    def getter(self, ref: str):
        qualifier, dot, name = ref.rpartition('.')
        if self.other is None:
            if dot and qualifier != self.table:
                raise SQLExecutionError(f'unknown table {qualifier!r} in {ref!r}')
            return lambda row: row.get(name)
        if not dot:
            raise SQLExecutionError(f'{ref!r} must be qualified in a join')
        if qualifier not in (self.table, self.other):
            raise SQLExecutionError(f'unknown table {qualifier!r} in {ref!r}')
        return lambda row: row.get(ref)


def compile_condition(node, scope: Scope):
    """A function row -> True | False | UNKNOWN; every reference is checked up front."""
    if isinstance(node, Column):
        return scope.getter(node.name)
    if isinstance(node, Literal):
        value = node.value
        return lambda row: value
    if isinstance(node, Compare):
        left, right, op = compile_condition(node.left, scope), compile_condition(node.right, scope), node.op
        return lambda row: compare(op, left(row), right(row))
    if isinstance(node, IsNull):
        get, negated = compile_condition(node.operand, scope), node.negated
        return lambda row: (get(row) is not None) if negated else (get(row) is None)
    if isinstance(node, Not):
        inner = compile_condition(node.operand, scope)

        def negate(row):
            t = inner(row)
            return UNKNOWN if t is UNKNOWN else not t
        return negate
    if isinstance(node, (And, Or)):
        a, b = compile_condition(node.left, scope), compile_condition(node.right, scope)
        if isinstance(node, And):
            def conj(row):
                x, y = a(row), b(row)
                if x is False or y is False:
                    return False
                return UNKNOWN if x is UNKNOWN or y is UNKNOWN else True
            return conj

        def disj(row):
            x, y = a(row), b(row)
            if x is True or y is True:
                return True
            return UNKNOWN if x is UNKNOWN or y is UNKNOWN else False
        return disj
    raise SQLExecutionError(f'not a condition: {node!r}')


def sort_records(records: list, keys: list) -> list:
    """Stable multi-key sort; keys are (getter, descending); NULL is the smallest value."""
    records = list(records)
    for get, descending in reversed(keys):
        kinds = {kind(get(r)) for r in records} - {None}
        if len(kinds) > 1:
            raise SQLExecutionError(f'cannot sort values of kinds {sorted(kinds)}')
        present = [r for r in records if get(r) is not None]
        nulls = [r for r in records if get(r) is None]
        present.sort(key=get, reverse=descending)
        records = present + nulls if descending else nulls + present
    return records


def source_rows(stmt: Select, tables: dict) -> list[dict]:
    if stmt.table not in tables:
        raise SQLExecutionError(f'unknown table {stmt.table!r}')
    if stmt.join is None:
        return list(tables[stmt.table])
    a, b = stmt.table, stmt.join.table
    if b not in tables:
        raise SQLExecutionError(f'unknown table {b!r}')
    if a == b:
        raise SQLExecutionError('a table cannot be joined with itself')
    sides = {}
    for col in (stmt.join.left, stmt.join.right):
        qualifier, dot, _ = col.name.rpartition('.')
        if not dot or qualifier not in (a, b):
            raise SQLExecutionError(f'join column {col.name!r} must name {a!r} or {b!r}')
        sides[qualifier] = col.name
    if len(sides) != 2:
        raise SQLExecutionError('the join must compare a column of each table')
    left_key, right_key = sides[a], sides[b]
    joined = []
    for ra in tables[a]:
        row_a = {f'{a}.{k}': v for k, v in ra.items()}
        for rb in tables[b]:
            row_b = {f'{b}.{k}': v for k, v in rb.items()}
            if compare('=', row_a.get(left_key), row_b.get(right_key)) is True:
                joined.append({**row_a, **row_b})
    return joined


def aggregate(agg: Aggregate, rows: list[dict], get):
    if agg.arg is None:
        return len(rows)
    values = [v for v in map(get, rows) if v is not None]
    if agg.func == 'COUNT':
        return len(values)
    if not values:
        return None
    if agg.func in ('SUM', 'AVG'):
        if any(kind(v) != 'number' for v in values):
            raise SQLExecutionError(f'{agg.text} over a value that is not a number')
        total = sum(values)
        if agg.func == 'AVG':
            return total / len(values)
        return total if all(isinstance(v, int) for v in values) else float(total)
    if len({kind(v) for v in values}) > 1:
        raise SQLExecutionError(f'{agg.text} over values of different kinds')
    return min(values) if agg.func == 'MIN' else max(values)


def group_key(values: tuple) -> tuple:
    return tuple(values)


def execute(stmt: Select, tables: dict) -> list[dict]:
    rows = source_rows(stmt, tables)
    scope = Scope(stmt.table, stmt.join.table if stmt.join else None)
    item_getters = []
    for expr, key in stmt.items:
        if isinstance(expr, Aggregate):
            item_getters.append((key, expr, scope.getter(expr.arg.name) if expr.arg else None))
        else:
            item_getters.append((key, expr, scope.getter(expr.name)))
    if stmt.where is not None:
        cond = compile_condition(stmt.where, scope)
        rows = [r for r in rows if cond(r) is True]

    if stmt.grouped:
        group_getters = [scope.getter(ref) for ref in stmt.group_by]
        groups: dict[tuple, list[dict]] = {}
        if stmt.group_by:
            for r in rows:
                groups.setdefault(group_key(tuple(g(r) for g in group_getters)), []).append(r)
        else:
            groups[()] = rows
        out = []
        for members in groups.values():
            result = {}
            for key, expr, get in item_getters:
                if isinstance(expr, Aggregate):
                    result[key] = aggregate(expr, members, get)
                else:
                    result[key] = get(members[0])
            out.append(result)
        keys = []
        for text, descending in stmt.order_by:
            match = next((key for key, expr, _ in item_getters
                          if text == key or text == canonical(expr)), None)
            if match is None:
                raise SQLExecutionError(f'ORDER BY {text!r} is not a select item')
            keys.append(((lambda r, k=match: r[k]), descending))
        out = sort_records(out, keys)
        return out if stmt.limit is None else out[:stmt.limit]

    aliases = {key: get for key, expr, get in item_getters if key != canonical(expr)}
    keys = [(aliases[text] if text in aliases else scope.getter(text), descending)
            for text, descending in stmt.order_by]
    rows = sort_records(rows, keys)
    if stmt.limit is not None:
        rows = rows[:stmt.limit]
    if stmt.columns is None:
        return [dict(r) for r in rows]
    return [{key: get(r) for key, _expr, get in item_getters} for r in rows]


def query(sql: str, tables: dict) -> list[dict]:
    return execute(parse(sql), tables)
