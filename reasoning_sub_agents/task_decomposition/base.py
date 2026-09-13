from abc import ABC, abstractmethod

from ..schemas import SubTask


class TaskDecomposerBase(ABC):
    @abstractmethod
    def generate_sub_tasks(
        self, user_input: str, chat_context: str | None = None
    ) -> list[SubTask]:
        pass