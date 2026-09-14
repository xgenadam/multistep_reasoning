import json
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class ListPartsTool(BaseModel):
    name: Literal['list_parts'] = 'list_parts'


class ReadPartTool(BaseModel):
    name: Literal['read_part'] = 'read_part'
    id: str
    start: int | None = None
    end: int | None = None


class SearchTool(BaseModel):
    name: Literal['search'] = 'search'
    query: str


class AskTool(BaseModel):
    name: Literal['ask'] = 'ask'
    question: str


class SummaryTool(BaseModel):
    name: Literal['summary'] = 'summary'


OracleTool = Annotated[
    ListPartsTool | ReadPartTool | SearchTool | AskTool | SummaryTool,
    Field(discriminator='name'),
]


class ExecutorTurn(BaseModel):
    thinking: str | None = None
    tool_calls: list[OracleTool] | None = None
    result: str | None = None

    @field_validator('thinking', 'result', mode='before')
    @classmethod
    def _stringify(cls, value: Any) -> str | None:
        return _as_text(value)

    @model_validator(mode='before')
    @classmethod
    def _flatten_qwen_shape(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            if isinstance(data, str):
                return {'result': data}
            return data
        data = dict(data)
        if 'thinking' not in data and 'thinking_step' in data:
            data['thinking'] = data['thinking_step']
        if data.get('tool_calls') in (None, []) and not _nonempty_text(data.get('result')):
            leftover = {
                k: v
                for k, v in data.items()
                if k not in {'thinking', 'thinking_step', 'tool_calls', 'result'}
                and v not in (None, '', [], {})
            }
            if leftover:
                data['result'] = leftover
            elif data.get('result') in (None, '', {}, []):
                data['result'] = None
        return data

    @model_validator(mode='after')
    def exactly_tools_or_result(self) -> Self:
        has_tools = bool(self.tool_calls)
        has_result = bool((self.result or '').strip())
        if has_tools and has_result:
            raise ValueError('Provide exactly one of tool_calls or result, not both')
        return self


_NULL_STRINGS = frozenset(
    {'', 'null', 'none', 'undefined', 'nil', '{}', '[]', '{"result": null}', '{"result":null}'}
)


def _nonempty_text(value: Any) -> bool:
    text = _as_text(value)
    return bool(text and text.strip())


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in _NULL_STRINGS:
            return None
        return value
    if isinstance(value, dict):
        if not value or all(v is None for v in value.values()):
            return None
        for key in ('text', 'content', 'result', 'answer', 'output', 'thinking'):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip() and inner.strip().lower() not in _NULL_STRINGS:
                return inner
            if isinstance(inner, dict):
                nested = _as_text(inner)
                if nested:
                    return nested
        dumped = json.dumps(value, ensure_ascii=False)
        if dumped.strip().lower() in _NULL_STRINGS:
            return None
        return dumped
    return str(value)


class OracleAnswer(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    part_id: str
    title: str
    index: int
    excerpt: str
