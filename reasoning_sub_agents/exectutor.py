from .schemas import Task, TaskStatus
from .llama_utils import LlamaRunner


class AgentExecutor:
    def __init__(self, llm: LlamaRunner):
        self.llm = llm

    def execute_sub_tasks(
        self, sub_tasks: list[Task]
    ) -> list[Task]:
        completed_tasks = {}
        uncompleted_tasks = {
            task.id: task for task in sub_tasks
        }
        while uncompleted_tasks:
            # get tasks without completed dependencies
            ready_tasks = self.get_agents_without_remaining_dependencies(
                uncompleted_tasks=uncompleted_tasks,
                completed_task_ids=set(completed_tasks.keys()),
            )
            for task_id, task in ready_tasks.items():
                task.result = self.llm(task.prompt.get_first_response())
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
