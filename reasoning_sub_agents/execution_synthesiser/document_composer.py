import json
import logging
import re
from typing import Annotated

from openai import OpenAI
from pydantic import BaseModel, Field, TypeAdapter

from ..document import (
    AddPart,
    DeletePart,
    Document,
    DocumentApplyError,
    DocumentIntegrityError,
    DocumentOp,
    MergeParts,
    MovePart,
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


# 0-06 consolidation: restricted op set — cleanup only, never add content.
ConsolidationOp = Annotated[
    MergeParts | MovePart | DeletePart,
    Field(discriminator='type'),
]


class ConsolidationResponse(BaseModel):
    ops: list[ConsolidationOp] = Field(default_factory=list)


CONSOLIDATE_PROMPT = """
You are the document consolidator for a multi-step LLM pipeline. All
sub-tasks are done. Your ONLY job is outline-level cleanup of the finished
document before it is presented: fold redundant or near-duplicate parts,
remove parts that add nothing, and fix ordering. You do NOT write new
content.

You may ONLY emit these operations:
- merge_parts: fold overlapping / redundant parts into one. "ids" is the
  ORDERED list of source part ids; the FIRST keeps its id, kind, title and
  position and the bodies are concatenated in ids order. Only merge parts
  whose content genuinely overlaps — never merge distinct topics just to
  shorten the document.
- move_part: reorder a part (set "after" to a part id or "end").
- delete_part: remove a part ONLY when it is redundant or an orphan (e.g. a
  stub, a leftover that a merge already absorbed, or a part whose content is
  fully covered by another). Deleting a part discards its body, so delete
  only what is truly safe to lose.

Rules:
1. You do NOT receive part bodies — only the outline (ids, kinds, titles,
   sizes) and a rolling summary. Decide from those; if you are unsure, do
   NOT delete.
2. Prefer merge over delete: consolidation should preserve content.
3. Do not change titles, bodies, or kinds. Do not emit any other operation
   (no add_part, no update/append/replace/insert).
4. If the document is already clean, emit an empty "ops" list.

Original user request (context only):
================================================================================
{user_request}
================================================================================

Rolling summary:
================================================================================
{summary}
================================================================================

Document outline (id, kind, title, char count):
================================================================================
{outline}
================================================================================

Output JSON matching this schema:
```
{json_definition}
```
"""


COMPOSE_PROMPT = """
You are the document composer for a multi-step LLM pipeline.
A user request was split into sub-tasks. After each sub-task you MUST update a
Document by proposing operations. You do not rewrite the whole answer.

Available operations:
- add_part: add a new part (id, kind, optional title, body or body_source, after).
- append_to_part: append text to the end of an existing part.
- replace_in_part: swap an exact substring inside a part.
- insert_in_part: insert text right after an exact anchor substring.
- update_part: replace one part's whole body.
- merge_parts: fold existing parts into one. "ids" is the ORDERED list of
  source part ids; the FIRST keeps its id, kind, title and position, the
  bodies are concatenated in ids order separated by a blank line, the other
  parts are deleted. Pure consolidation: nothing is added or lost.
- move_part: change a part's position.
- delete_part: remove a part.

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
7. Choose kind="section" for prose, kind="file" for runnable artifacts
   (scripts, tools, code files). A file part's title MUST be the filename with
   its extension (e.g. "wordcount.py"). A file part's body is the RAW file
   content only — never wrap it in ``` code fences (the renderer adds the
   fence and infers the language from the title), and never append usage
   notes, verification tables, or other commentary after the code; if notes
   are needed, put them in a separate section part.
8. Part ids must be unique, stable, kebab-case.
9. Titles are OPTIONAL. Omit title when a part needs no heading; when you do
   set one, keep it short and factual.
10. No duplicates: if the new content would overlap an existing part, prefer
    merge_parts (fold the parts) or a targeted patch over a near-duplicate
    add_part. Never add a part that merely restates what an existing part
    already says.
11. Match the output shape to the deliverable: if the sub-task's deliverable
    is a runnable artifact, its code goes in a file part, not buried inside a
    prose section; if the deliverable is prose (report, analysis, explanation)
    use section parts and do NOT emit file parts for prose. A prose section
    with several distinct aspects must use markdown "## " sub-headings inside
    its body, not one flat block of text.

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

    def consolidate(
        self,
        user_request: str,
        document: Document,
    ) -> list[ConsolidationOp]:
        """
        0-06: one best-effort consolidation pass after the final sub-task.

        Outline + summary only (no part bodies), restricted to
        merge/move/delete. Returns the ops applied (possibly empty); a bad
        proposal is logged and abandoned — this pass must never fail the
        pipeline or drop content it could not verify.
        """
        if len(document.parts) < 2:
            return []
        prompt = self._build_consolidation_prompt(user_request, document)
        set_phase('Consolidating document (JSON)')
        with llm_step('Consolidate document ops (JSON)', 'consolidate'):
            response = get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=generate_simple_llm_input(prompt),
                response_model=ConsolidationResponse,
            )
        if isinstance(response, list):
            response = ConsolidationResponse(ops=response)
        ops = list(response.ops)
        self.history.append(
            {
                'phase': 'consolidation',
                'ops': TypeAdapter(list[ConsolidationOp]).dump_python(ops),
                'error': None,
            }
        )
        if not ops:
            return []
        working = document.clone()
        try:
            working.apply(ops, origin_task='consolidation')
            # Consolidation may never drop the document or shrink it to
            # nothing: if the proposal leaves no parts, it is a no-op.
            if not working.parts:
                logger.warning('consolidation proposal empties the document; ignoring')
                self.history.append(
                    {'phase': 'consolidation', 'ops': [], 'error': 'emptied document'}
                )
                return []
        except (DocumentApplyError, DocumentIntegrityError) as exc:
            logger.warning('consolidation proposal invalid, abandoning: %s', exc)
            self.history.append(
                {
                    'phase': 'consolidation',
                    'ops': TypeAdapter(list[ConsolidationOp]).dump_python(ops),
                    'error': str(exc),
                }
            )
            return []
        document.title = working.title
        document.parts = working.parts
        document.op_log = working.op_log
        return ops

    def _build_consolidation_prompt(
        self,
        user_request: str,
        document: Document,
    ):
        # Outline only: id, kind, title and size — never bodies.
        outline = [
            {
                'id': p.id,
                'kind': p.kind,
                'title': p.title,
                'chars': len(p.body),
            }
            for p in document.parts
        ]
        schema = json.dumps(ConsolidationResponse.model_json_schema(), indent=2)
        core = CONSOLIDATE_PROMPT.format(
            user_request=user_request,
            summary=document.summary or '(empty)',
            outline=json.dumps(outline, indent=2),
            json_definition='(see schema below)',
        )
        return budgeted_prompt(
            [
                PromptPiece('core', core, priority=0, truncatable=False),
                PromptPiece(
                    'schema',
                    'Output JSON matching this schema:\n```\n' + schema + '\n```',
                    priority=0,
                    truncatable=False,
                ),
            ],
            self.prompt_token_budget,
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
        with llm_step('Compose document ops (JSON)', 'compose'):
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
        if isinstance(op, MergeParts):
            # The survivor (first id) and every absorbed part are all
            # summary-relevant: the survivor's body changed and the others
            # no longer exist.
            candidates = list(op.ids)
        else:
            part_id = getattr(op, 'id', None)
            candidates = [part_id] if isinstance(part_id, str) else []
        for part_id in candidates:
            if part_id not in ids:
                ids.append(part_id)
    return ids
