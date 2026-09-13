from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode='after')
    def exactly_tools_or_result(self) -> Self:
        has_tools = bool(self.tool_calls)
        has_result = self.result is not None
        if has_tools == has_result:
            raise ValueError('Provide exactly one of tool_calls or result')
        return self


class OracleAnswer(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    part_id: str
    title: str
    index: int
    excerpt: str
