import json
import logging
import os

from project_serializer import generate_structure
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator
from llama_server import start_llama_server

logging.basicConfig(level=logging.INFO)

# with open('project_text.txt') as f:
#     PROJECT_TEXT = f.read()

# prompt = f"""
# I have the following project, here is its structure and contents:
# {generate_structure("./reasoning_sub_agents", ".py", "venv")}
#
# The aim of the project is to add deeper reasoning to llm responses, and it tries this by breaking user input down into sub tasks and executing those independently
#
# I wonder if its possible to extend this in such a way that the context length limit of llms can be mitigated or overcome?
# For instance, when the chat history or such reaches a certain point the maximum context, what about breaking the chat history down into atomic concepts and storing them, and their relationships, in neo4j (a graph based database that can perform vector queries)?
# Then on subsequent input relevant conversation history would be retrieved and combined in such a way as to respond seamlessly to the user.
#
# Other functionality I envision, would be adding a verification step to sub task completion, or allowing the sub task to pause while a separate mechanism retrieves information not readily available to the subclass.
#
# One use case I am interested in, is asking an llm to write a book, previously when I have done this, the LLM has had very short replies. For instance asking it to write a chapter of a book and it responding with a few short paragraphs. I would imagine a verification step could also act as feedback and the task could be regenerated with its previous output and feedback used to improve the next generation. This could be done until either a 'regeneration budget' was reached or the verification step was happy with the results.
#
# I would also be interested in adding functionality for subtasks that were deemed too complex to spawn their own sub orchestration and to be further broken down, again with some sort of 'budget' constraint to prevent infinite breakdowns.
#
# Please analyse this project for potential improvements and ways to extend its functionality.
# I know there are ways to improve speed and efficiency, but I care about those less than I do improving the quality of responses
# After you have finished the analysis, please output the full new files that you have changed.
# """
#
prompt = ("Please write a Harry Potter fanfiction book, this should be a reimagining "
          "of the first book but with Hermione taking on Harry's role.\n"
          "Please write the entire book, at least 10 chapters with 30 paragraphs per"
          " chapter. Make it a full book length, of a similar size to the bible!"
          "There is no source text, just write and write and write, chapter by chapter!")

# prompt = f"""
# I have the following project, here is its structure and contents:
# {generate_structure("./reasoning_sub_agents", ".py", "venv")}
#
# The aim of the project is to add deeper reasoning to llm responses, and it tries this by breaking user input down into sub tasks and executing those independently
#
# For some reason, there is only ever a single sub task generated during the decomposition step. Why is this?
# I have given it other prompts too, such as tasking it to write a book, and it only ever writes the plan for writing the book, it doesnt actually get on with it.
# Whats going on, why isn't it doing what I want?
# """

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

    # start_llama_server(config)

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
    with open(f"output_{results_idx}.md", "w") as f:
        f.write(response.content)
    print(response.content)


if __name__ == "__main__":
    main()
