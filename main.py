import json
import os
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

import logging
logging.basicConfig(level=logging.DEBUG)

prompt = '''
I have the following idea:

I want to use dna origami to create structures that have magnetic molecules attached to specific points on them.
I then want to use hard drive with specific patterns magnetised to them, that the dna origami structures will selectively attach to based on the pattern magnetised onto the surface.

The overall goal is to develop a process of cheaply producing bespoke nanoscale devices, in small batches and with equipment that is relatively widely available. This is intended to be an alternative to standard lithographical processes, and to be able to do things that they cannot.

How would I go about this? Are there better ways of achieving this goal?

Overall I want to be able to provide a device that is affordable to consumers, and could theoretically be used in a garage, like a 3d printer.
One of the benefits of this process is that I suspect it wouldn't produce the same sort of pollution/industrial waste that standard semiconductor fabrication does, though I am unsure if this is true.
What alternatives exist?

I also want to be able to simulate the process, design and implement simulated experiements
I anticipate multiple experiments, one that would simulate the magnetic binding of different molecules onto magnetic surfaces, one that would generate the molecules using dna origami, and one that would simulate the structured clustering of the origami.
For the software packages use only open source software
Also what existing data would be useful for this?
'''


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

        idx_part = filename[len(prefix_with_underscore):-5]  # remove prefix_ and .json

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
    response, sub_tasks = task_orchestrator.query(user_input=prompt, return_sub_tasks=True)
    response_dict = {
        'final_response': response.model_dump(),
        'sub_tasks': [task.model_dump() for task in sub_tasks]
    }
    history_idx = get_max_index(os.getcwd(), "history") + 1
    results_idx = get_max_index(os.getcwd(), "results") + 1
    if history_idx is None:
        raise ValueError('history idx should not be None')
    if results_idx is None:
        raise ValueError('results idx should not be None')
    with open(f"history_{history_idx}.json", "w") as f:
        json.dump(task_orchestrator.history, f, indent=4)
    with open(f'results_{results_idx}.json', 'w') as f:
        json.dump(response_dict, f, indent=4)
    print(response.get_first_response())



if __name__ == "__main__":
    main()
