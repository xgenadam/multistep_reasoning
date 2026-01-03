import json
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator


def main():
    with open("config.json") as f:
        config = json.load(f)
    task_orchestrator = TaskOrchestrator.instantiate(config=config)
    prompt = 'I want to start eating healthier. Please prepare a list of recipes that are simple to prepare and above all minimise washing up. Please create a meal plan. You can also look at more complex to prepare meals that involve preparation at the beginning of the week. Also can you prepare whole meals in a rice cooker? Would an air fryer be a good investment for this?'
    response, sub_tasks = task_orchestrator.query(user_input=prompt, return_sub_tasks=True)
    response_dict = {
        'final_response': response.model_dump(),
        'sub_tasks': [task.model_dump() for task in sub_tasks]
    }
    with open('results_2.json', 'w') as f:
        json.dump(response_dict, f, indent=4)
    print(response.get_first_response())



if __name__ == "__main__":
    main()
