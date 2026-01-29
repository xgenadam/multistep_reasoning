import json
import logging

from openai import OpenAI
from pydantic import TypeAdapter

from ..llama_utils import generate_simple_llm_input, get_streamed_json_response
from ..schemas import DecomposeItem, DecomposeReset, DecomposeSubTask, SubTask
from .base import TaskDecomposerBase

logger = logging.getLogger(__name__)

DECOMPOSE_TASK_PROMPT = """
You are a world-class task decomposition expert with perfect intuition for breaking complex requests into atomic sub-tasks.
This is the json format you MUST output (always as a list):
```
{json_definition}
```

For the following user query, generate 3-5 sub-tasks that completely fulfill the request when combined.
**CRITICAL INSTRUCTION:** ANY request requiring more than one logical action must be broken into multiple sub-tasks. 
**EXAMPLE TRIGGERS (MUST DECOMPOSE ANY TIME THESE OR SIMILAR PATTERNS APPEAR):**
- Any request containing 'write', 'create', 'design', 'analyze', 'guide me'
- Any multi-step process (e.g., 'Plan an event: research venues first, then budget, then schedule')
- Any request requiring different types of work (research → writing → synthesis)

**STRONG DECOMPOSITION RULES:**
1. FOR ANY request with sequential dependencies, generate between 3-5 sub-tasks
2. Each sub-task must:
   - Start with an action verb ("Research", "Create", "Validate", etc.)
   - Have a concrete, verifiable deliverable (e.g., "Draft of report introduction")
   - Be completable in a single LLM response
3. IMPOSSIBLE EXCEPTION: You may only return a single sub-task if:
   - The request is a straightforward factual question with a definitive yes/no answer
   - The task can literally be completed in under 30 words of context

**ILLUSTRATIVE EXAMPLE:**
User query: "Design a website about climate change"
Sub-tasks:
1. Research key climate change statistics and impacts
2. Outline website structure including home, about, and resources pages
3. Draft homepage content incorporating researched statistics
4. Create wireframe for website layout visuals

**PROOF:**
If your response has fewer than 3 sub-tasks but involves more than one logical stage, you have failed this critical instruction.

This is the user query:
{user_input}
"""


class SimpleTaskDecomposer(TaskDecomposerBase):
    def __init__(
        self,
        llm_client: OpenAI,
        history: dict | None = None,
    ):
        self.llm_client = llm_client
        self.history = {} if history is None else history

    def generate_sub_tasks(self, user_input: str) -> list[SubTask]:
        # given user input
        #  1. break down into relevant subtasks, with only relevant context
        #  2. run devil's advocate on the subtasks, find any potential issues in
        #     subtasks
        #  3. given the results from 1 and 2, generate refined subtasks
        self.history['user_input'] = user_input
        initial_tasks = self.generate_initial_sub_tasks(user_input=user_input)
        # TODO: steps 2-3
        return initial_tasks

    def generate_initial_sub_tasks(self, user_input: str) -> list[SubTask]:
        logger.info('generating initial sub tasks')

        initial_decomposed_tasks = self.generate_initial_decomposition(
            user_input=user_input
        )
        decomposed_tasks = self.filter_decompose_response(
            decomposition_response=initial_decomposed_tasks
        )
        sub_tasks = self.create_sub_tasks(decomposed_tasks)
        logger.info(f'generated {len(sub_tasks)} sub tasks')
        self.history['initial_tasks'] = TypeAdapter(list[SubTask]).dump_python(
            sub_tasks
        )
        return sub_tasks

    def generate_initial_decomposition(self, user_input: str) -> list[DecomposeItem]:
        initial_decompose_prompt = DECOMPOSE_TASK_PROMPT.format(
            user_input=user_input,
            json_definition=json.dumps(
                TypeAdapter(list[DecomposeItem]).json_schema(), indent=4
            ),
        )
        self.history['decomposition_prompt'] = initial_decompose_prompt
        decompose_response = get_streamed_json_response(
            llama_client=self.llm_client,
            llm_input=generate_simple_llm_input(initial_decompose_prompt),
            response_model=list[DecomposeItem],
        )
        # this is a workaround for a known bug where if there is a single item
        # returned, it will not be returned as a list
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
