import json
import logging
from copy import deepcopy
from itertools import permutations
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from .llama_utils import generate_simple_llm_input, get_streamed_json_response
from .schemas import DecomposeItem, Task, TaskBase, TaskDependency

logger = logging.getLogger(__name__)


class DecomposeResponse(BaseModel):
    reasoning: str
    tasks: list[DecomposeItem]


class RestrictedTaskDependency(TaskDependency):
    task_id: str


class DecomposeItemResponse(TaskBase):
    task_id: str
    dependencies: list[RestrictedTaskDependency]


class TaskIDDecomposeResponse(BaseModel):
    reason: str
    tasks: list[DecomposeItemResponse]


DECOMPOSE_TASK_PROMPT = """
You are a task decomposition expert. Analyze this root task:
{user_input}
Break it down into atomic subtasks in JSON array format:
```
{{
    "reasoning": <think about task breakdown before doing the breakdown>,
    "tasks": [
      {{
        "name": "<unique task name>"
        "description": "<detailed description>",
        "context": "<relevant context>",
        "complexity": <estimated_complexity>,
        "type": "<task_type>"
        "raw_dependencies": [
            {{
                "task_name": <name of task this task is dependent on>",
                "dependence_strength": <how dependent this task is on the other task>
            }},
        ] # this is a list of dictionaries, there can be none, one or more elements
      }}
    ]
}}
```
Rules for decomposition:
1. Ensure tasks are small enough to complete in one LLM operation
2. Maintain logical sequence flow
3. Keep types focused (research, analysis, writing, etc.)
4. Match complexity to subtask estimate (range: 1-5)
5. ONLY output JSON as structured above
6. A task is only dependent on another task if the other task must be completed before the other task begins
7. do not allow for circular dependencies within tasks dependent on other tasks.
8. A task does not have to be dependent on another task
9. Dependence strength should be a float between 0 and 10 indicating how important the dependence is
"""


GENERATE_DEPENDENCIES_PROMPT = """
You are a helpful task dependency expert.
Given the following user input:
{user_input}

which has been broken down into the following tasks:
```json
{sub_tasks}
```

this breakdown was based on this reasoning:
{reasoning}

please analyse the tasks for which tasks are dependent on other tasks and return the dependencies in the following format:
```
{{
    "reasoning": <think about task breakdown before doing the breakdown>,
    "tasks": [
      {{
        "task_id": <unique task id>,
        "name": "<unique task name>",
        "description": "<detailed description>",
        "context": "<relevant context>",
        "complexity": <estimated_complexity>,
        "type": "<task_type>",
        "dependencies": [
            {{
                "task_id": <task_id of task this task is dependent on>",
                "dependence_strength": <how dependent this task is on the other task>
            }},
        ] # this is a list of dictionaries, there can be none, one or more elements
      }}
    ]
}}
```

Rules:
1. No circular dependencies
2. Not all tasks are dependent on other tasks
3. A task cannot be dependent on itself
4. only analyse the dependencies, do no offer further comment
5. A task is only dependent on another task if the other task must be completed before the other task begins
6. Dependence strength should be a float between 0 and 10 indicating how important the dependence is
"""


