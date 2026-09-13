import json
import logging

from openai import OpenAI

from ..document.models import PartOutline
from ..execution_synthesiser.base import ExecutorSynthesiserBase
from ..llama_utils import (
    extract_message,
    generate_simple_llm_input,
    stream_conversation,
)
from ..oracle.document_oracle import DocumentOracle
from ..schemas import AccumulatedResult, SubTask, SubTaskResult, TaskStatus
from .base import ExecutorBase

logger = logging.getLogger()


PROMPT = """
You are an expert sub task execution agent.

This is the relevant context of the task which you are assigned:
================================================================================
{context}
================================================================================

This is your objective:
================================================================================
{objective}
================================================================================
"""

DOCUMENT_CONTEXT = """

A document is being built from prior sub-tasks. You cannot query it.
Use this outline and summary as background only.

Outline:
================================================================================
{outline}
================================================================================

Rolling summary:
================================================================================
{summary}
================================================================================
"""


class SimpleAgentExecutor(ExecutorBase):
    def __init__(self, llm_client: OpenAI, history: list | None = None):
        self.llm_client = llm_client
        self.history = [] if history is None else history

    def execute_one(
        self,
        sub_task: SubTask,
        *,
        outline: list[PartOutline] | None = None,
        summary: str | None = None,
        oracle: DocumentOracle | None = None,
    ) -> SubTask:
        if oracle is not None:
            logger.warning('simple executor ignoring oracle; it cannot query the document')
        prompt_str = PROMPT.format(
            context=sub_task.decomposed_sub_task.context,
            objective=sub_task.decomposed_sub_task.objective,
        )
        if outline is not None:
            prompt_str += DOCUMENT_CONTEXT.format(
                outline=json.dumps([item.model_dump() for item in outline], indent=2),
                summary=summary or '(empty)',
            )
        prompt = generate_simple_llm_input(prompt_str)
        execution_response = stream_conversation(
            llama_client=self.llm_client, llm_input=prompt
        )
        sub_task.sub_task_result = SubTaskResult(
            chat_response=extract_message(execution_response)
        )
        sub_task.status = TaskStatus.COMPLETED
        self.history.append(
            {
                'completed_sub_task': sub_task.model_dump(),
                'full_prompt': prompt_str,
            }
        )
        return sub_task

    def execute_sub_tasks(
        self,
        user_request: str,
        sub_tasks: list[SubTask],
        synthesiser: ExecutorSynthesiserBase,
    ) -> AccumulatedResult:
        accumulated_results: list[AccumulatedResult] = []

        for idx, sub_task in enumerate(sub_tasks):
            logger.info(f'Executing sub task {idx} of {len(sub_tasks)}')
            self.execute_one(sub_task)
            logger.info(
                'completed sub_task %s, result: %s',
                idx,
                sub_task.sub_task_result.chat_response.content
                if sub_task.sub_task_result and sub_task.sub_task_result.chat_response
                else None,
            )
            accumulated_result = synthesiser.synthesize(
                user_request=user_request,
                completed_sub_tasks=sub_tasks[:idx],
                accumulated_results=accumulated_results,
                current_sub_task=sub_task,
                sub_tasks=sub_tasks,
            )
            self.history[-1]['accumulated_result'] = accumulated_result.model_dump()
            logger.info(
                f'completed sub_task {idx}, result: {accumulated_result.chat_response.content}'
            )
            accumulated_result.previous_results = accumulated_results.copy()
            accumulated_results.append(accumulated_result)

        if not accumulated_results:
            raise RuntimeError(
                'something went wrong here, if this gets raised it '
                'means no sub tasks were executed!'
            )

        return accumulated_result
