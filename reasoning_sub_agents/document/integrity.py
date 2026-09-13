from .errors import DocumentIntegrityError
from .models import Document
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
        if current_result not in _all_bodies(document):
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
        if current_result not in part.body:
            raise DocumentIntegrityError(
                f'sub-task result was not kept in part {part_id!r}'
            )


def _all_bodies(document: Document) -> str:
    return '\n'.join(part.body for part in document.parts)
