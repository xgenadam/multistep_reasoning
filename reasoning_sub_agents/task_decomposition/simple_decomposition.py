import json
import logging

from openai import OpenAI
from pydantic import TypeAdapter

from ..llama_utils import generate_simple_llm_input, get_streamed_json_response
from ..progress import llm_step, set_phase
from ..prompt_budget import cap_prompt
from ..schemas import DecomposeItem, DecomposeReset, DecomposeSubTask, SubTask
from .base import TaskDecomposerBase

logger = logging.getLogger(__name__)

DECOMPOSE_TASK_PROMPT = """
The user's request is:
================================================================================
{user_input}
================================================================================

{conversation_block}Break THAT request into sub-tasks. Every sub-task name and objective MUST be a step toward this exact request. Do not invent a different topic. Do not follow the climate-website example below as the task — it is only a format illustration.

Output JSON in this schema:
```
{json_definition}
```

Rules:
- The JSON array MUST contain at least one object with meta_type "sub_task_detail".
- Emit sub_task_detail items first. thinking_step is optional; at most one short item.
- Never return only thinking_step / pause / reset items.
- Use 1 sub-task if the request is a single short question or one atomic action.
- Use 2-5 sub-tasks if the request has multiple steps.
- Each sub-task starts with a verb and has a concrete deliverable that still refers to the user's request (names, topic, artefacts they asked for).
- Do not generate tasks about JSON, schemas, or error messages unless the user asked about those.
- Match sub-task deliverables to the requested output shape. If the user asks for a
  code artifact (a script, tool, program), the sub-tasks must PRODUCE that
  artifact (e.g. "Write the wordcount.py script", "Add error handling to the
  script"), not merely design, explain, or summarize around it. If the user
  asks for prose (a report, analysis), sub-task deliverables are prose.

Format illustration only (NOT the user's task):
User query: "Design a website about climate change"
1. Research climate statistics for the site
2. Outline pages
3. Draft homepage copy
"""

CONVERSATION_BLOCK = """
Previous conversation (for context only; fulfil the new user query below):
================================================================================
{chat_context}
================================================================================

"""


def fallback_sub_task(user_input: str) -> SubTask:
    """Single executable task used when decomposition JSON had no sub_task_detail items."""
    text = (user_input or '').strip() or 'Respond to the user request.'
    first_line = text.splitlines()[0].strip()
    name = first_line[:72]
    if len(first_line) > 72:
        name = name.rstrip() + '...'
    if not name:
        name = 'Respond to the request'
    return SubTask(
        decomposed_sub_task=DecomposeSubTask(
            meta_type='sub_task_detail',
            name=name,
            type='writing',
            description='Fallback single task after empty decomposition.',
            context='The decomposer returned no executable sub-tasks.',
            complexity=3,
            objective=text,
        )
    )


def ensure_sub_tasks(user_input: str, sub_tasks: list[SubTask]) -> list[SubTask]:
    if sub_tasks:
        return sub_tasks
    logger.warning(
        'Decomposition produced no executable sub-tasks; using a fallback for %r',
        (user_input or '')[:80],
    )
    return [fallback_sub_task(user_input)]


class SimpleTaskDecomposer(TaskDecomposerBase):
    def __init__(
        self,
        llm_client: OpenAI,
        history: dict | None = None,
        prompt_token_budget: int = 16384,
    ):
        self.llm_client = llm_client
        self.history = {} if history is None else history
        self.prompt_token_budget = prompt_token_budget

    def generate_sub_tasks(
        self, user_input: str, chat_context: str | None = None
    ) -> list[SubTask]:
        self.history['user_input'] = user_input
        self.history['chat_context'] = chat_context
        initial_tasks = self.generate_initial_sub_tasks(
            user_input=user_input, chat_context=chat_context
        )
        return initial_tasks

    def generate_initial_sub_tasks(
        self, user_input: str, chat_context: str | None = None
    ) -> list[SubTask]:
        logger.info('generating initial sub tasks')

        initial_decomposed_tasks = self.generate_initial_decomposition(
            user_input=user_input, chat_context=chat_context
        )
        decomposed_tasks = self.filter_decompose_response(
            decomposition_response=initial_decomposed_tasks
        )
        type_counts: dict[str, int] = {}
        for item in initial_decomposed_tasks:
            key = getattr(item, 'meta_type', type(item).__name__)
            type_counts[str(key)] = type_counts.get(str(key), 0) + 1
        sub_tasks = self.create_sub_tasks(decomposed_tasks)
        logger.info(
            'decomposition items=%s executable=%s types=%s',
            len(initial_decomposed_tasks),
            len(sub_tasks),
            type_counts,
        )
        if not sub_tasks:
            logger.warning(
                'No sub_task_detail items in decomposition JSON (types=%s)',
                type_counts,
            )
            sub_tasks = ensure_sub_tasks(user_input, sub_tasks)
        self.history['initial_tasks'] = TypeAdapter(list[SubTask]).dump_python(
            sub_tasks
        )
        self.history['decomposition_item_types'] = type_counts
        return sub_tasks

    def generate_initial_decomposition(
        self, user_input: str, chat_context: str | None = None
    ) -> list[DecomposeItem]:
        conversation_block = (
            CONVERSATION_BLOCK.format(chat_context=chat_context) if chat_context else ''
        )
        schema = json.dumps(
            TypeAdapter(list[DecomposeItem]).json_schema(), indent=4
        )
        initial_decompose_prompt = cap_prompt(
            DECOMPOSE_TASK_PROMPT.format(
                user_input=user_input,
                conversation_block=conversation_block,
                json_definition=schema,
            ),
            self.prompt_token_budget,
        )
        self.history['decomposition_prompt'] = initial_decompose_prompt
        set_phase('Initial decomposition (JSON)')
        with llm_step('Initial decomposition (JSON)'):
            decompose_response = get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=generate_simple_llm_input(initial_decompose_prompt),
                response_model=list[DecomposeItem],
            )
        # this is a workaround for a known bug where if there is a single item
        # returned, it will not be returned as a list
        # decompose_response = decompose_response.decompose_items
        if not isinstance(decompose_response, list):
            decompose_response = [decompose_response]

        self.history['decompose_response'] = TypeAdapter(
            list[DecomposeItem]
        ).dump_python(decompose_response)
        return decompose_response

    def filter_decompose_response(
        self, decomposition_response: list[DecomposeItem]
    ) -> list[DecomposeSubTask]:
        try:
            last_reset_index = max(
                i
                for i, item in enumerate(decomposition_response)
                if isinstance(item, DecomposeReset)
            )
            items = decomposition_response[last_reset_index + 1 :]
        except ValueError:
            items = decomposition_response
        decompose_tasks = [item for item in items if isinstance(item, DecomposeSubTask)]
        return decompose_tasks

    def create_sub_tasks(
        self, decomposed_sub_tasks: list[DecomposeSubTask]
    ) -> list[SubTask]:
        return [
            SubTask(meta_type='sub_task', decomposed_sub_task=decomposed_sub_task)
            for decomposed_sub_task in decomposed_sub_tasks
        ]
