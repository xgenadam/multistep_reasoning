from abc import ABC, abstractmethod

from ..schemas import AccumulatedResult, SubTask


class ExecutorSynthesiserBase(ABC):
    @abstractmethod
    def synthesize(
            self,
            user_request: str,
            completed_sub_tasks: list[SubTask],
            accumulated_results: list[AccumulatedResult],
            current_sub_task: SubTask,
            sub_tasks: list[SubTask],
    ) -> AccumulatedResult:
        pass
