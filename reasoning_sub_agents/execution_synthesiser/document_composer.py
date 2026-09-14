import json
import logging
import re

from openai import OpenAI
from pydantic import BaseModel, Field, TypeAdapter

from ..document import (
    AddPart,
    Document,
    DocumentApplyError,
    DocumentIntegrityError,
    DocumentOp,
    assert_payload_kept,
    preview_text,
)
from ..llama_utils import generate_simple_llm_input, get_streamed_json_response
from ..progress import llm_step, set_phase
from ..prompt_budget import PromptPiece, budgeted_prompt
from ..schemas import SubTask

logger = logging.getLogger(__name__)

MAX_ATTACHED_PARTS = 4


class ComposerResponse(BaseModel):
    need_part_ids: list[str] = Field(default_factory=list)
    ops: list[DocumentOp] = Field(default_factory=list)


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
4. You do NOT receive every part body. You get an outline, a rolling summary,
   and a preview of the current result. If you need exact text for a patch,
   set need_part_ids to those ids and leave ops empty. Those bodies will be
   attached on the next call (at most {max_attached} parts).
5. Never emit an operation that rewrites parts you are not changing.
6. There is no full-document overwrite. If the document is empty, add_part.
7. Choose kind="section" for prose, kind="file" for named artifacts.
8. Part ids must be unique, stable, kebab-case.

This is the original user request:
================================================================================
{user_request}
================================================================================

Sub-task names and objectives:
================================================================================
{sub_tasks}
================================================================================

This is the current sub-task:
================================================================================
{current_sub_task}
================================================================================

Current sub-task result preview (full text is stored; use body_source to copy it):
================================================================================
{result_preview}
================================================================================

Rolling summary:
================================================================================
{summary}
================================================================================

Document outline:
================================================================================
{outline}
================================================================================

Attached part bodies (only the parts you asked for or that failed last apply):
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
        max_attached_parts: int = MAX_ATTACHED_PARTS,
        prompt_token_budget: int = 16384,
    ) -> None:
        self.llm_client = llm_client
        self.history: list = history if history is not None else []
        self.max_retries = max_retries
        self.max_attached_parts = max_attached_parts
        self.prompt_token_budget = prompt_token_budget

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
        loaded_ids: list[str] = []

        for attempt in range(self.max_retries):
            response = self._propose(
                user_request=user_request,
                sub_tasks=sub_tasks,
                current_sub_task=current_sub_task,
                document=document,
                error=last_error,
                attached_ids=loaded_ids,
            )
            fetched = _take_needed_parts(
                document,
                response.need_part_ids,
                loaded_ids,
                self.max_attached_parts,
            )
            if fetched and not response.ops:
                loaded_ids.extend(fetched)
                self.history.append(
                    {
                        'attempt': attempt + 1,
                        'need_part_ids': list(fetched),
                        'ops': [],
                        'error': None,
                    }
                )
                continue
            if fetched:
                loaded_ids.extend(fetched)

            ops = list(response.ops)
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
                for part_id in changed_part_ids(ops):
                    if document.has_part(part_id) and part_id not in loaded_ids:
                        loaded_ids.append(part_id)
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
        attached_ids: list[str],
    ) -> ComposerResponse:
        error_block = ''
        if error:
            error_block = (
                '\nThe previous operations failed with this error. Fix it:\n'
                f'================================================================================\n'
                f'{error}\n'
                f'================================================================================\n'
            )
        attached = []
        for part_id in attached_ids:
            if not document.has_part(part_id):
                continue
            part = document.get_part(part_id)
            attached.append(
                {
                    'id': part.id,
                    'kind': part.kind,
                    'title': part.title,
                    'body': part.body,
                }
            )
        sub_task_brief = [
            {
                'name': task.decomposed_sub_task.name,
                'objective': task.decomposed_sub_task.objective,
            }
            for task in sub_tasks
        ]
        schema = json.dumps(ComposerResponse.model_json_schema(), indent=2)
        prompt = budgeted_prompt(
            [
                PromptPiece(
                    'core',
                    COMPOSE_PROMPT.format(
                        user_request=user_request,
                        sub_tasks=json.dumps(sub_task_brief, indent=2),
                        current_sub_task=current_sub_task.decomposed_sub_task.model_dump_json(
                            indent=2
                        ),
                        result_preview=preview_text(_result_text(current_sub_task)),
                        summary=document.summary or '(empty)',
                        outline=json.dumps(
                            [item.model_dump() for item in document.outline()],
                            indent=2,
                        ),
                        part_bodies='(see attached parts below)',
                        error_block='',
                        json_definition='(see schema below)',
                        max_attached=self.max_attached_parts,
                    ),
                    priority=0,
                    truncatable=False,
                ),
                PromptPiece(
                    'part_bodies',
                    'Attached part bodies:\n'
                    + (json.dumps(attached, indent=2) if attached else '(none)'),
                    priority=4,
                ),
                PromptPiece('error', error_block, priority=2),
                PromptPiece(
                    'schema',
                    'Output JSON matching this schema:\n```\n' + schema + '\n```',
                    priority=0,
                    truncatable=False,
                ),
            ],
            self.prompt_token_budget,
        )
        set_phase('Composing document operations (JSON)')
        with llm_step('Compose document ops (JSON)'):
            response = get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=generate_simple_llm_input(prompt),
                response_model=ComposerResponse,
            )
        if isinstance(response, ComposerResponse):
            return response
        if isinstance(response, list):
            return ComposerResponse(ops=response)
        return ComposerResponse(ops=[response])


def _take_needed_parts(
    document: Document,
    requested: list[str],
    already: list[str],
    limit: int,
) -> list[str]:
    fetched: list[str] = []
    for part_id in requested:
        if part_id in already or part_id in fetched:
            continue
        if not document.has_part(part_id):
            continue
        fetched.append(part_id)
        if len(fetched) >= limit:
            break
    return fetched


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
