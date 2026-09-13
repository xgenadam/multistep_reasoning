import json
import logging

from openai import OpenAI

from ..document.models import PartOutline
from ..execution_synthesiser.base import ExecutorSynthesiserBase
from ..llama_utils import get_streamed_json_response
from ..oracle.document_oracle import DocumentOracle
from ..oracle.tools import ExecutorTurn
from ..schemas import (
    AccumulatedResult,
    LLMInput,
    LLMMessage,
    SubTask,
    SubTaskResult,
    TaskStatus,
)
from .base import ExecutorBase

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert sub-task execution agent.
A document is being built from prior sub-tasks. You are given an outline and a
rolling summary. You may query the document with tools, then produce your result.

Rules:
1. Use tools when you need a concrete detail from the document.
2. Prefer list_parts / read_part / search when you know where to look.
3. Use ask only when you do not know which part holds the answer.
4. When you are ready, return a final `result` and no tool_calls.
5. Your result is the deliverable for THIS sub-task only, not the whole document.
"""

USER_PROMPT = """
This is the relevant context of the task which you are assigned:
================================================================================
{context}
================================================================================

This is your objective:
================================================================================
{objective}
================================================================================

Document outline:
================================================================================
{outline}
================================================================================

Rolling summary:
================================================================================
{summary}
================================================================================

Tool JSON schema (respond as ExecutorTurn):
```
{json_definition}
```
"""


class OracleLoopExecutor(ExecutorBase):
    def __init__(
        self,
        llm_client: OpenAI,
        history: list | None = None,
        max_oracle_rounds: int = 8,
    ) -> None:
        self.llm_client = llm_client
        self.history = [] if history is None else history
        self.max_oracle_rounds = max_oracle_rounds

    def execute_sub_tasks(
        self,
        user_request: str,
        sub_tasks: list[SubTask],
        synthesiser: ExecutorSynthesiserBase,
    ) -> AccumulatedResult:
        raise TypeError(
            'oracle_loop executor cannot be used with execute_sub_tasks; '
            'use TaskOrchestrator document pipeline'
        )

    def execute_one(
        self,
        sub_task: SubTask,
        *,
        outline: list[PartOutline] | None = None,
        summary: str | None = None,
        oracle: DocumentOracle | None = None,
    ) -> SubTask:
        if oracle is None:
            raise TypeError('oracle_loop executor requires a DocumentOracle')
        outline_payload = [item.model_dump() for item in (outline or [])]
        user_prompt = USER_PROMPT.format(
            context=sub_task.decomposed_sub_task.context,
            objective=sub_task.decomposed_sub_task.objective,
            outline=json.dumps(outline_payload, indent=2),
            summary=summary or '(empty)',
            json_definition=json.dumps(ExecutorTurn.model_json_schema(), indent=2),
        )
        messages = [
            LLMMessage(role='system', content=SYSTEM_PROMPT),
            LLMMessage(role='user', content=user_prompt),
        ]
        rounds: list[dict] = []
        for round_idx in range(self.max_oracle_rounds):
            turn = get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=LLMInput(messages=messages),
                response_model=ExecutorTurn,
            )
            if turn.tool_calls:
                observation = oracle.dispatch(turn.tool_calls)
                rounds.append(
                    {
                        'round': round_idx,
                        'thinking': turn.thinking,
                        'tool_calls': [tool.model_dump() for tool in turn.tool_calls],
                        'observation': observation,
                    }
                )
                messages.append(
                    LLMMessage(role='assistant', content=turn.model_dump_json())
                )
                messages.append(
                    LLMMessage(
                        role='user',
                        content='Tool results:\n' + observation,
                    )
                )
                continue
            sub_task.sub_task_result = SubTaskResult(
                chat_response=_assistant_message(turn.result or '')
            )
            sub_task.status = TaskStatus.COMPLETED
            self.history.append(
                {
                    'completed_sub_task': sub_task.model_dump(),
                    'oracle_rounds': rounds,
                    'full_prompt': user_prompt,
                }
            )
            return sub_task

        raise RuntimeError(
            f'oracle_loop executor exceeded {self.max_oracle_rounds} rounds '
            f'without producing a result for {sub_task.decomposed_sub_task.name!r}'
        )


def _assistant_message(content: str):
    from openai.types.chat import ChatCompletionMessage

    return ChatCompletionMessage(role='assistant', content=content)
