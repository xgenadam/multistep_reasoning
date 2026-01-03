from .schemas import Task, LlamaResponse
from .llama_utils import LlamaRunner
import json


GENERATE_SUB_TASK_PROMPT = """
You are an expert prompt generator.
This is the overall task:
{user_input}

which has been broken down into the following subtasks:
{sub_tasks}

This is the sub task that is one step in the completion of the overall task, and the one to focus on: 
{sub_task}

Given this sub task, create an instruction prompt that will then be used to complete the sub task

Rules for creating the instruction prompt:
1. Keep only to the scope of the sub task
2. Provide information relevant to the completion of the sub task
3. if there is ambiguity, highlight this but provide your best guess 
"""


class TaskPromptGenerator:
    def __init__(self, llm: LlamaRunner):
        self.llm = llm

    def generate_sub_task_prompt(
        self, user_input, task: Task, tasks: list[Task]
    ) -> LlamaResponse:
        prompt = GENERATE_SUB_TASK_PROMPT.format(
            user_input=user_input,
            sub_tasks=json.dumps(
                [
                    task.model_dump(
                        include=["description", "context", "type", "complexity"]
                    )
                    for task in tasks
                ]
            ),
            sub_task=json.dumps(
                task.model_dump(
                    include=["description", "context", "type", "complexity"]
                ),
                indent=2,
            ),
        )
        return self.llm(prompt)
