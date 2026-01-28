import json
import logging
from collections.abc import Iterable

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from .llama_utils import extract_message, generate_simple_llm_input, stream_conversation
from .schemas import SubTask

SYNTHESIS_PROMPT = """
### Final Synthesis ###
Original User Request:
{user_input}

Completed Subtasks and Results:
{completed_tasks}

**Instructions for Synthesis:**
1. **Thoroughly analyze** all subtask results to identify key findings, including technical details, code snippets, and structured data.
2. **Resolve any contradictions** or inconsistencies between results, ensuring logical coherence.
3. **Combine information** from all subtasks to form a comprehensive answer, explicitly preserving:
   - Code blocks or snippets (include verbatim with proper formatting).
   - Technical specifications, formulas, or structured data (e.g., tables, JSON).
   - Complex findings or nuanced insights (do not simplify or omit).
4. **Structure the response** logically, grouping related details (e.g., code under a "Implementation" section, analysis under "Findings").
5. **Validate completeness** by cross-referencing the final output with sub-task results:
   - Flag any missing critical details (e.g., "Note: Subtask X mentioned [specific detail] not included above").
   - Ensure all actionable outputs (e.g., scripts, configurations) are retained.
6. **Maintain clarity** and conciseness, but prioritize accuracy and completeness over brevity.
7. **Highlight high-value content** (e.g., "Key Implementation: [code block]") to ensure visibility.
"""


class ResultSynthesiser:
    def __init__(self, llm_client: OpenAI, history: dict | None = None):
        self.llm_client = llm_client
        self.history = history if history is not None else {}

    def synthesise_results(
        self, user_input: str, completed_sub_tasks: Iterable[Task]
    ) -> ChatCompletionMessage:
        completed_sub_task_str = json.dumps(
            [
                task.model_dump(
                    include={
                        'context',
                        'description',
                        'complexity',
                        'type',
                        'result',
                        'status',
                    }
                )
                for task in completed_sub_tasks
            ],
            indent=4,
        )
        synthesis_prompt = SYNTHESIS_PROMPT.format(
            user_input=user_input,
            completed_tasks=completed_sub_task_str,
        )
        llm_input = generate_simple_llm_input(synthesis_prompt)
        logging.debug('beginning synthesis')
        synthesis_result = extract_message(
            stream_conversation(
                llama_client=self.llm_client,
                llm_input=llm_input,
            )
        )

        self.history['objective'] = llm_input.model_dump()
        self.history['result'] = synthesis_result.model_dump()
        logging.debug('finished synthesis')
        return synthesis_result
