import json
import logging
import os
from pathlib import Path

from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

from .project_serializer import generate_structure

logging.basicConfig(level=logging.DEBUG)

prompt = f"""
I have the following project, here is its structure and contents:
{generate_structure("./reasoning_sub_agents", ".py", "venv")}

Here is an example history output of the project:
```json
{json.load(Path("history_6.json").open())}
```

The aim of the project is to add deeper reasoning to llm responses, and it tries this by breaking user input down into sub tasks and executing those independently

I wonder if its possible to extend this in such a way that the context length limit of llms can be mitigated or overcome? 

Please analyse this project for potential improvements and ways to extend its functionality
"""


def get_max_index(directory: str, prefix: str) -> int | None:
    """
    Returns the greatest integer idx for files named <prefix>_<idx>.json
    in the given directory.

    Non-integer idx values are ignored.
    Returns None if no valid files are found.
    """
    max_idx = None
    prefix_with_underscore = f"{prefix}_"

    for filename in os.listdir(directory):
        if not filename.endswith(".json"):
            continue
        if not filename.startswith(prefix_with_underscore):
            continue

        idx_part = filename[
            len(prefix_with_underscore) : -5
        ]  # remove prefix_ and .json

        try:
            idx = int(idx_part)
        except ValueError:
            continue  # ignore non-integer idx

        if max_idx is None or idx > max_idx:
            max_idx = idx

    return max_idx


def main():
    with open("config.json") as f:
        config = json.load(f)
    task_orchestrator = TaskOrchestrator.instantiate(config=config)
    response, sub_tasks = task_orchestrator.query(
        user_input=prompt, return_sub_tasks=True
    )
    response_dict = {
        "final_response": response.model_dump(),
    }
    history_idx = get_max_index(os.getcwd(), "history") + 1
    results_idx = get_max_index(os.getcwd(), "results") + 1
    if history_idx is None:
        raise ValueError("history idx should not be None")
    if results_idx is None:
        raise ValueError("results idx should not be None")
    with open(f"history_{history_idx}.json", "w") as f:
        json.dump(task_orchestrator.history, f, indent=4)
    with open(f"results_{results_idx}.json", "w") as f:
        json.dump(response_dict, f, indent=4)
    print(response.get_first_response())


if __name__ == "__main__":
    main()
