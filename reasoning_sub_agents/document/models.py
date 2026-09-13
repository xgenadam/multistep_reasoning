from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel

from .operations import DocumentOp


class PartKind(StrEnum):
    SECTION = 'section'
    FILE = 'file'


RenderMode = Literal['markdown_with_files', 'sections_only']


class Part(BaseModel):
    id: str
    kind: PartKind
    title: str
    body: str
    origin_task: str | None = None


class PartOutline(BaseModel):
    id: str
    kind: PartKind
    title: str
    char_count: int


class AppliedOp(BaseModel):
    op: DocumentOp
    origin_task: str | None = None


class Document:
    def __init__(
        self,
        *,
        title: str | None = None,
        parts: list[Part] | None = None,
        summary: str = '',
        op_log: list[AppliedOp] | None = None,
        render_mode: RenderMode = 'markdown_with_files',
    ) -> None:
        self.title = title
        self.parts: list[Part] = parts if parts is not None else []
        self.summary = summary
        self.op_log: list[AppliedOp] = op_log if op_log is not None else []
        self.render_mode: RenderMode = render_mode

    @classmethod
    def empty(cls, *, render_mode: RenderMode = 'markdown_with_files') -> Self:
        return cls(render_mode=render_mode)

    def clone(self) -> Self:
        return self.__class__(
            title=self.title,
            parts=list(self.parts),
            summary=self.summary,
            op_log=list(self.op_log),
            render_mode=self.render_mode,
        )

    def part_index(self, part_id: str) -> int:
        for idx, part in enumerate(self.parts):
            if part.id == part_id:
                return idx
        raise KeyError(part_id)

    def get_part(self, part_id: str) -> Part:
        return self.parts[self.part_index(part_id)]

    def has_part(self, part_id: str) -> bool:
        return any(part.id == part_id for part in self.parts)

    def outline(self) -> list[PartOutline]:
        return [
            PartOutline(
                id=part.id,
                kind=part.kind,
                title=part.title,
                char_count=len(part.body),
            )
            for part in self.parts
        ]

    def render(self, mode: RenderMode | None = None) -> str:
        render_mode = mode or self.render_mode
        chunks: list[str] = []
        if self.title:
            chunks.append(f'# {self.title}')
        for part in self.parts:
            if part.kind == PartKind.SECTION:
                heading = f'## {part.title}' if part.title else ''
                block = f'{heading}\n\n{part.body}'.strip()
                chunks.append(block)
            elif render_mode == 'markdown_with_files':
                lang = _fence_language(part.title)
                fence = f'```{lang}\n{part.body}\n```' if lang else f'```\n{part.body}\n```'
                heading = f'## {part.title}' if part.title else '## file'
                chunks.append(f'{heading}\n\n{fence}')
        return '\n\n'.join(chunks).strip()

    def apply(
        self,
        ops: list[DocumentOp],
        *,
        current_result: str | None = None,
        origin_task: str | None = None,
    ) -> None:
        from .apply import apply_operations

        apply_operations(
            self,
            ops,
            current_result=current_result,
            origin_task=origin_task,
        )

    def to_dict(self) -> dict:
        return {
            'title': self.title,
            'parts': [part.model_dump() for part in self.parts],
            'summary': self.summary,
            'op_log': [entry.model_dump() for entry in self.op_log],
            'render_mode': self.render_mode,
        }


def _fence_language(title: str) -> str:
    if '.' not in title:
        return ''
    ext = title.rsplit('.', 1)[-1].lower()
    if ext in {'md', 'txt'}:
        return ''
    return ext
