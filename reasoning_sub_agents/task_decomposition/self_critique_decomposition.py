import json
import logging
from typing import cast

from openai import OpenAI
from pydantic import TypeAdapter

from ..llama_utils import generate_simple_llm_input, get_streamed_json_response, get_streamed_boolean_decision, extract_content, stream_conversation
from ..schemas import DecomposeItem, DecomposeReset, DecomposeSubTask, SubTask
from .simple_decomposition import SimpleTaskDecomposer

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
- If the request has sequential dependencies, ensure proper task ordering.

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
        initial_sub_tasks = super().generate_sub_tasks(
            user_input=user_input, chat_context=chat_context
        )
        self.history['initial_decomposition_count'] = len(initial_sub_tasks)
        
        # 2: Critique the decomposition
        criticism = self.critique_sub_tasks(user_input, initial_sub_tasks)
        self.history['critique'] = criticism
        
        # 3: Determine if regeneration is needed
        logger.info('determining if regeneration is needed')
        regenerate = self.should_regenerate(user_input, criticism, initial_sub_tasks)
        self.history['regeneration_needed'] = regenerate
        
        # 4: Handle regeneration if required
        if regenerate:
            logger.info('Regenerating sub-tasks due to critique')
            return self.regenerate_sub_tasks(user_input, criticism, initial_sub_tasks)
        logger.info('No regeneration needed')

        return initial_sub_tasks

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
        
        critique_prompt = SELF_CRITIQUE_PROMPT.format(
            user_input=user_input,
            sub_tasks=sub_tasks_str
        )
        
        # Request critique from LLM
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
            
        # Use LLM decision only when critique is ambiguous
        decision_prompt = DECISION_PROMPT_TEMPLATE.format(
            user_input=user_input,
            criticism=criticism,
            subtask_count=subtask_count
        )
        
        return get_streamed_boolean_decision(
            llama_client=self.llm_client,
            llm_input=generate_simple_llm_input(decision_prompt)
        )

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
        revised_prompt = REVISION_PROMPT.format(
            user_input=user_input,
            criticism=criticism,
            json_definition=json.dumps(
                TypeAdapter(list[DecomposeItem]).json_schema(), indent=4
            ),
            previous_decomposition_results=previous_decomposition_results
        )
        self.history['regeneration_prompt'] = revised_prompt

        revised_response = get_streamed_json_response(
            llama_client=self.llm_client,
            llm_input=generate_simple_llm_input(revised_prompt),
            response_model=list[DecomposeItem],
        )
        # revised_response = revised_response.decompose_items
        if not isinstance(revised_response, list):
            revised_response = [revised_response]
        
        decomposed_tasks = self.filter_decompose_response(revised_response)
        self.history['regenerated_decomposition_count'] = len(decomposed_tasks)
        self.history['regenerated_sub_tasks'] =  TypeAdapter(list[SubTask]).dump_python(
            decomposed_tasks
        )
        logger.info(f'regenerated {len(decomposed_tasks)} sub-tasks')
        return self.create_sub_tasks(decomposed_tasks)
