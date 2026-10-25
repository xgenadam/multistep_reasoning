import ast
import re

from .errors import DocumentIntegrityError
from .models import Document, unwrap_outer_fence
from .operations import (
    AddPart,
    AppendToPart,
    DocumentOp,
    InsertInPart,
    UpdatePart,
    _BodyMixin,
)


def assert_payload_kept(
    document: Document,
    ops: list[DocumentOp],
    current_result: str,
) -> None:
    """
    Enforce that a sub-task result is not dropped.

    - body_source=current_result is kept by construction.
    - A file part keeps the result without its outer fence (0-09).
    - Literal bodies on add/append/update/insert must contain the result
      in the targeted part after apply.
    - Patch-only ops (replace/move/delete) do not require the full payload.
    """
    if not current_result:
        return

    used_body_source = False
    wrote_literal_body = False
    targeted_ids: list[str] = []

    for op in ops:
        if isinstance(op, _BodyMixin) and op.body_source == 'current_result':
            used_body_source = True
        if isinstance(op, (AddPart, AppendToPart, UpdatePart, InsertInPart)):
            if op.body is not None:
                wrote_literal_body = True
                targeted_ids.append(op.id)

    if used_body_source:
        if not _kept(current_result, _all_bodies(document)):
            raise DocumentIntegrityError(
                'body_source=current_result was used but the payload is not in the document'
            )
        return

    if not wrote_literal_body:
        return

    for part_id in targeted_ids:
        try:
            part = document.get_part(part_id)
        except KeyError as exc:
            raise DocumentIntegrityError(
                f'composed part {part_id!r} is missing from the document'
            ) from exc
        if not _kept(current_result, part.body):
            raise DocumentIntegrityError(
                f'sub-task result was not kept in part {part_id!r}'
            )


def _kept(payload: str, body: str) -> bool:
    return payload in body or unwrap_outer_fence(payload) in body


def _all_bodies(document: Document) -> str:
    return '\n'.join(part.body for part in document.parts)


# D-030: the keep rule as a setting. verbatim is assert_payload_kept above.
_FENCED = re.compile(r'^(`{3,}|~{3,})[^\n]*\n(.*?)^\1[ \t]*$', re.DOTALL | re.MULTILINE)
_TOP_DEF = re.compile(r'^(?:async\s+def|def|class)\s+([A-Za-z_]\w*)', re.MULTILINE)
_ANY_DEF = re.compile(r'^[ \t]*(?:async\s+def|def|class)\s+([A-Za-z_]\w*)', re.MULTILINE)


def defined_names(result: str) -> list[str]:
    """Top-level functions and classes a sub-task result defines, from its
    fenced code blocks (or the whole text when there are none)."""
    blocks = [m.group(2) for m in _FENCED.finditer(result)] or [unwrap_outer_fence(result)]
    names: list[str] = []
    for code in blocks:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            found = _TOP_DEF.findall(code)
        else:
            found = [n.name for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        names.extend(n for n in found if n not in names)
    return names


def line_coverage(result: str, document: Document) -> float:
    """Share of the result's non-blank lines (stripped) found in the document."""
    lines = [ln.strip() for ln in result.splitlines() if ln.strip() and not ln.strip().startswith(('```', '~~~'))]
    if not lines:
        return 1.0
    have = {ln.strip() for part in document.parts for ln in part.body.splitlines()}
    return round(sum(ln in have for ln in lines) / len(lines), 3)


def _is_python(part) -> bool:
    return part.kind == 'file' and any((x or '').endswith('.py') for x in (part.id, part.title))


def check_payload(
    document: Document,
    ops: list[DocumentOp],
    current_result: str,
    rule: str = 'verbatim',
) -> dict:
    """Apply the keep rule; return what was kept, for the composer history.

    verbatim: assert_payload_kept. names: every .py part an op wrote a literal
    body into must parse, and every top-level def/class of the result must be
    defined somewhere in the document (a merge or refactor may move it).
    off: nothing enforced. Coverage is measured under every rule.
    """
    stats: dict = {'keep_rule': rule, 'coverage': line_coverage(current_result, document)}
    if rule == 'verbatim':
        assert_payload_kept(document, ops, current_result)
        return stats
    if rule == 'off' or not current_result:
        return stats
    literal_ids = [op.id for op in ops
                   if isinstance(op, (AddPart, AppendToPart, UpdatePart, InsertInPart)) and op.body is not None]
    for part_id in literal_ids:
        if not document.has_part(part_id):
            continue
        part = document.get_part(part_id)
        if _is_python(part):
            try:
                ast.parse(unwrap_outer_fence(part.body))
            except SyntaxError as exc:
                raise DocumentIntegrityError(
                    f'file part {part_id!r} does not parse as Python after the edit '
                    f'(line {exc.lineno}: {exc.msg}); write the whole file as valid code'
                ) from exc
    have = set(_ANY_DEF.findall('\n'.join(part.body for part in document.parts)))
    missing = [n for n in defined_names(current_result) if n not in have]
    stats['names_missing'] = missing
    if missing:
        raise DocumentIntegrityError(
            'the sub-task defined ' + ', '.join(missing) + ' but the document no longer defines '
            + ('it' if len(missing) == 1 else 'them')
            + '; keep every function and class (merging or refactoring them is fine)'
        )
    return stats
