import json
import logging
import re

from openai import OpenAI
from pydantic import BaseModel, TypeAdapter

from ..document import (
    AddPart,
    Document,
    DocumentApplyError,
    DocumentIntegrityError,
    DocumentOp,
    assert_payload_kept,
)
from ..llama_utils import generate_simple_llm_input, get_streamed_json_response
from ..schemas import SubTask

logger = logging.getLogger(__name__)


class ComposerResponse(BaseModel):
    ops: list[DocumentOp]


COMPOSE_PROMPT = """
You are the document composer for a multi-step LLM pipeline.
A user request was split into sub-tasks. After each sub-task you MUST update a
Document by proposing operations. You do not rewrite the whole answer.

Rules:
1. Prefer adding a new part with body_source="current_result" so the sub-task
   output is copied verbatim in code. Do not re-type the sub-task result.
2. You may write small glue yourself (titles, transitions, TOC, one-sentence
   bridges) as literal `body` text.
3. To revise an existing part, use replace_in_part / insert_in_part / update_part
   on that id only. replace_in_part.search must match the part body EXACTLY.
4. Never emit an operation that rewrites parts you are not changing.
5. There is no full-document overwrite. If the document is empty, add_part.
6. Choose kind="section" for prose in the final reply, kind="file" for named
   artifacts (code, configs). File titles should be paths (e.g. "src/main.py").
7. Part ids must be unique, stable, kebab-case (e.g. "chapter-3", "src-main-py").

This is the original user request:
================================================================================
{user_request}
================================================================================

These are all sub-tasks:
================================================================================
{sub_tasks}
================================================================================

This is the current sub-task:
================================================================================
{current_sub_task}
================================================================================

This is the current sub-task result (already stored; use body_source to include it):
================================================================================
{current_result}
================================================================================

Document outline:
================================================================================
{outline}
================================================================================

Existing part bodies (for exact search/replace only; do not re-emit these as new bodies):
================================================================================
{part_bodies}
================================================================================
{error_block}

Output JSON matching this schema:
```
{json_definition}
```
"""


class DocumentComposer:
    def __init__(
        self,
        llm_client: OpenAI,
        history: list | None = None,
        max_retries: int = 3,
    ) -> None:
        self.llm_client = llm_client
        self.history: list = history if history is not None else []
        self.max_retries = max_retries

    def compose(
        self,
        user_request: str,
        sub_tasks: list[SubTask],
        current_sub_task: SubTask,
        document: Document,
    ) -> list[DocumentOp]:
        current_result = _result_text(current_sub_task)
        last_error: str | None = None
        origin_task = current_sub_task.decomposed_sub_task.name

        for attempt in range(self.max_retries):
            ops = self._propose(
                user_request=user_request,
                sub_tasks=sub_tasks,
                current_sub_task=current_sub_task,
                document=document,
                error=last_error,
            )
            if not ops:
                logger.warning(
                    'composer returned no ops on attempt %s; defaulting to verbatim add_part',
                    attempt + 1,
                )
                ops = [_fallback_add_part(current_sub_task, document)]

            working = document.clone()
            try:
                working.apply(
                    ops,
                    current_result=current_result,
                    origin_task=origin_task,
                )
                assert_payload_kept(working, ops, current_result)
            except (DocumentApplyError, DocumentIntegrityError) as exc:
                last_error = str(exc)
                logger.warning('compose attempt %s failed: %s', attempt + 1, last_error)
                self.history.append(
                    {
                        'attempt': attempt + 1,
                        'ops': TypeAdapter(list[DocumentOp]).dump_python(ops),
                        'error': last_error,
                    }
                )
                continue

            document.title = working.title
            document.parts = working.parts
            document.summary = working.summary
            document.op_log = working.op_log
            self.history.append(
                {
                    'attempt': attempt + 1,
                    'ops': TypeAdapter(list[DocumentOp]).dump_python(ops),
                    'error': None,
                }
            )
            return ops

        raise DocumentApplyError(
            f'composer failed after {self.max_retries} retries: {last_error}'
        )

    def _propose(
        self,
        user_request: str,
        sub_tasks: list[SubTask],
        current_sub_task: SubTask,
        document: Document,
        error: str | None,
    ) -> list[DocumentOp]:
        error_block = ''
        if error:
            error_block = (
                '\nThe previous operations failed with this error. Fix it:\n'
                f'================================================================================\n'
                f'{error}\n'
                f'================================================================================\n'
            )
        part_bodies = [
            {
                'id': part.id,
                'kind': part.kind,
                'title': part.title,
                'body': part.body,
            }
            for part in document.parts
        ]
        prompt = COMPOSE_PROMPT.format(
            user_request=user_request,
            sub_tasks=json.dumps(
                [task.decomposed_sub_task.model_dump() for task in sub_tasks],
                indent=2,
            ),
            current_sub_task=current_sub_task.decomposed_sub_task.model_dump_json(
                indent=2
            ),
            current_result=_result_text(current_sub_task),
            outline=json.dumps(
                [item.model_dump() for item in document.outline()], indent=2
            ),
            part_bodies=json.dumps(part_bodies, indent=2),
            error_block=error_block,
            json_definition=json.dumps(ComposerResponse.model_json_schema(), indent=2),
        )
        response = get_streamed_json_response(
            llama_client=self.llm_client,
            llm_input=generate_simple_llm_input(prompt),
            response_model=ComposerResponse,
        )
        if isinstance(response, ComposerResponse):
            return list(response.ops)
        if isinstance(response, list):
            return response
        return [response]


def _result_text(sub_task: SubTask) -> str:
    result = sub_task.sub_task_result
    if result is None or result.chat_response is None:
        return ''
    return result.chat_response.content or ''


def _fallback_add_part(sub_task: SubTask, document: Document) -> AddPart:
    base = _slugify(sub_task.decomposed_sub_task.name)
    part_id = base
    n = 2
    while document.has_part(part_id):
        part_id = f'{base}-{n}'
        n += 1
    return AddPart(
        id=part_id,
        kind='section',
        title=sub_task.decomposed_sub_task.name,
        body_source='current_result',
        after='end',
        origin_task=sub_task.decomposed_sub_task.name,
    )


def _slugify(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return slug or 'part'


def changed_part_ids(ops: list[DocumentOp]) -> list[str]:
    ids: list[str] = []
    for op in ops:
        part_id = getattr(op, 'id', None)
        if isinstance(part_id, str) and part_id not in ids:
            ids.append(part_id)
    return ids
