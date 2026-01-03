import copy
import json


from .boolean_decider import BooleanDecider
from .schemas import Task, LlamaResponse
from .llama_utils import LlamaRunner


DECOMPOSE_TASK_PROMPT = """
You are a task decomposition expert. Analyze this root task:
{user_input}
Break it down into atomic subtasks in JSON array format:
[
  {{
    "description": "<detailed description>",
    "context": "<relevant context>",
    "complexity": <estimated_complexity>,
    "type": "<task_type>"
  }}
]
Rules for decomposition:
1. Ensure tasks are small enough to complete in one LLM operation
2. Maintain logical sequence flow
4. Keep types focused (research, analysis, writing, etc.)
5. Match complexity to subtask estimate (range: 1-5)
6. ONLY output JSON as structured above
"""


GENERATE_NEW_TASK_FROM_DECOMPOSE_RESPONSE_PROMPT = """
You are a task analysis expert that answers questions regarding tasks to respond to a user input.
This is the user input:
{user_input}

Here are a list of tasks, in an approximate json format, that are steps to answer the user input:
{decomposed_tasks}


These are the previous tasks that have been extracted from the above list, in json format:
{previous_tasks}

Extract and output just the {tag} of task number {task_number}
Rules for extraction:
1. Extract and output only the {tag} of {task_number} and output that, do not add additional text
2. type should be a single word
3. context should be the background information the task needs for the task, it should be brief 
4. the description should be a brief description of the relevant task, what it needs to achieve 
"""


VERIFY_NO_MORE_TASKS_PROMPT = """
This is a loosely structured set of tasks:
{raw_task_decomposition}

This is a more structured format of the loosely structured set of tasks:
{structured_tasks}

Is the number of structured tasks equal to, or greater than, the number of unstructured tasks?
"""


GENERATE_DEPENDENCIES_PROMPT = """
You are a helpful task dependency expert.
Given the following user input:
{user_input}

which has been broken down into the following tasks:
{sub_tasks}

please analyse the tasks for which tasks are dependent on other tasks

Rules:
1. No circular dependencies
2. Not all tasks are dependent on other tasks
3. A task cannot be dependent on itself
"""


CHECK_DEPENDENCIES_PROMPT = """
Given the following:
{dependency_response}

is this task:
{task_1}

dependent on this task:
{task_2}

being completed first?
"""


