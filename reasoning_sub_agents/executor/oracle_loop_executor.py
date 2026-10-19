import json
import logging

from openai import OpenAI

from ..document.models import PartOutline
from ..execution_synthesiser.base import ExecutorSynthesiserBase
from ..llama_utils import get_streamed_json_response
from ..oracle.document_oracle import DocumentOracle
from ..progress import llm_step
from ..prompt_budget import cap_prompt
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
Original user request (the sub-task MUST serve this; do not switch topic):
================================================================================
{user_request}
================================================================================

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
        prompt_token_budget: int = 16384,
    ) -> None:
        self.llm_client = llm_client
        self.history = [] if history is None else history
        self.max_oracle_rounds = max_oracle_rounds
        self.prompt_token_budget = prompt_token_budget

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
        user_request: str | None = None,
    ) -> SubTask:
        if oracle is None:
            raise TypeError('oracle_loop executor requires a DocumentOracle')
        outline_payload = [item.model_dump() for item in (outline or [])]
        schema = json.dumps(ExecutorTurn.model_json_schema(), indent=2)
        user_prompt = cap_prompt(
            USER_PROMPT.format(
                user_request=user_request or '(not provided)',
                context=sub_task.decomposed_sub_task.context,
                objective=sub_task.decomposed_sub_task.objective,
                outline=json.dumps(outline_payload, indent=2),
                summary=summary or '(empty)',
                json_definition=schema,
            ),
            self.prompt_token_budget,
        )
        messages = [
            LLMMessage(role='system', content=SYSTEM_PROMPT),
            LLMMessage(role='user', content=user_prompt),
        ]
        rounds: list[dict] = []
        for round_idx in range(self.max_oracle_rounds):
            if round_idx == self.max_oracle_rounds - 1:
                messages.append(
                    LLMMessage(
                        role='user',
                        content=(
                            'This is the last allowed turn. Do not call tools. '
                            'Put the best deliverable you can in `result` now, '
                            'even if incomplete, and say what is still missing.'
                        ),
                    )
                )
            with llm_step(
                f'Execute {sub_task.decomposed_sub_task.name} (turn {round_idx + 1})',
                'executor_turn',
            ):
                turn = get_streamed_json_response(
                    llama_client=self.llm_client,
                    llm_input=LLMInput(messages=messages),
                    response_model=ExecutorTurn,
                )
            if turn.tool_calls:
                observation = cap_prompt(
                    oracle.dispatch(turn.tool_calls),
                    self.prompt_token_budget // 4
                    if self.prompt_token_budget > 0
                    else 0,
                )
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
            result_text = (turn.result or '').strip()
            if not result_text:
                logger.warning(
                    'executor turn %s had no tool_calls and empty result; asking again',
                    round_idx,
                )
                rounds.append(
                    {
                        'round': round_idx,
                        'thinking': turn.thinking,
                        'tool_calls': [],
                        'observation': '(empty result; retrying)',
                    }
                )
                messages.append(
                    LLMMessage(role='assistant', content=turn.model_dump_json())
                )
                messages.append(
                    LLMMessage(
                        role='user',
                        content=(
                            'Your previous JSON had no tool_calls and result was '
                            'null/empty. Write the sub-task deliverable now as a '
                            'non-empty string in `result`. Do not wrap it as '
                            '{"result": null}.'
                        ),
                    )
                )
                continue
            sub_task.sub_task_result = SubTaskResult(
                chat_response=_assistant_message(result_text)
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

        fallback = _budget_fallback_text(
            sub_task, rounds, self.max_oracle_rounds
        )
        logger.warning(
            'oracle_loop exhausted %s rounds for %r; using partial fallback',
            self.max_oracle_rounds,
            sub_task.decomposed_sub_task.name,
        )
        sub_task.sub_task_result = SubTaskResult(
            chat_response=_assistant_message(fallback)
        )
        sub_task.status = TaskStatus.COMPLETED
        self.history.append(
            {
                'completed_sub_task': sub_task.model_dump(),
                'oracle_rounds': rounds,
                'full_prompt': user_prompt,
                'budget_exhausted': True,
            }
        )
        return sub_task


def _budget_fallback_text(
    sub_task: SubTask, rounds: list[dict], max_rounds: int
) -> str:
    name = sub_task.decomposed_sub_task.name
    objective = sub_task.decomposed_sub_task.objective
    thinking_bits: list[str] = []
    observations: list[str] = []
    for entry in rounds:
        thinking = (entry.get('thinking') or '').strip()
        if thinking:
            thinking_bits.append(thinking)
        observation = (entry.get('observation') or '').strip()
        if observation and observation != '(empty result; retrying)':
            observations.append(observation)
    parts = [
        f'Partial result for **{name}** (oracle round budget of {max_rounds} reached).',
        '',
        'The executor kept querying tools or returning empty JSON instead of a '
        'finished deliverable. What follows is the best draft from those rounds, '
        'not a complete answer.',
        '',
        f'Objective: {objective}',
    ]
    if thinking_bits:
        parts.extend(['', 'Last working notes:', thinking_bits[-1]])
    if observations:
        excerpt = observations[-1]
        if len(excerpt) > 2000:
            excerpt = excerpt[:2000] + '\n…'
        parts.extend(['', 'Last tool observation:', excerpt])
    if not thinking_bits and not observations:
        parts.extend(
            [
                '',
                'No usable notes were captured. Increase '
                '`options.max_oracle_rounds` or simplify the sub-task.',
            ]
        )
    return '\n'.join(parts)


def _assistant_message(content: str):
    from openai.types.chat import ChatCompletionMessage

    return ChatCompletionMessage(role='assistant', content=content)
