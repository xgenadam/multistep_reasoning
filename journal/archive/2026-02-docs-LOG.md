# 01/02/25
This is the first log entry and comes at a point where the project has been developed intermitently over the last few weeks

I guess here is worth introducing the original concept of the project, its aims and the initial development before getting to this stage.

The project was borne out of the following goal: To get an LLM to enrich its output via some self prompting. Wrapping the calls to the LLM in prompts that would force "thinking" behind the scenes.
The initial attempts involved breaking a task down into sub tasks, executing them, then having a final combination step

* initial decomposition did not use instruct and relied on a strong prompt to force the output of a given json format
  *  this was reliable for powerful models but after discovering the instruct package this seems to be superior
  * Sub tasks could depend on other sub tasks (more than one)
    * this required additional code to handle circular dependencies within tasks, became complicated and was not performant
    * the decision was made to switch over to linear completion tasks, and use instruct to enforce the output
* after decomposition a prompt agent would use the info in the sub task to generate a prompt for that task
* the execution step looked for tasks without dependencies, executed them and stored the results
* the synthesiser took all of these results and combined them
* handle pause return in decomposition

There were plenty of flaws with the above approach:
* the dependencies between tasks was flaky. 
  * required a pythonic check for circular dependencies
  * to counter circular dependencies the model was updated to provide a 'weight' for dependencies
  * without instruct this was a pain
  * added lots of room for error
  * how would task `n` accurately know it would be dependent on task `n+b`? it requires a very smart model and could be a source of error
  * the llm needed to name each sub task, and simpler models, when referencing dependencies, could get the names wrong

This was why it was decided to switch to a simpler, linear generation, using instruct to enforce output schema

After using instruct, it occured to add the following model types (in task decomposition), aside from the obvious sub task:
* thinking
  * this is a bit self explanatory, the idea is that to give the model more time to reason, even if it is mid generation of sub tasks, it could use this space to reason and plan ahead. Or even realise it had taken the wrong approach, which leads to the next output type
* reset
  * if the llm has generated a series of subtasks up to this point and realises part way through, generating this will result in the previously generated tasks being discarded. The llm is informed of this and should use it appropriately
* pause
  * the idea is that this should be the last type generated if there is a reason it can't complete the breakdown of sub tasks, such as needing clarrification from the user. currently this is not handled

The linear nature of task generation also simplified execution, and synthesis.
Currently tasks are executed, and then a synthesis step combines the previous synthesised results with the new sub task execution result.
This somewhat works, but it is not perfect, and info seems to be missing from the final output. Though more testing and a criticism step here might make things a bit more consistent.

One thing to note, the streaming stuff seems to not play as nice with instruct as I'd hoped. There seem to be edge cases. Worth looking more into though.

## whats next?
`TODO.md` contains a list of shit todo (duh!)
I intend to focus on the synthesis

# 02/02/26

Created `OBJECTIVE.md`, and `CURRENT_STATUS.md`
These are to be a reference for the overall objective. I don't anticipate this changing much, once written, but it is to encapsulate what I want out of this project. 
I need to write it, include milestones and provide some examples of what I want the project to do and at what standard.

`CURRENT_STATUS.md` is meant to keep track of what in the project is currently working and what is currently not working.

However, I don't want to get sidetracked with writing documentation (its a personal project, writing code is more fun!), so will write these later, the files are placeholders for now.

I've also create the `docs/notespace` subdirectory. This is for note takind and rough planning. Meant to be very informal. 

Today I'm aiming to work on the synthesiser. The decomposition is at a reasonable state, the synthesis is not.  

------

A bit later I read through how cline implemented file changes. They have a search and replace functionality along with the functionality to rewrite the entire file. The prompt tells the llm to prefer to replace in file unless it really needs to rewrite the entire thing. I will try this approach here.

# 03/02/26

lets start implementing the new synthesiser, it should implement the replace in document functionality (the "document" being the final response in this case).
This way we give the agent to modify early parts of the file if needed

Only made a small start on this, did other things today.