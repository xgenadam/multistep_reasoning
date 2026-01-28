from abc import ABC, abstractmethod

from ..schemas import AccumulatedResult, SubTask
from ..execution_synthesiser.base import ExecutorSynthesiserBase


class ExecutorBase(ABC):

    @abstractmethod
    def execute_sub_tasks(
            self,
            sub_tasks: list[SubTask],
            synthesiser: ExecutorSynthesiserBase
    ) -> AccumulatedResult:
        pass
