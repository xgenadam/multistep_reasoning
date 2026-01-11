import logging

from .llama_utils import generate_simple_llm_input, \
    run_multi_concurrent, stream_conversation, extract_message
from .schemas import Task, TaskStatus, LLMInput

from openai import OpenAI

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)


class AgentExecutor:
    def __init__(self, llm_client: OpenAI, history: list | None = None):
        self.llm_client = llm_client
        self.history = [] if history is None else history

    def execute_sub_tasks(self, sub_tasks: list[Task]) -> list[Task]:
        completed_tasks = {}
        uncompleted_tasks = {task.task_id: task for task in sub_tasks}
        logger.debug("executing sub tasks")
        while uncompleted_tasks:
            # get tasks without completed dependencies
            ready_tasks = self.get_agents_without_remaining_dependencies(
                uncompleted_tasks=uncompleted_tasks,
                completed_task_ids=set(completed_tasks.keys()),
            )
            llm_inputs: dict[str, LLMInput] = {
                task_id: generate_simple_llm_input(task.prompt.content)
                for task_id, task in ready_tasks.items()
            }
            logger.debug("starting tasks: %s", llm_inputs.keys())
            response = run_multi_concurrent(
                llama_client=self.llm_client,
                llm_inputs=llm_inputs,
                processor=stream_conversation
            )
            logger.debug("completed tasks: %s", llm_inputs.keys())
            for task_id, chat_completion in response.items():
                result = extract_message(response=chat_completion)
                task = ready_tasks[task_id]
                task.result = result
                self.history.append(
                    {
                        "task": task.model_dump(),
                        "generate_prompt": task.prompt.model_dump(),
                        "execution_response": task.result.model_dump(),
                    }
                )
                task.status = TaskStatus.COMPLETED
                completed_tasks[task_id] = task
                uncompleted_tasks.pop(task_id)
        return list(completed_tasks.values())

    def get_agents_without_remaining_dependencies(
        self,
        uncompleted_tasks: dict[str, Task],
        completed_task_ids: set[str],
    ) -> dict[str, Task]:
        return {
            task_id: task
            for task_id, task in uncompleted_tasks.items()
            if not set([dependency.task_id for dependency in task.dependencies]) - completed_task_ids
        }
