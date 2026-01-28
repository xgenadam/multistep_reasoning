from pydantic import TypeAdapter
from openai import OpenAI
import json

from ..llama_utils import generate_simple_llm_input, stream_conversation, \
    extract_message
from ..schemas import AccumulatedResult, SubTask
from .base import ExecutorSynthesiserBase

import logging

logger = logging.getLogger()

PREVIOUS_RESULT_SUB_PROMPT = """

Of these sub tasks, the following have been completed:
================================================================================
{completed_sub_tasks}
================================================================================

The previous result has likely gone through a rolling synthesis that will happen here, and is an accumulation of sub task results prior to that step, and the sub task of that step.
This is the previous result:
================================================================================
{previous_result}
================================================================================

"""

PROMPT = """
You are an expert task synthesiser.
You take the results of a sub task, and the results of previous sub tasks, and combine the results such that the original user request is fulfilled.

This is the original user request:
================================================================================
{user_request}
================================================================================

This request has been broken down into these sub tasks:
================================================================================
{sub_tasks}
================================================================================
{previous_result_sub_prompt}
This is the current sub task:
================================================================================
{current_sub_task}
================================================================================

This is the current result:
================================================================================
{current_result}
================================================================================

Combine the current results, with the previous results.
Rules for combining previous results:
1. The users request has been broken down into sub tasks, as this is part of a larger flow, only the parts of the user request relevant to the current task and completed sub tasks need to be taken into consideration
2. It is possible for there to be no previous results, this would indicate that this is the first sub task. In such a case it is fine to just return the output of the current sub task unchanged
3. Ensure that what you return is does not leave out key information. For instance, if the user asks for all of the code to be returned do not ommit information referenced by other information.
4. The aim is to build as complete a response from the previous and current sub tasks as possible. They are intermediary steps, and the output of this will be fed into following results as an intermediate step, however the output here should contain all information relevant to achieve completion of the combination of future sub tasks with the output produced here   
5. It is important to understand that this is part of a rolling combination process. Where a sub task is completed, the combined previous results are fed into this prompt, with the results of the most recently completed sub task. This means that the output here should be as complete as possible, with respect to the accumulated result and the current result, to complete the user request. 
"""


class SimpleSynthesiser(ExecutorSynthesiserBase):
    def __init__(self, llm_client: OpenAI, history: list | None = None, exclude_individual_sub_task_results: bool = True):
        self.llm_client = llm_client
        self.history = history if history is not None else []
        self.exclude_individual_sub_task_results = exclude_individual_sub_task_results

    def synthesize(
        self,
        user_request: str,
        completed_sub_tasks: list[SubTask],
        accumulated_results: list[AccumulatedResult],
        current_sub_task: SubTask,
        sub_tasks: list[SubTask],
    ) -> AccumulatedResult:
        logger.debug(f'sythesizing {current_sub_task.model_dump()}')
        sub_tasks_str = json.dumps([sub_task.decomposed_sub_task.model_dump() for sub_task in sub_tasks])
        completed_sub_tasks_str = json.dumps([sub_task.decomposed_sub_task.model_dump() for sub_task in completed_sub_tasks])
        try:
            previous_result_str = PREVIOUS_RESULT_SUB_PROMPT.format(
                previous_result=accumulated_results[-1].chat_response.content,
                completed_sub_tasks=completed_sub_tasks_str,
            )
        except IndexError:
            previous_result_str = ''
        prompt_str = PROMPT.format(
            user_request=user_request,
            sub_tasks=sub_tasks_str,
            previous_result_sub_prompt=previous_result_str,
            current_sub_task=current_sub_task.model_dump(),
            current_result=current_sub_task.sub_task_result.chat_response.content,
        )
        prompt = generate_simple_llm_input(prompt_str)
        synthesis_result = stream_conversation(llama_client=self.llm_client, llm_input=prompt)
        synthesis_result = extract_message(synthesis_result)
        accumulated_result = AccumulatedResult(
            previous_results=accumulated_results,
            current_task=current_sub_task,
            synthesis_prompt=prompt_str,
            chat_response=synthesis_result,
        )
        self.history.append(accumulated_result.model_dump())
        logger.debug(f'completed synthesis')
        return accumulated_result