class TaskDecomposer:
    def __init__(self, llm: LlamaRunner, boolean_decider: BooleanDecider):
        self.llm = llm
        self.boolean_decider = boolean_decider

    def generate_sub_tasks(self, user_input: str) -> list[Task]:
        # given user input
        #  1. break down into relevant subtasks, with only relevant context
        #  2. run devil's advocate on the subtasks, find any potential issues in
        #     subtasks
        #  3. given the results from 1 and 2, generate refined subtasks
        initial_tasks = self.generate_initial_sub_tasks(user_input=user_input)
        # TODO: steps 2-3
        return initial_tasks

    def generate_initial_sub_tasks(self, user_input: str) -> list[Task]:
        decomposition_response = self.generate_initial_decomposition(
            user_input=user_input
        )
        sub_tasks = self.create_subtasks_from_decomposition_response(
            user_input=user_input, decomposition_response=decomposition_response
        )
        return self.build_tasks_with_dependencies(
            user_input=user_input, sub_tasks=sub_tasks
        )

    def generate_initial_decomposition(self, user_input: str) -> LlamaResponse:
        initial_decompose_prompt = DECOMPOSE_TASK_PROMPT.format(user_input=user_input)
        return self.llm(initial_decompose_prompt)

    def create_subtasks_from_decomposition_response(
        self, user_input: str, decomposition_response: LlamaResponse
    ) -> list[Task]:
        sub_tasks = (
            self.create_subtasks_from_decomposition_response_without_dependencies(
                user_input=user_input,
                decomposition_response=decomposition_response,
            )
        )

        return sub_tasks

    def create_subtasks_from_decomposition_response_without_dependencies(
        self, user_input: str, decomposition_response: LlamaResponse
    ) -> list[Task]:
        sub_tasks: list[Task] = []
        # max loop 100, if there are more than 100 sub tasks, refactor
        # we want to start at 1 here due to the nature of how idx is used in the prompt
        for idx in range(1, 101):
            sub_tasks.append(
                self.generate_sub_task(
                    idx=idx,
                    user_input=user_input,
                    decomposition_response=decomposition_response,
                    previously_generated_sub_tasks=sub_tasks,
                )
            )
            if self.boolean_decider.get_decision(
                VERIFY_NO_MORE_TASKS_PROMPT.format(
                    raw_task_decomposition=decomposition_response.get_first_response(),
                    structured_tasks=json.dumps(
                        [task.model_dump(include=['description', 'context', 'type', 'complexity']) for task in sub_tasks], indent=2
                    ),
                )
            ):
                break
        return sub_tasks

    def build_tasks_with_dependencies(
        self, user_input: str, sub_tasks: list[Task]
    ) -> list[Task]:
        sub_tasks = copy.deepcopy(sub_tasks)
        sub_tasks_str = json.dumps(
            [
                task.model_dump(include=['description', 'context', 'type', 'complexity'])
                for task in sub_tasks
            ],
            indent=2,
        )
        dependency_prompt = GENERATE_DEPENDENCIES_PROMPT.format(
            user_input=user_input, sub_tasks=sub_tasks_str
        )
        dependency_response = self.llm(dependency_prompt)
        for sub_task_1 in sub_tasks:
            for sub_task_2 in sub_tasks:
                if sub_task_1 is sub_task_2 or sub_task_1.id in sub_task_2.dependencies:
                    continue
                if self.is_task_1_dependent_on_task_2(
                    task_1=sub_task_1,
                    task_2=sub_task_2,
                    dependency_response=dependency_response,
                ):
                    sub_task_1.dependencies.append(sub_task_2.id)
        return sub_tasks

    def is_task_1_dependent_on_task_2(
        self, task_1: Task, task_2: Task, dependency_response: LlamaResponse
    ) -> bool:
        check_dependency_prompt = CHECK_DEPENDENCIES_PROMPT.format(
            dependency_response=dependency_response.get_first_response(),
            task_1=json.dumps(task_1.model_dump(include=['description', 'context', 'type', 'complexity']), indent=2),
            task_2=json.dumps(task_2.model_dump(include=['description', 'context', 'type', 'complexity']), indent=2),
        )
        return self.boolean_decider.get_decision(check_dependency_prompt)

    def generate_sub_task(
        self,
        idx: int,
        user_input: str,
        decomposition_response: LlamaResponse,
        previously_generated_sub_tasks: list[Task],
    ) -> Task:
        task_data = {}
        for tag in ["description", "context", "task_type", "complexity", "type"]:
            task_data[tag] = self.generate_sub_task_component(
                idx=idx,
                tag=tag,
                user_input=user_input,
                decomposition_response=decomposition_response,
                previously_generated_sub_tasks=previously_generated_sub_tasks,
            ).get_first_response()
        return Task(id=f"sub_task_{idx}", **task_data)

    def generate_sub_task_component(
        self,
        idx: int,
        tag: str,
        user_input: str,
        decomposition_response: LlamaResponse,
        previously_generated_sub_tasks: list[Task],
    ) -> LlamaResponse:
        previous_tasks_str = json.dumps(
            [
                task.model_dump(include=['description', 'context', 'type', 'complexity'])
                for task in previously_generated_sub_tasks
            ],
            indent=2,
        )
        prompt = GENERATE_NEW_TASK_FROM_DECOMPOSE_RESPONSE_PROMPT.format(
            user_input=user_input,
            decomposed_tasks=decomposition_response.get_first_response(),
            previous_tasks=previous_tasks_str,
            tag=tag,
            task_number=idx,
        )
        return self.llm(prompt)
