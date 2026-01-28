from abc import ABC, abstractmethod

from ..execution_synthesiser.base import ExecutorSynthesiserBase
from ..schemas import AccumulatedResult, SubTask


class ExecutorBase(ABC):
    @abstractmethod
    def execute_sub_tasks(
        self, user_request: str, sub_tasks: list[SubTask], synthesiser: ExecutorSynthesiserBase
    ) -> AccumulatedResult:
        pass
