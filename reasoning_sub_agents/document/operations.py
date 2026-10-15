from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

BodySource = Literal['current_result']


class _BodyMixin(BaseModel):
    body: str | None = None
    body_source: BodySource | None = None

    @model_validator(mode='after')
    def exactly_one_body_origin(self) -> Self:
        has_body = self.body is not None
        has_source = self.body_source is not None
        if has_body == has_source:
            raise ValueError('Provide exactly one of body or body_source')
        return self


class AddPart(_BodyMixin):
    type: Literal['add_part'] = 'add_part'
    id: str
    kind: Literal['section', 'file']
    # Optional (D1 / 0-02); omit when the part needs no heading.
    title: str | None = None
    after: str = 'end'
    origin_task: str | None = None


class AppendToPart(_BodyMixin):
    type: Literal['append_to_part'] = 'append_to_part'
    id: str


class ReplaceInPart(BaseModel):
    type: Literal['replace_in_part'] = 'replace_in_part'
    id: str
    search: str
    replace: str

    @model_validator(mode='after')
    def search_not_empty(self) -> Self:
        if not self.search:
            raise ValueError('search must not be empty')
        return self


class InsertInPart(_BodyMixin):
    type: Literal['insert_in_part'] = 'insert_in_part'
    id: str
    anchor: str

    @model_validator(mode='after')
    def anchor_not_empty(self) -> Self:
        if not self.anchor:
            raise ValueError('anchor must not be empty')
        return self


class UpdatePart(_BodyMixin):
    type: Literal['update_part'] = 'update_part'
    id: str


class MergeParts(BaseModel):
    """
    Deterministic, non-generative consolidation: fold every part named in
    `ids` into a single part.

    - `ids` is an *ordered* list; the first entry is the "primary" whose
      id/kind/title/origin_task survive on the merged part.
    - The merged part is placed at the primary's original position and its
      body is the bodies of all `ids` parts, in `ids` order, joined by a
      blank line. Reordering `ids` reorders the merged body and chooses a
      different survivor.
    - Every `ids` entry must be a unique, existing part id; length >= 2
      (merging a single part is a no-op and rejected).
    - No content is dropped and none is invented — pure state manipulation,
      so it costs the composer zero tokens (this is what the consolidation
      pass uses to replace the delete-then-re-add churn observed in the
      s3 baseline).
    """

    type: Literal['merge_parts'] = 'merge_parts'
    ids: list[str] = Field(min_length=2)

    @model_validator(mode='after')
    def ids_unique(self) -> Self:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError(f'merge ids must be unique: {self.ids}')
        return self


class MovePart(BaseModel):
    type: Literal['move_part'] = 'move_part'
    id: str
    after: str


class DeletePart(BaseModel):
    type: Literal['delete_part'] = 'delete_part'
    id: str


DocumentOp = Annotated[
    AddPart
    | AppendToPart
    | ReplaceInPart
    | InsertInPart
    | UpdatePart
    | MergeParts
    | MovePart
    | DeletePart,
    Field(discriminator='type'),
]
