from enum import StrEnum
from typing import Annotated, Literal, Union, Self
from pydantic import field_validator

from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
)
from pydantic import BaseModel, Field

ChatResponse = Union[ChatCompletion, list[ChatCompletionChunk]]

objective_description = '''
The objective for the taskRules for creating the instruction objective:
1. Keep only to the scope of the sub task
2. Provide information relevant to the completion of the sub task
3. if there is ambiguity, highlight this but provide your best guess
'''

class DecomposeSubTask(BaseModel):
    meta_type: Literal['sub_task_detail']
    name: str = Field(description='The name of the sub task')
    type: str = Field(description='The type of the task. Keep types focused (research, analysis, writing, etc.)')
    description: str = Field(description='Brief description for the task')
    context: str = Field(
        description='The context for the task, how it relates to the overall goal'
    )
    complexity: int = Field(description='The complexity of the task. Match complexity to subtask estimate (range: 1-5)')
    objective: str = Field(description=objective_description)


thinking_description = '''
As you are creating sub tasks, this is an optional space to think hard about the strategy for breaking down subsequent sub tasks.
You can include your reasoning here, and at a later stage it will be filtered out from execution of sub tasks.
'''

class DecomposeThinkingStep(BaseModel):
    meta_type: Literal['thinking_step']
    thinking: str = Field(
        description=thinking_description
    )


pause_description = '''
If this block is used, it should be because further breakdown of tasks is dependent on information or something that you do not have immediate access to.
For instance, if user clarification about the nature of something is required.
Try to avoid this if possible, unless user clarification is absolutely required.
This should be the final item generated in the response.
This space should be used to explain why a pause was needed.
'''

class DecompositionPause(BaseModel):
    meta_type: Literal['pause']
    reasoning: str = Field(description=pause_description)


class DecompositionUserInputPause(DecompositionPause):
    meta_type: Literal['user_input_pause'] = 'user_input_pause'


reset_description = '''
During the initial breakdown of sub tasks, it may be that an error or more optimal approach has been realised mid generation. 
This realisation means that all prior generated tasks are now invalid and to start generating the tasks again
Tasks prior to this will be discarded, and not executed. 
Only subsequent subtasks wille be considered. 
The space here is is intended to be the reasoning for why this reset is needed
'''

class DecomposeReset(BaseModel):
    meta_type: Literal['reset']
    reasoning: str = Field(
        description=reset_description
    )


DecomposeItem = Annotated[
    DecomposeSubTask | DecomposeThinkingStep | DecompositionPause | DecomposeReset, Field(discriminator='meta_type')
]


class TaskStatus(StrEnum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'


class SubTaskResult(BaseModel):
    meta_type: Literal['sub_task_result'] = 'sub_task_result'
    chat_response: ChatCompletionMessage | None = None


class SubTask(BaseModel):
    meta_type: Literal['sub_task'] = ('sub_task'
                                      '')
    decomposed_sub_task: DecomposeSubTask
    sub_task_result: SubTaskResult | None = None
    status: TaskStatus = TaskStatus.PENDING


class AccumulatedResult(BaseModel):
    meta_type: Literal['accumulated_result'] = 'accumulated_result'
    previous_results: list[Self]
    current_task: SubTask
    synthesis_prompt: ChatCompletionMessage
    chat_response: ChatCompletionMessage

    @field_validator('chat_response', mode='before')
    @classmethod
    def convert_sub_task_result(cls, v) -> ChatCompletionMessage:
        from .llama_utils import extract_message
        # If it's already a ChatCompletionMessage, return it as-is
        if isinstance(v, ChatCompletionMessage):
            return v
        return extract_message(v)



class BooleanResponse(BaseModel):
    yes: bool

class LLMMessage(BaseModel):
    role: Literal['system', 'user', 'assistant']
    content: str

class LLMInput(BaseModel):
    messages: list[LLMMessage]




# #
# # class Task(TaskBase):
# #     task_id: str
# #     objective: ChatCompletionMessage | None = None
# #     result: ChatResponse | None = None
# #     status: TaskStatus = TaskStatus.PENDING
# #     dependencies: list[TaskDependency] = Field(default_factory=list)
#
#
# class LlamaRoles(StrEnum):
#     SYSTEM = 'system'
#     USER = 'user'
#     ASSISTANT = 'assistant'
#
#
# class LlamaMessage(BaseModel):
#     role: Literal['system', 'user', 'assistant']
#     content: str
#
#
# class DecompositionHistory(BaseModel):
#     user_input: str
#     decomposition_prompt: str
#     decomposition_response: ChatResponse
#     initial_tasks: list[Task]
#
#
# class TaskExecutionResults(BaseModel):
#     task_id: str
#     task_prompt: ChatResponse
#     execution_response: ChatResponse
#
#
# class TaskSynthesisHistory(BaseModel):
#     objective: str
#     result: ChatResponse
#
#
# class TaskPromptHistory(BaseModel):
#     task: Task
#     generate_prompt: str
#     task_prompt: ChatResponse
#
#
# class OrchestrationHistory(BaseModel):
#     user_input: str
#     decomposition_history: DecompositionHistory
#     prompt_history: list[TaskPromptHistory]
#     execution_results: list[TaskExecutionResults] = []
#     synthesis_history: TaskSynthesisHistory
#
#
# class LLMMessage(BaseModel):
#     content: str
#     role: Literal['system', 'user', 'assistant']
#
#
# class LLMInput(BaseModel):
#     messages: list[LLMMessage]