class TaskDecomposer:
    def __init__(
        self,
        llm_client: OpenAI,
        history: dict | None = None,
    ):
        self.llm_client = llm_client
        self.history = {} if history is None else history

    def generate_sub_tasks(self, user_input: str) -> list[Task]:
        # given user input
        #  1. break down into relevant subtasks, with only relevant context
        #  2. run devil's advocate on the subtasks, find any potential issues in
        #     subtasks
        #  3. given the results from 1 and 2, generate refined subtasks
        self.history["user_input"] = user_input
        initial_tasks = self.generate_initial_sub_tasks(user_input=user_input)
        # TODO: steps 2-3
        return initial_tasks

    def generate_initial_sub_tasks(self, user_input: str) -> list[Task]:
        logger.debug("generating initial sub tasks")

        initial_decompose_taks = self.generate_initial_decomposition(
            user_input=user_input
        )
        sub_tasks = self.create_subtasks_from_decomposition_response(
            user_input=user_input, decomposition_response=initial_decompose_taks
        )
        logger.debug(f"generated {len(sub_tasks)} sub tasks")
        initial_task_history = []
        for task in sub_tasks:
            task_dict = task.model_dump()
            initial_task_history.append(task_dict)
        self.history["initial_tasks"] = initial_task_history
        return sub_tasks

    def generate_initial_decomposition(self, user_input: str) -> DecomposeResponse:
        initial_decompose_prompt = DECOMPOSE_TASK_PROMPT.format(user_input=user_input)
        self.history["decomposition_prompt"] = initial_decompose_prompt
        decompose_response = get_streamed_json_response(
            llama_client=self.llm_client,
            llm_input=generate_simple_llm_input(initial_decompose_prompt),
            response_model=DecomposeResponse,
        )
        self.history["decompose_response"] = decompose_response.model_dump()
        return decompose_response

    def create_subtasks_from_decomposition_response(
        self, user_input: str, decomposition_response: DecomposeResponse
    ) -> list[Task]:
        # The initial decomposition should generate names for tasks and their dependencies
        # However we can't trust that the model is correct, what if the names are duplicated,
        # or what if the names are not valid?
        # solution: create a custom subclass of task, that has the dependencies be one of the task ids
        # feed the previous response be input to this, along with the prompt, but have the dependencies be forced to be
        # one of the task ids or None.
        # use the response from this to then programatically search for circular imports and break the minimum total
        # strength dependencies to break the circular tasks

        class DecomposeItemWithID(DecomposeItem):
            task_id: str

        tasks_with_ids = [
            DecomposeItemWithID(task_id=f"task_{idx}", **item.model_dump())
            for idx, item in enumerate(decomposition_response.tasks)
        ]
        tasks_with_dependencies_prompt = GENERATE_DEPENDENCIES_PROMPT.format(
            user_input=user_input,
            reasoning=decomposition_response.reasoning,
            sub_tasks=json.dumps([task.model_dump() for task in tasks_with_ids], indent=4),
        )

        task_ids = [task.task_id for task in tasks_with_ids]

        class RestrictedTaskDependency(TaskDependency):
            task_id: Literal[*task_ids]

        class DecomposeItemResponse(TaskBase):
            task_id: Literal[*task_ids]
            dependencies: list[RestrictedTaskDependency]

        class TaskIDDecomposeResponse(BaseModel):
            reason: str
            tasks: list[DecomposeItemResponse]

        logger.debug("generating sub tasks with enforced dependencies")
        enforced_sub_task_response: TaskIDDecomposeResponse = (
            get_streamed_json_response(
                llama_client=self.llm_client,
                llm_input=generate_simple_llm_input(tasks_with_dependencies_prompt),
                response_model=TaskIDDecomposeResponse,
            )
        )
        logger.debug(f"generated {len(enforced_sub_task_response.tasks)} sub tasks")
        self.history["decompose_with_dependencies_response"] = (
            enforced_sub_task_response.model_dump()
        )

        cleaned_decomposed_tasks = self.clean_task_decompose_response(
            enforced_sub_task_response.tasks
        )
        self.history["cleaned_decompose_with_dependencies_response"] = [
            cleaned_task.model_dump() for cleaned_task in cleaned_decomposed_tasks
        ]

        tasks = [
            Task(**cleaned_task.model_dump())
            for cleaned_task in cleaned_decomposed_tasks
        ]
        return tasks

    def clean_task_decompose_response(
        self, decomposed_tasks: list[DecomposeItemResponse]
    ) -> list[DecomposeItemResponse]:
        """
        Cleans a TaskIDDecomposeResponse by:
        1. Removing duplicate tasks (keeping unique task_id).
           - Keeps the first occurrence of non-dependency fields (from TaskBase).
           - Merges dependencies: union of all dependencies, taking the maximum strength for any duplicate dependency edges.
        2. Removing circular dependencies by finding the topological ordering that maximizes the total kept dependence_strength
           (i.e., minimizes the total strength of removed edges). This is solved exactly via brute-force over all permutations
           (feasible since max 10 tasks → 10! = 3.6M permutations, runs in ~5–30 seconds on typical hardware depending on edge count).

        Returns a new cleaned TaskIDDecomposeResponse with the same 'reason' field.
        """
        logger.debug(
            f"cleaning {len(decomposed_tasks)} tasks of duplication and circular dependencies"
        )
        # Step 1: Deduplicate and merge
        task_map: dict[str, DecomposeItemResponse] = {}

        for item in decomposed_tasks:
            tid = item.task_id
            if tid not in task_map:
                task_map[tid] = deepcopy(item)
            else:
                existing = task_map[tid]
                # Merge dependencies: keep max strength for each target
                dep_dict: dict[str, RestrictedTaskDependency] = {
                    dep.task_id: dep for dep in existing.dependencies
                }
                for dep in item.dependencies:
                    if dep.task_id in dep_dict:
                        dep_dict[dep.task_id].dependence_strength = max(
                            dep_dict[dep.task_id].dependence_strength,
                            dep.dependence_strength,
                        )
                    else:
                        dep_dict[dep.task_id] = deepcopy(dep)
                existing.dependencies = list(dep_dict.values())
                # Non-dependency fields (from TaskBase) remain from the first occurrence

        nodes: list[str] = list(task_map.keys())
        k = len(nodes)

        # this should never occur
        if k == 0:
            raise RuntimeError("removing duplicated tasks resulted in 0 tasks!")

        # Build edges: (prereq, dependent, strength) where prereq → dependent means "dependent depends on prereq"
        # (i.e., prereq should come before dependent in topological order)
        strength_map: dict[tuple[str, str], float] = {}
        for dependent, item in task_map.items():
            for dep in item.dependencies:
                prereq = dep.task_id
                if prereq == dependent:
                    continue  # Remove self-loops (they are always invalid cycles)
                if prereq in task_map:
                    key = (prereq, dependent)
                    strength_map[key] = max(
                        strength_map.get(key, 0.0), dep.dependence_strength
                    )

        edges: list[tuple[str, str, float]] = [
            (p, d, s) for (p, d), s in strength_map.items()
        ]

        # Map nodes to 0..k-1 for faster processing
        node_to_idx: dict[str, int] = {node: i for i, node in enumerate(nodes)}
        edges_idx: list[tuple[int, int, float]] = [
            (node_to_idx[p], node_to_idx[d], s) for p, d, s in edges
        ]

        # Step 2: Find the best topological ordering (maximize kept strength)
        best_score = -float("inf")
        best_order: tuple[int, ...] | None = None

        for perm in permutations(
            range(k)
        ):  # perm is the order of indices: early → late
            # Build position array: pos[idx] = position in order (smaller = earlier)
            pos = [0] * k
            for position, node_idx in enumerate(perm):
                pos[node_idx] = position

            score = 0.0
            for i_prereq, i_dependent, s in edges_idx:
                if pos[i_prereq] < pos[i_dependent]:  # forward edge → keep
                    score += s

            if score > best_score:
                best_score = score
                best_order = perm

        # Build kept edge set using best order
        if best_order is None:
            kept_edges: set[tuple[str, str]] = set()
        else:
            pos = [0] * k
            for position, node_idx in enumerate(best_order):
                pos[node_idx] = position

            kept_edges = {
                (nodes[i_prereq], nodes[i_dependent])
                for i_prereq, i_dependent, _ in edges_idx
                if pos[i_prereq] < pos[i_dependent]
            }

        # Create cleaned items with only kept dependencies
        new_items: list[DecomposeItemResponse] = []
        for node in nodes:
            original_item = task_map[node]
            new_deps = [
                dep
                for dep in original_item.dependencies
                if (dep.task_id, node) in kept_edges
            ]
            new_item = deepcopy(original_item)
            new_item.dependencies = new_deps
            new_items.append(new_item)

        # Sort tasks by numeric index for deterministic output (task_0, task_1, ...)
        new_items.sort(key=lambda x: int(x.task_id.split("_")[1]))

        logger.debug(f"cleaned tasks, resulting in {len(new_items)} new tasks")
        return new_items
