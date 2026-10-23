"""Render a parsed template against a context."""
import operator
from collections.abc import Mapping

from .lexer import TemplateRenderError
from .parser import (BoolOp, Compare, Filter, For, If, Literal, Not, Output, Path, Text,
                     parse)


def to_text(value) -> str:
    return '' if value is None else str(value)


def _seq(value):
    return value if isinstance(value, (str, list, tuple)) else list(value)


def _first(value):
    if value is None:
        return None
    seq = _seq(value)
    return seq[0] if len(seq) else None


def _last(value):
    if value is None:
        return None
    seq = _seq(value)
    return seq[-1] if len(seq) else None


def _reverse(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value[::-1]
    return list(value)[::-1]


def _join(value, sep):
    if value is None:
        return ''
    return sep.join(to_text(item) for item in value)


def _default(value, fallback):
    if value is None or (isinstance(value, str) and value == ''):
        return fallback
    return value


def _truncate(value, n):
    text = to_text(value)
    return text if len(text) < n else text[:n] + '...'


def _items(value):
    if value is None:
        return []
    if not isinstance(value, Mapping):
        raise TypeError(f'{type(value).__name__} is not a mapping')
    return list(value.items())


FILTERS = {
    'upper': lambda v: to_text(v).upper(),
    'lower': lambda v: to_text(v).lower(),
    'trim': lambda v: to_text(v).strip(),
    'length': lambda v: 0 if v is None else len(v),
    'first': _first,
    'last': _last,
    'reverse': _reverse,
    'join': _join,
    'default': _default,
    'truncate': _truncate,
    'items': _items,
}

_COMPARE = {'==': operator.eq, '!=': operator.ne, '<': operator.lt,
            '<=': operator.le, '>': operator.gt, '>=': operator.ge}


def _segment(value, seg):
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(str(seg))
    if isinstance(seg, int):
        if isinstance(value, (list, tuple)) and seg < len(value):
            return value[seg]
        return None
    if seg.startswith('_'):
        return None
    return getattr(value, seg, None)


def _lookup(scopes: list[dict], name: str):
    for scope in reversed(scopes):
        if name in scope:
            return scope[name]
    return None


def evaluate(expr, scopes: list[dict], lineno: int):
    if isinstance(expr, Literal):
        return expr.value
    if isinstance(expr, Path):
        value = _lookup(scopes, expr.name)
        for seg in expr.segments:
            value = _segment(value, seg)
        return value
    if isinstance(expr, Filter):
        value = evaluate(expr.expr, scopes, lineno)
        try:
            return FILTERS[expr.name](value, *expr.args)
        except (TypeError, ValueError, AttributeError, KeyError, IndexError) as e:
            raise TemplateRenderError(f'filter {expr.name!r} failed: {e}', lineno) from None
    if isinstance(expr, Compare):
        left = evaluate(expr.left, scopes, lineno)
        right = evaluate(expr.right, scopes, lineno)
        try:
            return bool(_COMPARE[expr.op](left, right))
        except TypeError as e:
            raise TemplateRenderError(f'cannot compare: {e}', lineno) from None
    if isinstance(expr, Not):
        return not evaluate(expr.operand, scopes, lineno)
    if isinstance(expr, BoolOp):
        left = bool(evaluate(expr.left, scopes, lineno))
        if expr.op == 'and':
            return left and bool(evaluate(expr.right, scopes, lineno))
        return left or bool(evaluate(expr.right, scopes, lineno))
    raise TypeError(f'unknown expression node {expr!r}')


def render_nodes(nodes: list, scopes: list[dict], out: list[str]) -> None:
    for node in nodes:
        if isinstance(node, Text):
            out.append(node.text)
        elif isinstance(node, Output):
            out.append(to_text(evaluate(node.expr, scopes, node.lineno)))
        elif isinstance(node, If):
            for condition, body, lineno in node.branches:
                if evaluate(condition, scopes, lineno):
                    render_nodes(body, scopes, out)
                    break
            else:
                if node.else_body is not None:
                    render_nodes(node.else_body, scopes, out)
        elif isinstance(node, For):
            _render_for(node, scopes, out)
        else:
            raise TypeError(f'unknown node {node!r}')


def _render_for(node: For, scopes: list[dict], out: list[str]) -> None:
    iterable = evaluate(node.iterable, scopes, node.lineno)
    if iterable is None:
        items = []
    else:
        try:
            items = list(iterable)
        except TypeError:
            raise TemplateRenderError(
                f'cannot loop over {type(iterable).__name__}', node.lineno) from None
    if not items:
        if node.else_body is not None:
            render_nodes(node.else_body, scopes, out)
        return
    scope: dict = {}
    scopes.append(scope)
    try:
        n = len(items)
        for i, item in enumerate(items):
            scope[node.name] = item
            scope['loop'] = {'index': i + 1, 'index0': i, 'first': i == 0,
                             'last': i == n - 1, 'length': n}
            render_nodes(node.body, scopes, out)
    finally:
        scopes.pop()


class Template:
    def __init__(self, source: str):
        self.source = source
        self.nodes = parse(source)

    def render(self, context: dict | None = None, **kwargs) -> str:
        base = dict(context or {})
        base.update(kwargs)
        out: list[str] = []
        render_nodes(self.nodes, [base], out)
        return ''.join(out)


def render(source: str, context: dict | None = None, **kwargs) -> str:
    return Template(source).render(context, **kwargs)
