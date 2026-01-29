import json
import logging

from openai import OpenAI
from pydantic import TypeAdapter

from ..llama_utils import generate_simple_llm_input, get_streamed_json_response, get_streamed_boolean_decision
from ..schemas import DecomposeItem, DecomposeReset, DecomposeSubTask, SubTask
from .simple_decomposition import SimpleTaskDecomposer


logger = logging.getLogger(__name__)

SELF_CRITIQUE_PROMPT = """

"""


class SelfCritiquingDecomposition(SimpleTaskDecomposer):
    def generate_sub_tasks(self, user_input: str) -> list[SubTask]:
        sub_tasks = super().generate_sub_tasks(user_input=user_input)
        return sub_tasks


    def critique_sub_tasks(
            self,
            user_input: str,
            generated_sub_tasks: list[SubTask]
    ) -> list[SubTask]:
        pass

    def should_regenerate(self, user_input: str, criticism: str, sub_tasks: list[SubTask]) -> bool:
        pass

    def regenerate_sub_tasks(self, user_input: str, criticism: str, sub_tasks: list[SubTask]) -> list[SubTask]:
        pass