from typing import Any
from pydantic import BaseModel, field_serializer
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    id: str
    description: str
    context: str
    # ideally int but could be a string if the model is stupid
    complexity: int | str
    type: str
    dependencies: list[str] = []
    prompt: "LlamaResponse | None" = None
    result: "LlamaResponse | None" = None
    status: TaskStatus = TaskStatus.PENDING

    @field_serializer("prompt", "result")
    def serialize_llama(self, value: "LlamaResponse | None") -> str | None:
        if value is None:
            return None
        return value.get_first_response()


class LlamaRoles(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LlamaMessage(BaseModel):
    role: LlamaRoles
    content: str


class LlamaResponseChoices(BaseModel):
    finish_reason: str
    index: int
    logprobs: Any
    message: LlamaMessage


class LlamaUsage(BaseModel):
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int


class LlamaResponse(BaseModel):
    choices: list[LlamaResponseChoices]
    created: int
    id: str
    model: str
    usage: LlamaUsage

    def get_first_response(self) -> str:
        return self.choices[0].message.content


class DecompositionHistory(BaseModel):
    user_input: str
    decomposition_prompt: str
    decomposition_response: LlamaResponse
    initial_tasks: list[Task]


class TaskExecutionResults(BaseModel):
    task_id: str
    task_prompt: LlamaResponse
    execution_response: LlamaResponse


class TaskSynthesisHistory(BaseModel):
    prompt: str
    result: LlamaResponse


class TaskPromptHistory(BaseModel):
    task: Task
    generate_prompt: str
    task_prompt: LlamaResponse



class OrchestrationHistory(BaseModel):
    user_input: str
    decomposition_history: DecompositionHistory
    prompt_history: list[TaskPromptHistory]
    execution_results: list[TaskExecutionResults] = []
    synthesis_history: TaskSynthesisHistory

#
# class SubTaskHistoryItem(BaseModel):
#     prompt: LlamaMessage
#     response: LlamaResponse
#
#
# class SubTaskHistory(BaseModel):
#     history: list[SubTaskHistoryItem]
#     task_id: str
#
#
# class UserQueryHistory(BaseModel):
#     user_query: str | None = None
#     decompose_prompt: str | None = None
#     decompose_response: LlamaResponse | None = None
#     initial_sub_task_histories: list[SubTaskHistory] = []
#     # counter_argument_history
#     # finalised_sub_task_history
