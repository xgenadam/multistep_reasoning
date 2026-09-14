from abc import ABC, abstractmethod

from ..document.models import PartOutline
from ..execution_synthesiser.base import ExecutorSynthesiserBase
from ..oracle.document_oracle import DocumentOracle
from ..schemas import AccumulatedResult, SubTask


class ExecutorBase(ABC):
    @abstractmethod
    def execute_sub_tasks(
        self,
        user_request: str,
        sub_tasks: list[SubTask],
        synthesiser: ExecutorSynthesiserBase,
    ) -> AccumulatedResult:
        pass

    def execute_one(
        self,
        sub_task: SubTask,
        *,
        outline: list[PartOutline] | None = None,
        summary: str | None = None,
        oracle: DocumentOracle | None = None,
        user_request: str | None = None,
    ) -> SubTask:
        raise NotImplementedError(
            f'{type(self).__name__} does not implement execute_one'
        )
