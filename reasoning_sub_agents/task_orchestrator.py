import logging
from typing import Self

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from .llama_utils import create_llama_client
from .schemas import AccumulatedResult
from .task_decomposition import TaskDecomposer
from .execution_synthesiser.base import ExecutorSynthesiserBase
from .execution_synthesiser.simple_synthesiser import SimpleSynthesiser
from .executor.base import ExecutorBase
from .executor.simple_exectutor import SimpleAgentExecutor

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    def __init__(
        self,
        decomposer: TaskDecomposer,
        agent_executor: ExecutorBase,
        result_synthesiser: ExecutorSynthesiserBase,
        llm_client: OpenAI,
        history: list | None = None,
    ):
        self.decomposer = decomposer
        self.agent_executor = agent_executor
        self.result_synthesiser = result_synthesiser
        self.llm_client = llm_client
        self.history = [] if history is None else history

    def query(
        self, user_input: str, return_sub_tasks: bool = False
    ) -> ChatCompletionMessage | tuple[ChatCompletionMessage, AccumulatedResult]:
        # this is our entrypoint post initialization
        # user input should be the most recent user input
        # history is still TBD regarding structure, but the current assumption
        # is that it will contain the conversation history and sub agent history

        # over should do the following
        # given user input
        #  1. break down into relevant subtasks, with only relevant context
        #  2. run devil's advocate on the subtasks, find any potential issues in
        #     subtasks
        #  3. given the results from 1 and 2, generate refined subtasks
        #  4. should then build prompts for each subtask, subtasks should not have
        #     access to the history, the context they need should be part of the objective
        #     Note: currently the objective is being handled as part of step 1, this is
        #     subject to change
        #  5. execute all subtasks
        #  6. given the output of all subtasks aggregate the result

        # decomposer handles steps 1-3
        # TODO: just to get running the decomposer is currently only doing step 1
        sub_tasks = self.decomposer.generate_sub_tasks(user_input)

        logger.debug('executing sub tasks')
        sub_task_execution_result = self.agent_executor.execute_sub_tasks(
            user_request=user_input,
            sub_tasks=sub_tasks,
            synthesiser=self.result_synthesiser,
        )

        self.history.append(
            {
                'user_input': user_input,
                'decomposition_history': self.decomposer.history,
                'execution_results': self.agent_executor.history,
                'synthesis_history': self.result_synthesiser.history,
            }
        )
        if return_sub_tasks:
            return sub_task_execution_result.chat_response, sub_task_execution_result
        return sub_task_execution_result.chat_response

    @classmethod
    def instantiate(
        cls, *, config: dict | None = None, llm_client: OpenAI | None = None
    ) -> Self:
        if config is None and llm_client is None:
            raise ValueError('Neither config nor llm_client provided')
        if config and llm_client:
            raise ValueError('Cannot provide both config and llm_client')
        if config:
            llm_client = create_llama_client(config)
        decomposer = TaskDecomposer(llm_client=llm_client)
        agent_executor = SimpleAgentExecutor(llm_client=llm_client)
        result_synthesiser = SimpleSynthesiser(llm_client=llm_client)
        return cls(
            decomposer=decomposer,
            agent_executor=agent_executor,
            result_synthesiser=result_synthesiser,
            llm_client=llm_client,
        )
