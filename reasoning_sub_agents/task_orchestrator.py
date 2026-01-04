import logging
from typing import Self

from llama_cpp import Llama

from .boolean_decider import BooleanDecider
from .exectutor import AgentExecutor
from .llama_utils import llama_container
from .prompt_generator import TaskPromptGenerator
from .result_synthesiser import ResultSynthesiser
from .schemas import LlamaResponse, Task
from .task_decomposition import TaskDecomposer

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    def __init__(
        self,
        decomposer: TaskDecomposer,
        task_prompt_generator: TaskPromptGenerator,
        agent_executor: AgentExecutor,
        result_synthesiser: ResultSynthesiser,
        boolean_decider: BooleanDecider,
        llm: Llama,
        history: list | None = None,
    ):
        self.decomposer = decomposer
        self.task_prompt_generator = task_prompt_generator
        self.agent_executor = agent_executor
        self.result_synthesiser = result_synthesiser
        self.boolean_decider = boolean_decider
        self.llm = llm
        self.history = [] if history is None else history

    def query(
        self, user_input: str, return_sub_tasks: bool = False
    ) -> LlamaResponse | tuple[LlamaResponse, list[Task]]:
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
        #     access to the history, the context they need should be part of the prompt
        #  5. execute all subtasks
        #  6. given the output of all subtasks aggregate the result

        # decomposer handles steps 1-3
        # TODO: just to get running the decomposer is currently only doing step 1
        sub_tasks = self.decomposer.generate_sub_tasks(user_input)

        # step 4
        logger.debug(f"generating sub task prompts for {len(sub_tasks)} tasks")
        for sub_task in sub_tasks:
            sub_task.prompt = self.task_prompt_generator.generate_sub_task_prompt(
                user_input=user_input, task=sub_task, tasks=sub_tasks
            )

        # step 5
        logger.debug("executing sub tasks")
        sub_task_execution_results = self.agent_executor.execute_sub_tasks(
            sub_tasks=sub_tasks
        )

        # step 6
        synthesised_results = self.result_synthesiser.synthesise_results(
            user_input, sub_task_execution_results
        )
        self.history.append(
            {
                "user_input": user_input,
                "decomposition_history": self.decomposer.history,
                "prompt_history": self.task_prompt_generator.history,
                "execution_results": self.agent_executor.history,
                "synthesis_history": self.result_synthesiser.history,
            }
        )
        if return_sub_tasks:
            return (synthesised_results, sub_task_execution_results)
        return synthesised_results

    @classmethod
    def instantiate(cls, config: dict) -> Self:
        reasoning_config = config["reasoning_model"]
        binary_decision_config = config["binary_decision_model"]
        llm = Llama(**reasoning_config)
        llama_runner = llama_container(llm=llm)
        boolean_decider = BooleanDecider(binary_decision_config["model_path"])
        decomposer = TaskDecomposer(llm=llama_runner, boolean_decider=boolean_decider)
        task_prompt_generator = TaskPromptGenerator(llm=llama_runner)
        agent_executor = AgentExecutor(llm=llama_runner)
        result_synthesiser = ResultSynthesiser(llm=llama_runner)
        return cls(
            decomposer=decomposer,
            task_prompt_generator=task_prompt_generator,
            agent_executor=agent_executor,
            result_synthesiser=result_synthesiser,
            boolean_decider=boolean_decider,
            llm=llm,
        )
