import copy
import json

from .boolean_decider import BooleanDecider
from .schemas import Task, LlamaResponse
from .llama_utils import LlamaRunner

from pydantic_core import ValidationError

import logging

logger = logging.getLogger(__name__)

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
3. Keep types focused (research, analysis, writing, etc.)
4. Match complexity to subtask estimate (range: 1-5)
5. ONLY output JSON as structured above
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
5. If a task is already present, do not duplicate it 
"""

VERIFY_NO_MORE_TASKS_PROMPT = """
This is the first set of tasks:

```text
{raw_task_decomposition}
```

This is the second set of tasks:
```json
{structured_tasks}
```

Is the number of tasks in the second set, or greater than, the number of tasks in the first set?
Or does the content of second set of tasks contain the content of the first set?  
Answer with only yes or no
Rules for answering:
1. ONLY RESPOND with yes OR no DO NOT ELABORATE BEYOND yes OR no
2. only respond with yes OR no do not elaborate beyond yes or no
"""

GENERATE_DEPENDENCIES_PROMPT = """
You are a helpful task dependency expert.
Given the following user input:
{user_input}

which has been broken down into the following tasks:
```json
{sub_tasks}
```

please analyse the tasks for which tasks are dependent on other tasks

Rules:
1. No circular dependencies
2. Not all tasks are dependent on other tasks
3. A task cannot be dependent on itself
4. only analyse the dependencies, do no offer further comment
"""

CHECK_DEPENDENCIES_PROMPT = """
Given the following task dependencies:
```text
{dependency_response}
```

this is the subject task:
```json
{task_1}
```

this potential dependant task:
```json
{task_2}
```

