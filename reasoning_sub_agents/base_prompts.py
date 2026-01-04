ROOT_TASK_TEXT = """
{{
  "id": "{task_id}",
  "description": "{description}",
  "complexity": {complexity},
  "type": "{task_type}",
  "context": "{context}"
}}
"""


DEVIATIONS_PROMPT = """
Given the following subtasks decomposition:
{subtasks}

Identify any flaws, missing steps, or improvements needed. Consider:
- Are any tasks redundant or overlapping?
- Are there missing dependencies?
- Are the tasks atomic enough?
- Is the complexity correctly estimated?
- Are the types appropriate?

Provide a detailed critique and suggest modifications.
"""

FINALIZE_TASK_PROMPT = """
Given the initial decomposition:
{initial_tasks}

And the following critique:
{critique}

Generate an improved decomposition of subtasks that addresses the critique.
Return in the same JSON format as specified.
"""

EXECUTE_TASK_PROMPT = """
### Task Execution ###
You are tasked with executing the following subtask:

**Description:** {task_description}
**Context:** {task_context}

**Instructions:**
1. Analyze the task description and context thoroughly.
2. Utilize the provided context to complete the task.
3. If additional information is needed, make reasonable assumptions based on the context.
4. Provide a detailed and accurate response.

**Response Format:**
Return your response in JSON format with the following structure:
{
    "result": "<Your task result>",
    "metadata": {
        "confidence": "<confidence level 1-5>",
        "notes": "<additional notes or considerations>"
    }
}
"""

SYNTHESIZE_PROMPT = """
### Final Synthesis ###
Original User Request: {user_request}

Completed Subtasks and Results:
{results}

**Instructions for Synthesis:**
1. **Thoroughly analyze** all subtask results to identify key findings.
2. **Resolve any contradictions** or inconsistencies between results.
3. **Combine information** from all subtasks to form a comprehensive answer.
4. **Structure the response** logically, highlighting important points.
5. **Ensure completeness** by addressing all aspects of the original request.
6. **Maintain clarity** and conciseness in the final output.

Please provide a well-structured, coherent final answer based on the subtask results.
"""


CHECK_TASKS_DEPENDENCIES_PROMPT = """
You are a task dependency expert. Given an overall task, and two subtasks. 
Your job is to determine if one task is dependent on the other.
The overall task is:
{root_task}
Is this task:
{{
    "id": "{sub_task_1_id}",
    "description": "{sub_task_1_description}",
    "context": "{sub_task_1_context}",
    "complexity": {sub_task_1_complexity},
    "type": "{sub_task_1_type}}"
}}
dependent on this task:
{{
    "id": "{sub_task_2_id}",
    "description": "{sub_task_2_description}",
    "context": "{sub_task_2_context}",
    "complexity": {sub_task_2_complexity},
    "type": "{sub_task_2_type}}"
}}
Rules for dependencies:
1. A task is only dependent on another task if actions from the other task are relevant to the tasks completion
2. Tasks cannot be mutually dependent
3. ONLY reply with YES or NO
"""
