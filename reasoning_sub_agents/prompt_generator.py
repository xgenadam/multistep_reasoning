import json
import logging

from openai import OpenAI
from .llama_utils import ChatResponse, generate_simple_llm_input, stream_conversation, run_multi_concurrent, extract_content
from .schemas import Task

logger = logging.getLogger(__name__)

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
    def __init__(self, llm_client: OpenAI, history: list | None = None):
        self.llm_client = llm_client
        self.history = [] if history is None else history

    def generate_sub_task_prompt(
        self, user_input, tasks: list[Task]
    ) -> dict[str, ChatResponse]:
        llm_inputs = {}
        for task in tasks:
            prompt = GENERATE_SUB_TASK_PROMPT.format(
                user_input=user_input,
                sub_tasks=json.dumps(
                    [
                        task.model_dump(
                            include=["description", "context", "type", "complexity"]
                        )
                        for task in tasks
                    ],
                    indent=4
                ),
                sub_task=json.dumps(
                    task.model_dump(
                        include=["description", "context", "type", "complexity"]
                    ),
                    indent=4,
                ),
            )
            llm_inputs[task.task_id] = generate_simple_llm_input(prompt)
        logger.debug("generating prompts for tasks")
        responses = run_multi_concurrent(
            llama_client=self.llm_client,
            llm_inputs=llm_inputs,
            processor=stream_conversation
        )
        for task_id, response in responses.items():
            self.history.append(
                {
                    "task": task.model_dump(),
                    "prompt": llm_inputs[task_id].model_dump(),
                    "task_prompt": extract_content(response),
                }
            )
        logger.debug("generated prompts for tasks")
        return responses
