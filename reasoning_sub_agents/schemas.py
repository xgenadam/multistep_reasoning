"""
for reference only
from pydantic import BaseModel, TypeAdapter
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class RootTaskModel(BaseModel):
    id: str
    description: str
    complexity: int | float
    type: str
    context: str


class TaskModel(BaseModel):
    id: str
    description: str
    context: str = ""  # Made optional with default empty string
    complexity: int = 0
    parent: str = ""
    dependencies: list[str] = []
    type: str
    status: TaskStatus = TaskStatus.PENDING
"""

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
    complexity: str
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