is the subject task dependent on the potentially dependant task?
answer with only yes or no
Rules:
1. ONLY RESPOND with yes OR no DO NOT ELABORATE BEYOND yes OR no
2. only respond with yes OR no do not elaborate beyond yes or no
"""


class TaskDecomposer:
    def __init__(
            self,
            llm: LlamaRunner,
            boolean_decider: BooleanDecider,
            history: dict | None = None):
        self.llm = llm
        self.boolean_decider = boolean_decider
        self.history = {} if history is None else history

    def generate_sub_tasks(self, user_input: str) -> list[Task]:
        # given user input
        #  1. break down into relevant subtasks, with only relevant context
        #  2. run devil's advocate on the subtasks, find any potential issues in
        #     subtasks
        #  3. given the results from 1 and 2, generate refined subtasks
        self.history['user_input'] = user_input
        initial_tasks = self.generate_initial_sub_tasks(user_input=user_input)
        # TODO: steps 2-3
        return initial_tasks

    def generate_initial_sub_tasks(self, user_input: str) -> list[Task]:
        logger.debug('generating initial sub tasks')

        decomposition_response = self.generate_initial_decomposition(
            user_input=user_input
        )
        sub_tasks = self.create_subtasks_from_decomposition_response(
            user_input=user_input, decomposition_response=decomposition_response
        )
        logger.debug(f'generated {len(sub_tasks)} sub tasks')
        logger.debug('beginning dependency analysis of sub tasks')
        tasks = self.build_tasks_with_dependencies(
            user_input=user_input, sub_tasks=sub_tasks
        )
        initial_task_history = []
        for task in sub_tasks:
            task_dict = task.model_dump()
            initial_task_history.append(task_dict)
        self.history['initial_task'] = initial_task_history
        return tasks

    def generate_initial_decomposition(self, user_input: str) -> LlamaResponse:
        # TODO: modify the prompt such that the decomposition includes task
        #  dependencies. Will need to also add a check for circular dependencies,
        #  and if they occur a method to break them
        initial_decompose_prompt = DECOMPOSE_TASK_PROMPT.format(
            user_input=user_input)
        self.history['decomposition_prompt'] = initial_decompose_prompt
        decompose_response = self.llm(initial_decompose_prompt)
        self.history['decompose_response'] = decompose_response.model_dump()
        return decompose_response

    def create_subtasks_from_decomposition_response(
            self, user_input: str, decomposition_response: LlamaResponse
    ) -> list[Task]:
        try:
            # high quality models can actually output properly structured json that
            # we can serialize. the fallback is for crappier models, though if they
            # are too poor quality even that will mess up
            sub_task_dicts = json.loads(
                decomposition_response.get_first_response().replace('```json',
                                                                    '').replace(
                    '```', ''))
            tasks = []
            for idx, task_dict in enumerate(sub_task_dicts):
                tasks.append(Task(id=f'task_{idx}', **task_dict))
            return tasks
        except (json.decoder.JSONDecodeError, ValidationError) as exc:
            logger.warning('failed to convert raw model output to Task: %s, using fallback task generation' % exc)
            logger.debug(f'raw_prompt: {decomposition_response.get_first_response()}')
            sub_tasks = (
                self.create_subtasks_from_decomposition_response_without_dependencies(
                    user_input=user_input,
                    decomposition_response=decomposition_response,
                )
            )
            initial_task_history = []
            for task in sub_tasks:
                task_dict = task.model_dump()
                initial_task_history.append(task_dict)
            self.history['initial_task'] = initial_task_history
            return sub_tasks


    def create_subtasks_from_decomposition_response_without_dependencies(
            self, user_input: str, decomposition_response: LlamaResponse
    ) -> list[Task]:
        sub_tasks: list[Task] = []
        # max loop 100, if there are more than 100 sub tasks, refactor
        # we want to start at 1 here due to the nature of how idx is used in the prompt
        for idx in range(1, 101):
            # TODO: we may want to add a sub task duplication check before appending
            sub_tasks.append(
                self.generate_sub_task(
                    idx=idx,
                    user_input=user_input,
                    decomposition_response=decomposition_response,
                    previously_generated_sub_tasks=sub_tasks,
                )
            )
            more_tasks_prompt = VERIFY_NO_MORE_TASKS_PROMPT.format(
                raw_task_decomposition=decomposition_response.get_first_response(),
                structured_tasks=json.dumps(
                    [task.model_dump(
                        include=['description', 'context', 'type', 'complexity']) for
                     task in sub_tasks], indent=2
                ),
            )
            more_tasks_response = self.llm(more_tasks_prompt)
            more_task_text = more_tasks_response.get_first_response().strip().lower()
            if more_task_text not in {'yes', 'no'}:
                logger.warning(
                    f'expected yes or no response to {more_tasks_prompt}, got {more_task_text}')
                if self.boolean_decider.is_affirmative(
                        more_tasks_response.get_first_response()):
                    break
            else:
                if more_task_text == 'yes':
                    break
        return sub_tasks

    def build_tasks_with_dependencies(
            self, user_input: str, sub_tasks: list[Task]
    ) -> list[Task]:
        sub_tasks = copy.deepcopy(sub_tasks)
        sub_tasks_str = json.dumps(
            [
                task.model_dump(
                    include=['id', 'description', 'context', 'type', 'complexity'])
                for task in sub_tasks
            ],
            indent=2,
        )
        dependency_prompt = GENERATE_DEPENDENCIES_PROMPT.format(
            user_input=user_input, sub_tasks=sub_tasks_str
        )
        dependency_response = self.llm(dependency_prompt)
        for sub_task_1 in sub_tasks:
            logger.debug(f'finding dependencies of sub task {sub_task_1.id}')
            for sub_task_2 in sub_tasks:
                if sub_task_1 is sub_task_2 or sub_task_1.id in sub_task_2.dependencies:
                    continue
                if not self.task_1_dep_task_2_results_in_circular_dependence(
                        sub_task_1, sub_task_2,
                        sub_tasks) and self.is_task_1_dependent_on_task_2(
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
            task_1=json.dumps(task_1.model_dump(
                include=['id', 'description', 'context', 'type', 'complexity']), indent=2),
            task_2=json.dumps(task_2.model_dump(
                include=['id', 'description', 'context', 'type', 'complexity']), indent=2),
        )
        dependency_check = self.llm(check_dependency_prompt)
        dependency_check_text = dependency_check.get_first_response().strip().lower()
        if dependency_check_text not in {'yes', 'no'}:
            logger.warning(
                f'expected yes or no response to:\n{check_dependency_prompt}\ngot:\n{dependency_check_text}')
            return self.boolean_decider.is_affirmative(
                dependency_check.get_first_response())
        else:
            return dependency_check_text == 'yes'

    def generate_sub_task(
            self,
            idx: int,
            user_input: str,
            decomposition_response: LlamaResponse,
            previously_generated_sub_tasks: list[Task],
    ) -> Task:
        task_data = {}
        logger.debug(f"Generating task {idx}")
        for tag in ["description", "context", "task_type", "complexity", "type"]:
            task_data[tag] = self.generate_sub_task_component(
                idx=idx,
                tag=tag,
                user_input=user_input,
                decomposition_response=decomposition_response,
                previously_generated_sub_tasks=previously_generated_sub_tasks,
            ).get_first_response()
        logger.debug(f"Generated task {idx}")
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
                task.model_dump(
                    include=['description', 'context', 'type', 'complexity'])
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

    def task_1_dep_task_2_results_in_circular_dependence(
            self,
            task_1: Task,
            task_2: Task,
            tasks: list[Task]
    ) -> bool:
        """
        Returns True if adding task_2.id to task_1.dependencies would create
        a circular dependency.
        """
        # Build lookup for quick access
        task_map = {task.id: task for task in tasks}

        visited = set()

        def dfs(task_id: str) -> bool:
            if task_id == task_1.id:
                # We found a path back to task_1 → cycle
                return True

            if task_id in visited:
                return False

            visited.add(task_id)

            task = task_map.get(task_id)
            if not task:
                return False

            return any(dfs(dep_id) for dep_id in task.dependencies)

        # Check if task_1 is reachable from task_2
        return dfs(task_2.id)
