from .schemas import Task, TaskStatus
from .llama_utils import LlamaRunner

import logging

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)


class AgentExecutor:
    def __init__(self, llm: LlamaRunner, history: list | None = None):
        self.llm = llm
        self.history = [] if history is None else history

    def execute_sub_tasks(
            self, sub_tasks: list[Task]
    ) -> list[Task]:
        completed_tasks = {}
        uncompleted_tasks = {
            task.id: task for task in sub_tasks
        }
        logger.debug(f"executing sub tasks")
        while uncompleted_tasks:
            # get tasks without completed dependencies
            ready_tasks = self.get_agents_without_remaining_dependencies(
                uncompleted_tasks=uncompleted_tasks,
                completed_task_ids=set(completed_tasks.keys()),
            )
            for task_id, task in ready_tasks.items():
                logger.debug('starting task: %s', task_id)
                task.result = self.llm(task.prompt.get_first_response())
                self.history.append(
                    {
                        'task': task.model_dump(),
                        'generate_prompt': task.prompt.model_dump(),
                        'execution_response': task.result.model_dump(),
                    }
                )
                logger.debug('executed task: %s', task_id)
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
            if not set(task.dependencies) - completed_task_ids
        }
