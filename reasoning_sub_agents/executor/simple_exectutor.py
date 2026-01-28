from copy import deepcopy
import logging

from openai import OpenAI
from ..llama_utils import (
    extract_message,
    generate_simple_llm_input,
    run_multi_concurrent,
    stream_conversation,
)
from ..schemas import SubTask, TaskStatus, AccumulatedResult, SubTaskResult

from .base import ExecutorBase
from ..execution_synthesiser.base import ExecutorSynthesiserBase

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)


ACCUMULATED_PROMPT_PART = '''
'''


PROMPT = '''
You are an expert sub task execution agent.

This is the relevant context of the task which you are assigned:
{context}

This is your objective:
{objective}
'''


class SimpleAgentExecutor(ExecutorBase):
    def __init__(self, llm_client: OpenAI, history: list | None = None):
        self.llm_client = llm_client
        self.history = [] if history is None else history

    def execute_sub_tasks(
            self,
            sub_tasks: list[SubTask],
            synthesiser: ExecutorSynthesiserBase
    ) -> AccumulatedResult:
        accumulated_results: list[AccumulatedResult] = []

        for idx, sub_task in enumerate(sub_tasks):
            prompt = generate_simple_llm_input(PROMPT.format(context=sub_task.decomposed_sub_task.context,
                                   objective=sub_task.decomposed_sub_task.objective))
            execution_response = stream_conversation(llama_client=self.llm_client,
                                                  llm_input=prompt)
            sub_task_result = SubTaskResult(chat_response=extract_message(execution_response))
            sub_task.sub_task_result = sub_task_result
            sub_task.status = TaskStatus.COMPLETED
            accumulated_result = synthesiser.synthesize(
                accumulated_results=accumulated_results,
                current_sub_task=sub_task,
                upcoming_sub_tasks=sub_tasks[idx:],
            )
            accumulated_result.previous_results = accumulated_results.copy()
            accumulated_results.append(accumulated_result)

        # If no sub_tasks were processed, return a default empty result
        if not accumulated_results:
            raise RuntimeError('something went wrong here, if this gets raised it '
                               'means no sub tasks were executed!')

        return accumulated_result
