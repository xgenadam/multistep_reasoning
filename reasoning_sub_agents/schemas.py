from enum import StrEnum
from typing import List, Union, Literal

from openai.types.chat import ChatCompletion, ChatCompletionChunk, \
    ChatCompletionMessage
from pydantic import BaseModel, Field

ChatResponse = Union[
    ChatCompletion, List[ChatCompletionChunk]
]


class TaskNameDependency(BaseModel):
    task_name: str
    dependence_strength: float


class TaskBase(BaseModel):
    name: str
    description: str
    context: str
    complexity: int
    type: str


class DecomposeItem(TaskBase):
    raw_dependencies: list[TaskNameDependency] = Field(default_factory=list)


class BooleanResponse(BaseModel):
    yes: bool


class TaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskDependency(BaseModel):
    task_id: str
    dependence_strength: float


class Task(TaskBase):
    task_id: str
    prompt: ChatCompletionMessage | None = None
    result: ChatResponse | None = None
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[TaskDependency] = Field(default_factory=list)


class LlamaRoles(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LlamaMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


# class LlamaResponseChoices(BaseModel):
#     finish_reason: str
#     index: int
#     logprobs: Any
#     message: LlamaMessage
#
#
# class LlamaUsage(BaseModel):
#     completion_tokens: int
#     prompt_tokens: int
#     total_tokens: int


# class LlamaResponse(BaseModel):
#     choices: list[LlamaResponseChoices]
#     created: int
#     id: str
#     model: str
#     usage: LlamaUsage
#
#     def get_first_response(self) -> str:
#         return self.choices[0].message.content


class DecompositionHistory(BaseModel):
    user_input: str
    decomposition_prompt: str
    decomposition_response: ChatResponse
    initial_tasks: list[Task]


class TaskExecutionResults(BaseModel):
    task_id: str
    task_prompt: ChatResponse
    execution_response: ChatResponse


class TaskSynthesisHistory(BaseModel):
    prompt: str
    result: ChatResponse


class TaskPromptHistory(BaseModel):
    task: Task
    generate_prompt: str
    task_prompt: ChatResponse


class OrchestrationHistory(BaseModel):
    user_input: str
    decomposition_history: DecompositionHistory
    prompt_history: list[TaskPromptHistory]
    execution_results: list[TaskExecutionResults] = []
    synthesis_history: TaskSynthesisHistory


class LLMMessage(BaseModel):
    content: str
    role: Literal["system", "user", "assistant"]


class LLMInput(BaseModel):
    messages: list[LLMMessage]
