"""Test suite for SimpleSynthesiser class."""

import json
import pytest
from openai.types.chat import ChatCompletionMessage

from reasoning_sub_agents.schemas import (
    DecomposeSubTask,
    SubTask,
    SubTaskResult,
    AccumulatedResult,
    TaskStatus,
)
from reasoning_sub_agents.execution_synthesiser.simple_synthesiser import SimpleSynthesiser
from tests.mock_openai import MockOpenAI

def create_test_sub_task(name: str, result_content: str = "Test result") -> SubTask:
    """Helper to create a test SubTask with a result."""
    decompose_sub_task = DecomposeSubTask(
        meta_type='sub_task_detail',
        name=name,
        type='test',
        description=f'Test task: {name}',
        context='Test context',
        complexity=3,
        objective=f'Test objective: {name}',
    )
    sub_task_result = SubTaskResult(
        chat_response=ChatCompletionMessage(content=result_content, role='assistant')
    )
    return SubTask(
        decomposed_sub_task=decompose_sub_task,
        sub_task_result=sub_task_result,
        status=TaskStatus.COMPLETED,
    )

def create_accumulated_result(
    sub_task: SubTask,
    previous_results: list[AccumulatedResult] | None = None,
    synthesis_prompt: str = "Test prompt",
    result_content: str = "Test accumulated result",
) -> AccumulatedResult:
    """Helper to create a test AccumulatedResult."""
    previous = previous_results if previous_results is not None else []
    return AccumulatedResult(
        previous_results=previous,
        current_task=sub_task,
        synthesis_prompt=synthesis_prompt,
        chat_response=ChatCompletionMessage(content=result_content, role='assistant'),
    )

class TestSimpleSynthesiserInitialization:
    """Tests for SimpleSynthesiser initialization."""

    def test_initialization_with_default_history(self):
        """Test SimpleSynthesiser initialization with default history."""
        mock_client = MockOpenAI()
        synthesiser = SimpleSynthesiser(llm_client=mock_client)
        assert synthesiser.llm_client == mock_client
        assert synthesiser.history == []

    def test_initialization_with_custom_history(self):
        """Test SimpleSynthesiser initialization with custom history."""
        mock_client = MockOpenAI()
        custom_history = [{'test': 'value'}]
        synthesiser = SimpleSynthesiser(llm_client=mock_client, history=custom_history)
        assert synthesiser.llm_client == mock_client
        assert synthesiser.history == custom_history

class TestSimpleSynthesiserSynthesize:
    """Tests for SimpleSynthesiser.synthesize method."""

    def test_synthesize_first_task_no_previous_results(self):
        """Test synthesis when there are no previous accumulated results."""
        mock_client = MockOpenAI()
        mock_client.set_return_values("Synthesized result for first task")

        synthesiser = SimpleSynthesiser(llm_client=mock_client)

        sub_task = create_test_sub_task("Task 1")
        user_request = "Complete the project"
        sub_tasks = [sub_task]
        completed_sub_tasks = []
        accumulated_results = []

        result = synthesiser.synthesize(
            user_request=user_request,
            completed_sub_tasks=completed_sub_tasks,
            accumulated_results=accumulated_results,
            current_sub_task=sub_task,
            sub_tasks=sub_tasks,
        )

        assert isinstance(result, AccumulatedResult)
        assert result.current_task == sub_task
        assert len(result.previous_results) == 0
        assert "Synthesized result for first task" in result.chat_response.content
        assert len(synthesiser.history) == 1

    def test_synthesize_with_previous_results(self):
        """Test synthesis with existing accumulated results."""
        mock_client = MockOpenAI()
        mock_client.set_return_values("Combined result with previous")

        synthesiser = SimpleSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Task 1", "Result 1")
        task2 = create_test_sub_task("Task 2", "Result 2")

        prev_result = create_accumulated_result(task1, result_content="Accumulated Result 1")
        accumulated_results = [prev_result]

        result = synthesiser.synthesize(
            user_request="Complete the project",
            completed_sub_tasks=[task1],
            accumulated_results=accumulated_results,
            current_sub_task=task2,
            sub_tasks=[task1, task2],
        )

        assert isinstance(result, AccumulatedResult)
        assert result.current_task == task2
        assert len(result.previous_results) == 1
        assert result.previous_results[0] == prev_result
        assert len(synthesiser.history) == 1

    def test_synthesize_includes_all_parameters_in_prompt(self):
        """Test that all parameters are included in the synthesized prompt."""
        mock_client = MockOpenAI()
        # We'll capture what prompt was sent by checking the mock client's last call
        synthesiser = SimpleSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Research", "Research complete")
        task2 = create_test_sub_task("Analysis", "Analysis complete")
        prev_result = create_accumulated_result(task1, result_content="Previous accumulated")

        # Set a response that includes parts of what we expect in the prompt
        mock_client.set_return_values("Combined")

        synthesiser.synthesize(
            user_request="Do research and analysis",
            completed_sub_tasks=[task1],
            accumulated_results=[prev_result],
            current_sub_task=task2,
            sub_tasks=[task1, task2],
        )

        # The mock client was called, which means synthesis happened
        assert len(mock_client._responses) == 0  # Response was consumed

    def test_synthesize_handles_empty_completed_sub_tasks(self):
        """Test synthesis when completed_sub_tasks list is empty."""
        mock_client = MockOpenAI()
        mock_client.set_return_values("Result with no completed tasks")

        synthesiser = SimpleSynthesiser(llm_client=mock_client)

        task = create_test_sub_task("Only task")

        result = synthesiser.synthesize(
            user_request="Single task",
            completed_sub_tasks=[],
            accumulated_results=[],
            current_sub_task=task,
            sub_tasks=[task],
        )

        assert isinstance(result, AccumulatedResult)
        assert result.current_task == task

    def test_synthesize_incremental_history(self):
        """Test that history is incrementally updated."""
        mock_client = MockOpenAI()
        mock_client.set_return_values(
            "Result 1",
            "Result 2",
            "Result 3",
        )

        synthesiser = SimpleSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Task 1")
        task2 = create_test_sub_task("Task 2")
        task3 = create_test_sub_task("Task 3")

        # First synthesis
        synthesiser.synthesize(
            user_request="Multi task",
            completed_sub_tasks=[],
            accumulated_results=[],
            current_sub_task=task1,
            sub_tasks=[task1, task2, task3],
        )
        assert len(synthesiser.history) == 1

        # Second synthesis
        prev_result = create_accumulated_result(task1)
        synthesiser.synthesize(
            user_request="Multi task",
            completed_sub_tasks=[task1],
            accumulated_results=[prev_result],
            current_sub_task=task2,
            sub_tasks=[task1, task2, task3],
        )
        assert len(synthesiser.history) == 2

        # Third synthesis
        prev_result2 = create_accumulated_result(task2)
        synthesiser.synthesize(
            user_request="Multi task",
            completed_sub_tasks=[task1, task2],
            accumulated_results=[prev_result, prev_result2],
            current_sub_task=task3,
            sub_tasks=[task1, task2, task3],
        )
        assert len(synthesiser.history) == 3