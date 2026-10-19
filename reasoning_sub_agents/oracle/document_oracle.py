import json
import logging

from openai import OpenAI

from ..document import Document, Part
from ..document.summary import update_rolling_summary
from ..llama_utils import generate_simple_llm_input, get_streamed_json_response
from ..progress import llm_step
from ..prompt_budget import cap_prompt
from .tools import (
    AskTool,
    ListPartsTool,
    OracleAnswer,
    OracleTool,
    ReadPartTool,
    SearchHit,
    SearchTool,
    SummaryTool,
)

logger = logging.getLogger(__name__)

ASK_PROMPT = """
You answer questions about a document being built from sub-tasks.
Use only the retrieved excerpts. Cite part ids you used.

Question:
================================================================================
{question}
================================================================================

Document outline:
================================================================================
{outline}
================================================================================

Retrieved excerpts:
================================================================================
{excerpts}
================================================================================

Return JSON matching this schema:
```
{json_definition}
```
"""


class DocumentOracleError(Exception):
    pass


class DocumentOracle:
    def __init__(
        self,
        document: Document,
        llm_client: OpenAI | None = None,
        *,
        summary_max_words: int = 400,
        excerpt_chars: int = 160,
        prompt_token_budget: int = 16384,
    ) -> None:
        self.document = document
        self.llm_client = llm_client
        self.summary_max_words = summary_max_words
        self.excerpt_chars = excerpt_chars
        self.prompt_token_budget = prompt_token_budget

    def list_parts(self) -> list[dict]:
        return [item.model_dump() for item in self.document.outline()]

    def read_part(
        self, part_id: str, start: int | None = None, end: int | None = None
    ) -> str:
        try:
            part = self.document.get_part(part_id)
        except KeyError as exc:
            raise DocumentOracleError(f'unknown part id: {part_id}') from exc
        body = part.body
        if start is None and end is None:
            return body
        return body[start:end]

    def search(self, query: str) -> list[SearchHit]:
        if not query:
            return []
        needle = query.lower()
        hits: list[SearchHit] = []
        for part in self.document.parts:
            haystack = f'{part.title or ""}\n{part.body}'.lower()
            index = haystack.find(needle)
            if index < 0:
                continue
            hits.append(_hit(part, index, self.excerpt_chars))
        if hits:
            return hits
        tokens = [token for token in needle.split() if token]
        for part in self.document.parts:
            haystack = f'{part.title or ""}\n{part.body}'.lower()
            for token in tokens:
                index = haystack.find(token)
                if index >= 0:
                    hits.append(_hit(part, index, self.excerpt_chars))
                    break
        return hits

    def summary(self) -> str:
        return self.document.summary

    def ask(self, question: str) -> OracleAnswer:
        if self.llm_client is None:
            raise DocumentOracleError('ask() requires an llm_client')
        hits = self.search(question)
        if not hits:
            hits = [
                SearchHit(
                    part_id=part.id,
                    title=part.title,
                    index=0,
                    excerpt=part.body[: self.excerpt_chars * 2],
                )
                for part in self.document.parts[:8]
            ]
        excerpts = [hit.model_dump() for hit in hits]
        prompt = cap_prompt(
            ASK_PROMPT.format(
                question=question,
                outline=json.dumps(self.list_parts(), indent=2),
                excerpts=json.dumps(excerpts, indent=2),
                json_definition=json.dumps(OracleAnswer.model_json_schema(), indent=2),
            ),
            self.prompt_token_budget,
        )
        with llm_step('Oracle ask', 'oracle'):
            answer = get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=generate_simple_llm_input(prompt),
                response_model=OracleAnswer,
            )
        return answer

    def update_summary(self, changed_part_ids: list[str]) -> str:
        if self.llm_client is None:
            raise DocumentOracleError('update_summary() requires an llm_client')
        return update_rolling_summary(
            self.document,
            changed_part_ids,
            self.llm_client,
            max_words=self.summary_max_words,
            prompt_token_budget=self.prompt_token_budget,
        )

    def dispatch(self, tool_calls: list[OracleTool]) -> str:
        observations: list[dict] = []
        for tool in tool_calls:
            try:
                observations.append({'tool': tool.name, 'result': self._run(tool)})
            except DocumentOracleError as exc:
                observations.append({'tool': tool.name, 'error': str(exc)})
        return json.dumps(observations, indent=2)

    def _run(self, tool: OracleTool) -> object:
        if isinstance(tool, ListPartsTool):
            return self.list_parts()
        if isinstance(tool, ReadPartTool):
            return self.read_part(tool.id, tool.start, tool.end)
        if isinstance(tool, SearchTool):
            return [hit.model_dump() for hit in self.search(tool.query)]
        if isinstance(tool, AskTool):
            return self.ask(tool.question).model_dump()
        if isinstance(tool, SummaryTool):
            return self.summary()
        raise DocumentOracleError(f'unsupported tool: {type(tool)!r}')


def _hit(part: Part, index: int, excerpt_chars: int) -> SearchHit:
    start = max(0, index - excerpt_chars // 4)
    end = min(len(part.body), start + excerpt_chars)
    return SearchHit(
        part_id=part.id,
        title=part.title,
        index=index,
        excerpt=part.body[start:end],
    )
