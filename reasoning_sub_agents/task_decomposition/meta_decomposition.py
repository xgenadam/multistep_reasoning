"""Meta-prompt decomposition (the user, 2026-10-25; journal/design/meta-prompts.md).

The model is told how the pipeline works and writes the planner's instructions
itself; only the frame is fixed: the request, the JSON schema, and the one rule
the code enforces (at least one sub_task_detail item). There is no critique or
forced regeneration here: those carry hand-written rules (3-5 sub-tasks) that
would override what the model wrote.

- frozen: the instructions come from a file written once, offline
  (journal/baseline/write_meta_prompt.py), by the model itself or another one.
- dynamic: the model writes instructions for each request at run time (one more
  call per turn), seeing the request.

The hand-written decomposers (simple, self_critique) are unchanged.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import OpenAI
from pydantic import TypeAdapter

from ..llama_utils import extract_content, generate_simple_llm_input, get_streamed_json_response, stream_conversation
from ..progress import llm_step, set_phase
from ..prompt_budget import cap_prompt
from ..schemas import DecomposeItem
from .simple_decomposition import CONVERSATION_BLOCK, SimpleTaskDecomposer

logger = logging.getLogger(__name__)

WORKFLOW = """\
How the pipeline works:
1. A planner model reads the user's request and splits it into sub-tasks, as a JSON list.
2. Each sub-task is then executed on its own by a model that sees: the user's full request; that sub-task's name, \
objective, context and description as the planner wrote them; an outline of the shared document so far (part ids, \
kinds and titles) and a short rolling summary of it. It can look up parts of the document with tools, but it does not \
see the other sub-tasks' plans.
3. After each sub-task, a composer model edits the shared document to take in that sub-task's result: it can add a \
part (a file or a section), replace or merge parts, move or delete them. The harness checks each edit and asks again \
when one breaks the document (for example, a Python file part that no longer parses, or functions the sub-task wrote \
that disappear).
4. When every sub-task is done, the document is the answer. For a code request, its file parts are extracted and run \
against hidden tests; for prose, it is read as a whole.
"""

FIXED = """\
What is fixed, and cannot be changed by your instructions:
- The planner's reply must be JSON matching the schema it is given (shown below).
- The list must contain at least one item with meta_type "sub_task_detail"; those are the sub-tasks that run.
Everything else (how many sub-tasks, what each one covers, what each must deliver, what context each is given, the \
order) is for your instructions to decide.
"""

META_PROMPT = """\
You are writing the instructions a planner model will follow in a multi-step pipeline. Your instructions will be \
placed in the planner's prompt, after the user's request and before the JSON schema.

{workflow}
{fixed}
{target}

Write the instructions that will lead the planner to the breakdown most likely to produce a correct, complete final \
answer. Write them for the planner directly (address it as "you"). Do not restate the JSON schema; it is appended. \
Reply with the instructions only, as plain text.

The JSON schema the planner must follow, for reference:
```
{json_definition}
```
"""

TARGET_FROZEN = """\
These instructions will be used unchanged for every request. Requests vary: programs of one or more files with an \
exact interface and output format (tested by hidden tests), follow-ups that change an earlier answer, and prose \
tasks (reports, analyses, plans)."""

TARGET_DYNAMIC = """\
These instructions are for this one request:
================================================================================
{user_input}
================================================================================"""

FRAME = """
The user's request is:
================================================================================
{user_input}
================================================================================

{conversation_block}{instructions}

Output JSON in this schema:
```
{json_definition}
```
"""

MIN_INSTRUCTION_CHARS = 80


def decompose_schema() -> str:
    return json.dumps(TypeAdapter(list[DecomposeItem]).json_schema(), indent=4)


def meta_prompt(user_input: str | None) -> str:
    target = TARGET_FROZEN if user_input is None else TARGET_DYNAMIC.format(user_input=user_input)
    return META_PROMPT.format(workflow=WORKFLOW, fixed=FIXED, target=target, json_definition=decompose_schema())


def clean_instructions(text: str) -> str:
    """The written instructions, minus a wrapping fence or a restated schema."""
    text = (text or '').strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.strip('`').split('\n', 1)[-1].strip()
    return text


def valid_instructions(text: str) -> str | None:
    """Why written instructions cannot be used, or None if they can."""
    if len(text.strip()) < MIN_INSTRUCTION_CHARS:
        return f'too short ({len(text.strip())} characters)'
    if '"$defs"' in text or '"anyOf"' in text:
        return 'restates the JSON schema'
    return None


def write_instructions(llm_client: OpenAI, user_input: str | None, attempts: int = 2) -> tuple[str, list[dict]]:
    """Ask the model for planner instructions; returns (instructions, attempt log)."""
    log: list[dict] = []
    prompt = meta_prompt(user_input)
    for attempt in range(attempts):
        with llm_step('Write planner instructions (meta)', 'decompose'):
            reply = extract_content(stream_conversation(
                llama_client=llm_client, llm_input=generate_simple_llm_input(prompt)))
        text = clean_instructions(reply)
        problem = valid_instructions(text)
        log.append({'attempt': attempt + 1, 'chars': len(text), 'problem': problem})
        if problem is None:
            return text, log
    raise ValueError(f'meta-prompt instructions unusable after {attempts} attempts: {log[-1]["problem"]}')


class MetaPromptDecomposer(SimpleTaskDecomposer):
    def __init__(
        self,
        llm_client: OpenAI,
        history: dict | None = None,
        prompt_token_budget: int = 16384,
        mode: str = 'frozen',
        instructions_file: str | None = None,
    ):
        super().__init__(llm_client=llm_client, history=history, prompt_token_budget=prompt_token_budget)
        if mode not in ('frozen', 'dynamic'):
            raise ValueError(f'meta_prompt mode must be frozen or dynamic, not {mode!r}')
        self.mode = mode
        self.frozen: str | None = None
        if mode == 'frozen':
            if not instructions_file:
                raise ValueError('frozen meta-prompt decomposition needs options.meta_prompt_file')
            text = clean_instructions(Path(instructions_file).read_text())
            problem = valid_instructions(text)
            if problem:
                raise ValueError(f'{instructions_file}: {problem}')
            self.frozen = text
            self.instructions_file = instructions_file

    def instructions_for(self, user_input: str) -> str:
        if self.frozen is not None:
            self.history['meta_prompt'] = {'mode': 'frozen', 'file': self.instructions_file}
            return self.frozen
        set_phase('Writing planner instructions')
        text, log = write_instructions(self.llm_client, user_input)
        self.history['meta_prompt'] = {'mode': 'dynamic', 'attempts': log, 'instructions': text}
        return text

    def generate_initial_decomposition(
        self, user_input: str, chat_context: str | None = None
    ) -> list[DecomposeItem]:
        conversation_block = CONVERSATION_BLOCK.format(chat_context=chat_context) if chat_context else ''
        prompt = cap_prompt(
            FRAME.format(user_input=user_input, conversation_block=conversation_block,
                         instructions=self.instructions_for(user_input), json_definition=decompose_schema()),
            self.prompt_token_budget,
        )
        self.history['decomposition_prompt'] = prompt
        set_phase('Initial decomposition (JSON)')
        with llm_step('Initial decomposition (JSON)', 'decompose'):
            response = get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=generate_simple_llm_input(prompt),
                response_model=list[DecomposeItem],
            )
        if not isinstance(response, list):
            response = [response]
        self.history['decompose_response'] = TypeAdapter(list[DecomposeItem]).dump_python(response)
        return response
