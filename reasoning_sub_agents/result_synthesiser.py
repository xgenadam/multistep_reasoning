import json

from .schemas import Task, LlamaResponse
from .llama_utils import LlamaRunner

from typing import Iterable


SYNTHESIS_PROMPT = """
### Final Synthesis ###
Original User Request: {user_input}

Completed Subtasks and Results:
{completed_tasks}

**Instructions for Synthesis:**
1. **Thoroughly analyze** all subtask results to identify key findings.
2. **Resolve any contradictions** or inconsistencies between results.
3. **Combine information** from all subtasks to form a comprehensive answer.
4. **Structure the response** logically, highlighting important points.
5. **Ensure completeness** by addressing all aspects of the original request.
6. **Maintain clarity** and conciseness in the final output.

Please provide a well-structured, coherent final answer based on the subtask results.
"""


class ResultSynthesiser:
    def __init__(self, llm: LlamaRunner):
        self.llm = llm

    def synthesise_results(
        self, user_input: str, completed_sub_tasks: Iterable[Task]
    ) -> LlamaResponse:
        completed_sub_task_str = json.dumps(
            [
                task.model_dump(
                    include=[
                        "context",
                        "description",
                        "complexity",
                        "type",
                        "result",
                        "status",
                    ]
                )
                for task in completed_sub_tasks
            ],
            indent=2,
        )
        synthesis_prompt = SYNTHESIS_PROMPT.format(
            user_input=user_input,
            completed_tasks=completed_sub_task_str,
        )
        return self.llm(synthesis_prompt)
