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
    title: str
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
    | MovePart
    | DeletePart,
    Field(discriminator='type'),
]
