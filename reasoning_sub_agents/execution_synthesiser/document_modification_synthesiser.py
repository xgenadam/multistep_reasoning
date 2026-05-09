from pydantic import TypeAdapter
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
import json

from ..llama_utils import generate_simple_llm_input, stream_conversation, \
    extract_message, get_streamed_json_response
from ..schemas import AccumulatedResult, SubTask, ToolCall
from .base import ExecutorSynthesiserBase
from .synthesis_tools import AppendResult, WriteResult, ReplacePartResult, SynthesisPlanning, SynthesisReset, DocumentSynthesisItems

import logging

logger = logging.getLogger()



PREVIOUS_RESULT_SUB_PROMPT = """

Of these sub tasks, the following have been completed:
================================================================================
{completed_sub_tasks}
================================================================================

The previous result has likely gone through a rolling synthesis that will happen here, with the result being updated after completion of each sub task
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
3. Ensure that what you return is does not leave out key information. For instance, if the user asks for all of the code to be returned do not omit information referenced by other information.
4. The aim is to build as complete a response from the previous and current sub tasks as possible. They are intermediary steps, and the output of this will be fed into following results as an intermediate step, however the output here should contain all information relevant to achieve completion of the combination of future sub tasks with the output produced here   
5. It is important to understand that this is part of a rolling combination process. Where a sub task is completed, the combined previous results are fed into this prompt, with the results of the most recently completed sub task. This means that the output here should be as complete as possible, with respect to the accumulated result and the current result, to complete the user request.

How to combine: 
This is a the json format of items you MUST output:
```
{json_tool_definition}
```
These represent the tools available to you to update the previous result with the current result
"""


class RollingDocumentUpdateSynthesiser(ExecutorSynthesiserBase):
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
        """
        A brief explanation of how this synthesiser aims to work.
        This is being written before code, and may need to be updated to reflect later changes.
        The core idea:
            * Treat the accumulated result as a document that we can edit (only in the abstract, we actually want to create a new `AccumulatedResult` instance when we call this
            * the synthesiser will have access to two tools:
                * find_and_replace
                * full_write
            * find_and_replace
                * this tool requires two arguments:
                    * target
                        * exact match of text in the document, only affects the first instance
                        * if no matches, fail and log?
                            * maybe force a regeneration up to n times?
                    * replacement
                        * text to replace target with
            * full_write
                * should be used for new documents?
                * prompt should specify that it is only to be used when document is small, or there is a very good reason
        """
        logger.info(f'sythesizing {current_sub_task.model_dump()}')
        sub_tasks_str = json.dumps(
            [sub_task.decomposed_sub_task.model_dump() for sub_task in sub_tasks])
        completed_sub_tasks_str = json.dumps(
            [sub_task.decomposed_sub_task.model_dump() for sub_task in
             completed_sub_tasks])
        try:
            previous_result = accumulated_results[-1]
            previous_result_str = PREVIOUS_RESULT_SUB_PROMPT.format(
                previous_result=previous_result.chat_response.content,
                completed_sub_tasks=completed_sub_tasks_str,
            )
        except IndexError:
            previous_result = None
            previous_result_str = ''
        prompt_str = PROMPT.format(
            user_request=user_request,
            sub_tasks=sub_tasks_str,
            previous_result_sub_prompt=previous_result_str,
            current_sub_task=current_sub_task.model_dump(),
            current_result=current_sub_task.sub_task_result.chat_response.content,
            json_tool_definition=json.dumps(
                TypeAdapter(list[DocumentSynthesisItems]).json_schema(), indent=4
            )
        )
        prompt = generate_simple_llm_input(prompt_str)
        synthesis_response = get_streamed_json_response(llama_client=self.llm_client,
                                               llm_input=prompt)
        history = {'synthesis_response': TypeAdapter(list[DocumentSynthesisItems]).dump_python(synthesis_response)}
        synthesis_result = self.filter_synthesis_response(synthesis_response)
        if not synthesis_result:
            logger.warning('no synthesis results! something has probably gone wrong!')
        accumulated_result_text = previous_result.chat_response.content if previous_result else ''
        if not previous_result:
            accumulated_result = AccumulatedResult(
                    previous_results=accumulated_results,
                    current_task=current_sub_task,
                    synthesis_prompt=prompt_str,
                    chat_response=ChatCompletionMessage(content=previous_result_str,
                                                        role='assistant'),
                )
        for operation in synthesis_result:
            # TODO: modify the `AccumulatedResult` pydantic model such that it
            #  contains a raw result or something instead of `chat_response`
            #  because we don't use a chat response here
            raw_text = accumulated_result.chat_response.content
            if isinstance(operation, WriteResult):
                logger.info('overwritting text')
                raw_text = operation.text
            elif isinstance(operation, ReplacePartResult):
                logger.info('replacing text')
                if not operation.text_to_replace in raw_text:
                    logger.warning(f'tried to replace {operation.text_to_replace} '
                                   f'in {raw_text} but it was not found!')
                raw_text = raw_text.replace(operation.text_to_replace, operation.text)
            elif isinstance(operation, AppendResult):
                raw_text = f'{raw_text}{operation.text}'

            accumulated_result = AccumulatedResult(
                previous_results=accumulated_results,
                current_task=current_sub_task,
                synthesis_prompt=prompt_str,
                chat_response=ChatCompletionMessage(content=raw_text,
                                                    role='assistant'),
            )

        history['accumulated_result'] = accumulated_result.model_dump()
        self.history.append(history)
        logger.debug(f'completed synthesis')
        return accumulated_result


    def filter_synthesis_response(self, synthesis_response) ->list[WriteResult | ReplacePartResult | AppendResult]:
        try:
            last_reset_index = max(
                i
                for i, item in enumerate(synthesis_response)
                if isinstance(item, SynthesisReset)
            )
            items = synthesis_response[last_reset_index + 1 :]
        except ValueError:
            items = synthesis_response
        decompose_tasks = [item for item in items
                           if isinstance(item, WriteResult)
                           or isinstance(item, ReplacePartResult)
                           or isinstance(item, AppendResult)]
        for idx, item in enumerate(decompose_tasks[1:]):
            if isinstance(item, WriteResult):
                logger.warning(f'idx {idx+1} of synthesis should not have been a full write but was!')
        return decompose_tasks