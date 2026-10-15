import json
import logging
from typing import cast

from openai import OpenAI
from pydantic import TypeAdapter

from ..llama_utils import (
    extract_content,
    generate_simple_llm_input,
    get_streamed_json_response,
    limited_inner_tokens,
    stream_conversation,
)
from ..progress import llm_step, set_phase, set_sub_tasks
from ..prompt_budget import cap_prompt
from ..schemas import DecomposeItem, DecomposeReset, DecomposeSubTask, SubTask
from .simple_decomposition import (
    SimpleTaskDecomposer,
    ensure_sub_tasks,
)

logger = logging.getLogger(__name__)

SELF_CRITIQUE_PROMPT = """
You are a critical analyst for task decomposition quality. Analyze the following decomposition against these rules:

1. **Critical Rule**: ANY request requiring more than one logical action must be broken into multiple sub-tasks.
2. **Strong Rule**: Generate between 3-5 sub-tasks for any request with sequential dependencies or multiple types of work (e.g., any request containing 'write', 'create', 'design', 'analyze', or multi-step processes).
3. **Sub-task Quality**: Each sub-task must:
   - Start with an action verb ("Research", "Create", etc.)
   - Have a concrete, verifiable deliverable
   - Be completable in a single LLM response

User Request: {user_input}
Current Decomposition: {sub_tasks}

Return a detailed critique identifying any rule violations. If no violations exist, return "No critique".
"""

DECISION_PROMPT_TEMPLATE = """
Given the user request: {user_input}
Critique summary: {criticism}
Current sub-task count: {subtask_count}

Does the decomposition require regeneration based on the evidence above? 
Answer with true or false.
"""

REVISION_PROMPT = """
You are a task decomposition expert. You previously decomposed the user request but received this critique:
{criticism}
Generate a revised decomposition following these rules:
- For requests requiring multiple logical steps (e.g., containing 'write', 'create', 'design', 'analyze'), generate 3-5 sub-tasks.
- Each sub-task must have an action verb and concrete deliverable.
- Match deliverables to the requested output shape: if the user wants a code
  artifact (script, tool, program), sub-tasks must PRODUCE that artifact, not
  design/explain/summarize around it; if the user wants prose, sub-task
  deliverables are prose.
- If the request has sequential dependencies, ensure proper task ordering.
- The JSON array MUST contain at least one meta_type "sub_task_detail" object.
- Emit sub_task_detail items first. Do not return only thinking_step items.

User request: {user_input}

Previous decomposition results:
```json
{previous_decomposition_results}
```

Output in this format:
```
{json_definition}
```
"""


class SelfCritiquingDecomposition(SimpleTaskDecomposer):
    def generate_sub_tasks(
        self, user_input: str, chat_context: str | None = None
    ) -> list[SubTask]:
        # 1: Generate initial decomposition using parent logic
        set_phase('Initial decomposition')
        initial_sub_tasks = super().generate_sub_tasks(
            user_input=user_input, chat_context=chat_context
        )
        self.history['initial_decomposition_count'] = len(initial_sub_tasks)
        set_sub_tasks(
            [task.decomposed_sub_task.name for task in initial_sub_tasks],
            'queued',
        )

        # 2: Critique the decomposition
        set_phase('Critiquing the decomposition')
        criticism = self.critique_sub_tasks(user_input, initial_sub_tasks)
        self.history['critique'] = criticism
        
        # 3: Determine if regeneration is needed
        logger.info('determining if regeneration is needed')
        set_phase('Deciding whether to regenerate the decomposition')
        regenerate = self.should_regenerate(user_input, criticism, initial_sub_tasks)
        self.history['regeneration_needed'] = regenerate
        
        # 4: Handle regeneration if required
        if regenerate:
            logger.info('Regenerating sub-tasks due to critique')
            set_phase('Regenerating sub-tasks after critique')
            set_sub_tasks(
                [task.decomposed_sub_task.name for task in initial_sub_tasks],
                'rerunning',
            )
            revised = self.regenerate_sub_tasks(user_input, criticism, initial_sub_tasks)
            if not revised:
                logger.warning(
                    'Regeneration produced no executable sub-tasks; keeping initial'
                )
                revised = initial_sub_tasks
            revised = ensure_sub_tasks(user_input, revised)
            set_sub_tasks(
                [task.decomposed_sub_task.name for task in revised],
                'queued',
            )
            return revised
        logger.info('No regeneration needed')

        return ensure_sub_tasks(user_input, initial_sub_tasks)

    def critique_sub_tasks(
        self,
        user_input: str,
        generated_sub_tasks: list[SubTask]
    ) -> str:
        logger.info('Critiquing sub-tasks for decomposition quality')
        
        # Format subtasks for critique
        sub_tasks_str = json.dumps([
            task.decomposed_sub_task.model_dump()
            for task in generated_sub_tasks
        ], indent=4)
        
        critique_prompt = cap_prompt(
            SELF_CRITIQUE_PROMPT.format(
                user_input=user_input,
                sub_tasks=sub_tasks_str
            ),
            self.prompt_token_budget,
        )
        
        with llm_step('Critique decomposition'):
            with limited_inner_tokens(1024):
                critique_response = stream_conversation(
                    llama_client=self.llm_client,
                    llm_input=generate_simple_llm_input(critique_prompt),
                )
        
        return extract_content(critique_response)

    def should_regenerate(
        self,
        user_input: str,
        criticism: str,
        sub_tasks: list[SubTask]
    ) -> bool:
        logger.info('Evaluating need for regeneration')
        
        # Check sub-task count against rules
        subtask_count = len(sub_tasks)
        if subtask_count < 3:
            logger.warning(f'Decomposition has insufficient sub-tasks: {subtask_count} < 3')
            return True
        # Already 3–5 tasks: skip a long boolean LLM call. Only regen if
        # critique is clearly non-empty and not a "no critique" stub.
        stub = (criticism or '').strip().lower()
        if not stub or stub.startswith('no critique') or stub in {'none', 'n/a', 'ok'}:
            return False
        logger.info('Keeping initial decomposition (%s tasks); critique noted but not regenerated', subtask_count)
        return False

    def regenerate_sub_tasks(
        self,
        user_input: str,
        criticism: str,
        initial_sub_tasks: list[SubTask]
    ) -> list[SubTask]:
        logger.info('Regenerating sub-tasks based on critique')
        previous_decomposition_results = json.dumps([
            task.decomposed_sub_task.model_dump()
            for task in initial_sub_tasks
        ], indent=4)
        revised_prompt = cap_prompt(
            REVISION_PROMPT.format(
                user_input=user_input,
                criticism=criticism,
                json_definition=json.dumps(
                    TypeAdapter(list[DecomposeItem]).json_schema(), indent=4
                ),
                previous_decomposition_results=previous_decomposition_results
            ),
            self.prompt_token_budget,
        )
        self.history['regeneration_prompt'] = revised_prompt

        with llm_step('Regenerate decomposition (JSON)'):
            revised_response = get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=generate_simple_llm_input(revised_prompt),
                response_model=list[DecomposeItem],
            )
        # revised_response = revised_response.decompose_items
        if not isinstance(revised_response, list):
            revised_response = [revised_response]
        
        decomposed_tasks = self.filter_decompose_response(revised_response)
        revised = self.create_sub_tasks(decomposed_tasks)
        self.history['regenerated_decomposition_count'] = len(revised)
        self.history['regenerated_sub_tasks'] = TypeAdapter(list[SubTask]).dump_python(
            revised
        )
        logger.info('regenerated %s sub-tasks', len(revised))
        return revised
