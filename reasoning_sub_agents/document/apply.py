from .errors import DocumentApplyError
from .models import AppliedOp, Document, Part, PartKind
from .operations import (
    AddPart,
    AppendToPart,
    DeletePart,
    DocumentOp,
    InsertInPart,
    MovePart,
    ReplaceInPart,
    UpdatePart,
    _BodyMixin,
)


def apply_operations(
    document: Document,
    ops: list[DocumentOp],
    *,
    current_result: str | None = None,
    origin_task: str | None = None,
) -> None:
    """
    Apply ops atomically. On failure the original document is left unchanged.
    Untargeted parts keep object identity.
    """
    working = document.clone()
    applied: list[AppliedOp] = []
    for op in ops:
        _apply_one(
            working,
            op,
            current_result=current_result,
            origin_task=origin_task,
        )
        applied.append(AppliedOp(op=op, origin_task=origin_task))
    document.title = working.title
    document.parts = working.parts
    document.summary = working.summary
    document.op_log.extend(applied)


def resolve_body(op: _BodyMixin, current_result: str | None) -> str:
    if op.body_source == 'current_result':
        if current_result is None:
            raise DocumentApplyError(
                'body_source is current_result but no current sub-task result was provided'
            )
        return current_result
    if op.body is None:
        raise DocumentApplyError('operation is missing body and body_source')
    return op.body


def _apply_one(
    document: Document,
    op: DocumentOp,
    *,
    current_result: str | None,
    origin_task: str | None,
) -> None:
    if isinstance(op, AddPart):
        _add_part(document, op, current_result, origin_task)
    elif isinstance(op, AppendToPart):
        _append_to_part(document, op, current_result)
    elif isinstance(op, ReplaceInPart):
        _replace_in_part(document, op)
    elif isinstance(op, InsertInPart):
        _insert_in_part(document, op, current_result)
    elif isinstance(op, UpdatePart):
        _update_part(document, op, current_result)
    elif isinstance(op, MovePart):
        _move_part(document, op)
    elif isinstance(op, DeletePart):
        _delete_part(document, op)
    else:
        raise DocumentApplyError(f'unsupported operation: {type(op)!r}')


def _add_part(
    document: Document,
    op: AddPart,
    current_result: str | None,
    origin_task: str | None,
) -> None:
    if document.has_part(op.id):
        raise DocumentApplyError(f'part id already exists: {op.id}')
    body = resolve_body(op, current_result)
    part = Part(
        id=op.id,
        kind=PartKind(op.kind),
        title=op.title,
        body=body,
        origin_task=op.origin_task or origin_task,
    )
    insert_at = _index_after(document, op.after)
    document.parts.insert(insert_at, part)


def _append_to_part(
    document: Document, op: AppendToPart, current_result: str | None
) -> None:
    idx = _require_index(document, op.id)
    existing = document.parts[idx]
    addition = resolve_body(op, current_result)
    document.parts[idx] = existing.model_copy(update={'body': existing.body + addition})


def _replace_in_part(document: Document, op: ReplaceInPart) -> None:
    idx = _require_index(document, op.id)
    existing = document.parts[idx]
    found_at = existing.body.find(op.search)
    if found_at < 0:
        raise DocumentApplyError(
            f'search string not found in part {op.id!r}: {op.search!r}'
        )
    new_body = (
        existing.body[:found_at]
        + op.replace
        + existing.body[found_at + len(op.search) :]
    )
    document.parts[idx] = existing.model_copy(update={'body': new_body})


def _insert_in_part(
    document: Document, op: InsertInPart, current_result: str | None
) -> None:
    idx = _require_index(document, op.id)
    existing = document.parts[idx]
    found_at = existing.body.find(op.anchor)
    if found_at < 0:
        raise DocumentApplyError(
            f'anchor not found in part {op.id!r}: {op.anchor!r}'
        )
    insert_at = found_at + len(op.anchor)
    addition = resolve_body(op, current_result)
    new_body = existing.body[:insert_at] + addition + existing.body[insert_at:]
    document.parts[idx] = existing.model_copy(update={'body': new_body})


def _update_part(
    document: Document, op: UpdatePart, current_result: str | None
) -> None:
    idx = _require_index(document, op.id)
    existing = document.parts[idx]
    body = resolve_body(op, current_result)
    document.parts[idx] = existing.model_copy(update={'body': body})


def _move_part(document: Document, op: MovePart) -> None:
    idx = _require_index(document, op.id)
    part = document.parts.pop(idx)
    insert_at = _index_after(document, op.after)
    document.parts.insert(insert_at, part)


def _delete_part(document: Document, op: DeletePart) -> None:
    idx = _require_index(document, op.id)
    document.parts.pop(idx)


def _require_index(document: Document, part_id: str) -> int:
    try:
        return document.part_index(part_id)
    except KeyError as exc:
        raise DocumentApplyError(f'unknown part id: {part_id}') from exc


def _index_after(document: Document, after: str) -> int:
    if after == 'start':
        return 0
    if after == 'end':
        return len(document.parts)
    try:
        return document.part_index(after) + 1
    except KeyError as exc:
        raise DocumentApplyError(f'unknown after target: {after}') from exc
