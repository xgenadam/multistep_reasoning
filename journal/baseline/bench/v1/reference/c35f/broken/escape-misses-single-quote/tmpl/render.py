"""Render a parsed template against a context; loaders and environments."""
import html
import operator
from collections.abc import Mapping

from .lexer import TemplateNotFound, TemplateRenderError
from .parser import (Block, BoolOp, Compare, Extends, Filter, For, If, Literal, Not, Output,
                     Path, Super, Text, parse)


def _escape(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


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
    return text if len(text) <= n else text[:n] + '...'


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
    'safe': lambda v: v,
    'escape': lambda v: _escape(to_text(v)),
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


class _Renderer:
    def __init__(self, blocks: dict[str, list[Block]], autoescape: bool):
        self.blocks = blocks          # name -> definitions, most derived first
        self.autoescape = autoescape
        self.stack: list[tuple[str, int]] = []   # blocks being rendered: (name, level)

    def nodes(self, nodes: list, scopes: list[dict], out: list[str]) -> None:
        for node in nodes:
            if isinstance(node, Text):
                out.append(node.text)
            elif isinstance(node, Output):
                text = to_text(evaluate(node.expr, scopes, node.lineno))
                last = node.expr.name if isinstance(node.expr, Filter) else None
                if self.autoescape and last not in ('safe', 'escape'):
                    text = _escape(text)
                out.append(text)
            elif isinstance(node, If):
                for condition, body, lineno in node.branches:
                    if evaluate(condition, scopes, lineno):
                        self.nodes(body, scopes, out)
                        break
                else:
                    if node.else_body is not None:
                        self.nodes(node.else_body, scopes, out)
            elif isinstance(node, For):
                self.loop(node, scopes, out)
            elif isinstance(node, Block):
                self.block(node.name, 0, scopes, out)
            elif isinstance(node, Super):
                name, level = self.stack[-1]
                if level + 1 >= len(self.blocks[name]):
                    raise TemplateRenderError(f'block {name!r} has no parent to call', node.lineno)
                self.block(name, level + 1, scopes, out)
            elif isinstance(node, Extends):
                pass
            else:
                raise TypeError(f'unknown node {node!r}')

    def block(self, name: str, level: int, scopes: list[dict], out: list[str]) -> None:
        self.stack.append((name, level))
        try:
            self.nodes(self.blocks[name][level].body, scopes, out)
        finally:
            self.stack.pop()

    def loop(self, node: For, scopes: list[dict], out: list[str]) -> None:
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
                self.nodes(node.else_body, scopes, out)
            return
        scope: dict = {}
        scopes.append(scope)
        try:
            n = len(items)
            for i, item in enumerate(items):
                scope[node.name] = item
                scope['loop'] = {'index': i + 1, 'index0': i, 'first': i == 0,
                                 'last': i == n - 1, 'length': n}
                self.nodes(node.body, scopes, out)
        finally:
            scopes.pop()


def _collect_blocks(nodes: list, found: dict[str, Block]) -> None:
    for node in nodes:
        if isinstance(node, Block):
            found[node.name] = node
            _collect_blocks(node.body, found)
        elif isinstance(node, If):
            for _, body, _ in node.branches:
                _collect_blocks(body, found)
            _collect_blocks(node.else_body or [], found)
        elif isinstance(node, For):
            _collect_blocks(node.body, found)
            _collect_blocks(node.else_body or [], found)


def _extends(nodes: list) -> Extends | None:
    for node in nodes:
        if isinstance(node, Extends):
            return node
    return None


class DictLoader:
    def __init__(self, templates: dict[str, str]):
        self.templates = dict(templates)

    def get_source(self, name: str) -> str:
        try:
            return self.templates[name]
        except KeyError:
            raise TemplateNotFound(name) from None


class Template:
    def __init__(self, source: str, *, loader=None, autoescape: bool = False,
                 name: str | None = None):
        self.source = source
        self.loader = loader
        self.autoescape = autoescape
        self.name = name
        self.nodes = parse(source)

    def _chain(self) -> list[list]:
        """Node lists from this template up to its base."""
        chain, names = [self.nodes], [self.name]
        ext = _extends(self.nodes)
        while ext is not None:
            if ext.name in names:
                raise TemplateRenderError(f'circular extends of {ext.name!r}', ext.lineno)
            if self.loader is None:
                raise TemplateNotFound(ext.name)
            parent = parse(self.loader.get_source(ext.name))
            chain.append(parent)
            names.append(ext.name)
            ext = _extends(parent)
        return chain

    def render(self, context: dict | None = None, **kwargs) -> str:
        base = dict(context or {})
        base.update(kwargs)
        chain = self._chain()
        blocks: dict[str, list[Block]] = {}
        for nodes in chain:
            found: dict[str, Block] = {}
            _collect_blocks(nodes, found)
            for name, block in found.items():
                blocks.setdefault(name, []).append(block)
        out: list[str] = []
        _Renderer(blocks, self.autoescape).nodes(chain[-1], [base], out)
        return ''.join(out)


class Environment:
    def __init__(self, loader=None, autoescape: bool = False):
        self.loader = loader
        self.autoescape = autoescape

    def get_template(self, name: str) -> Template:
        if self.loader is None:
            raise TemplateNotFound(name)
        return Template(self.loader.get_source(name), loader=self.loader,
                        autoescape=self.autoescape, name=name)

    def from_string(self, source: str) -> Template:
        return Template(source, loader=self.loader, autoescape=self.autoescape)


def render(source: str, context: dict | None = None, **kwargs) -> str:
    return Template(source).render(context, **kwargs)
