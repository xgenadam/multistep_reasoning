"""Test suite for RollingDocumentUpdateSynthesiser class."""

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
from reasoning_sub_agents.execution_synthesiser.document_modification_synthesiser import (
    RollingDocumentUpdateSynthesiser,
)
from reasoning_sub_agents.execution_synthesiser.synthesis_tools import (
    WriteResult,
    ReplacePartResult,
    AppendResult,
    SynthesisReset,
)
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

class TestRollingDocumentUpdateSynthesiserInitialization:
    """Tests for RollingDocumentUpdateSynthesiser initialization."""

    def test_initialization_with_default_history(self):
        """Test RollingDocumentUpdateSynthesiser initialization with default history."""
        mock_client = MockOpenAI()
        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)
        assert synthesiser.llm_client == mock_client
        assert synthesiser.history == []
        assert synthesiser.exclude_individual_sub_task_results is True

    def test_initialization_with_custom_history(self):
        """Test RollingDocumentUpdateSynthesiser initialization with custom history."""
        mock_client = MockOpenAI()
        custom_history = [{'test': 'value'}]
        synthesiser = RollingDocumentUpdateSynthesiser(
            llm_client=mock_client,
            history=custom_history,
            exclude_individual_sub_task_results=False,
        )
        assert synthesiser.llm_client == mock_client
        assert synthesiser.history == custom_history
        assert synthesiser.exclude_individual_sub_task_results is False

@pytest.mark.skip(
    reason='RollingDocumentUpdateSynthesiser is unused and not registered; '
    'DocumentComposer replaces it'
)
class TestRollingDocumentUpdateSynthesiserSynthesize:
    """Tests for RollingDocumentUpdateSynthesiser.synthesize method."""

    def test_synthesize_first_task_no_previous_results(self):
        """Test synthesis when there are no previous accumulated results."""
        mock_client = MockOpenAI()
        # Return a JSON response with synthesis operations
        json_response = json.dumps([
            {"type": "write", "text": "First task result"}
        ])
        mock_client.set_return_values(json_response)

        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)

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
        assert "First task result" in result.chat_response.content
        assert len(synthesiser.history) == 1

    def test_synthesize_with_previous_results_append(self):
        """Test synthesis with append operation."""
        mock_client = MockOpenAI()
        json_response = json.dumps([
            {"type": "append", "text": " Appended content"}
        ])
        mock_client.set_return_values(json_response)

        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Task 1", "Result 1")
        task2 = create_test_sub_task("Task 2", "Result 2")

        prev_result = create_accumulated_result(task1, result_content="Previous result")
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
        # Should have appended to previous result
        assert "Previous result" in result.chat_response.content
        assert "Appended content" in result.chat_response.content

    def test_synthesize_with_previous_results_replace(self):
        """Test synthesis with replace operation."""
        mock_client = MockOpenAI()
        json_response = json.dumps([
            {"type": "replace_in_text", "search": "old text", "replace": "new text"}
        ])
        mock_client.set_return_values(json_response)

        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Task 1", "Result 1")
        task2 = create_test_sub_task("Task 2", "Result with old text")

        prev_result = create_accumulated_result(task1, result_content="old text")
        accumulated_results = [prev_result]

        result = synthesiser.synthesize(
            user_request="Complete the project",
            completed_sub_tasks=[task1],
            accumulated_results=accumulated_results,
            current_sub_task=task2,
            sub_tasks=[task1, task2],
        )

        assert isinstance(result, AccumulatedResult)
        assert "new text" in result.chat_response.content
        assert "old text" not in result.chat_response.content

    def test_synthesize_with_previous_results_write(self):
        """Test synthesis with write operation."""
        mock_client = MockOpenAI()
        json_response = json.dumps([
            {"type": "write", "text": "Completely new result"}
        ])
        mock_client.set_return_values(json_response)

        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Task 1", "Result 1")
        task2 = create_test_sub_task("Task 2", "Result 2")

        prev_result = create_accumulated_result(task1, result_content="Previous result")
        accumulated_results = [prev_result]

        result = synthesiser.synthesize(
            user_request="Complete the project",
            completed_sub_tasks=[task1],
            accumulated_results=accumulated_results,
            current_sub_task=task2,
            sub_tasks=[task1, task2],
        )

        assert isinstance(result, AccumulatedResult)
        # Write should completely replace the content
        assert result.chat_response.content == "Completely new result"

    def test_synthesize_with_synthesis_reset(self):
        """Test synthesis with SynthesisReset in response."""
        mock_client = MockOpenAI()
        # Response with reset followed by write
        json_response = json.dumps([
            {"type": "synthesis_reset", "content": "Resetting"},
            {"type": "write", "text": "Fresh start after reset"}
        ])
        mock_client.set_return_values(json_response)

        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Task 1", "Result 1")
        task2 = create_test_sub_task("Task 2", "Result 2")

        prev_result = create_accumulated_result(task1, result_content="Previous result")
        accumulated_results = [prev_result]

        result = synthesiser.synthesize(
            user_request="Complete the project",
            completed_sub_tasks=[task1],
            accumulated_results=accumulated_results,
            current_sub_task=task2,
            sub_tasks=[task1, task2],
        )

        assert isinstance(result, AccumulatedResult)
        # After reset, only the write should be applied
        assert result.chat_response.content == "Fresh start after reset"

    def test_synthesize_multiple_operations(self):
        """Test synthesis with multiple operations in sequence."""
        mock_client = MockOpenAI()
        json_response = json.dumps([
            {"type": "write", "text": "Initial text"},
            {"type": "append", "text": " Appended"},
            {"type": "replace_in_text", "search": "Initial", "replace": "Modified"}
        ])
        # Note: The filter_synthesis_response will only keep the WriteResult (first one)
        # and warn about subsequent WriteResults
        mock_client.set_return_values(json_response)

        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)

        task1 = create_test_sub_task("Task 1", "Result 1")
        task2 = create_test_sub_task("Task 2", "Result 2")

        prev_result = create_accumulated_result(task1, result_content="Previous")
        accumulated_results = [prev_result]

        result = synthesiser.synthesize(
            user_request="Complete the project",
            completed_sub_tasks=[task1],
            accumulated_results=accumulated_results,
            current_sub_task=task2,
            sub_tasks=[task1, task2],
        )

        assert isinstance(result, AccumulatedResult)

    def test_filter_synthesis_response_removes_reset_and_before(self):
        """Test that filter_synthesis_response removes items before last reset."""
        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=MockOpenAI())

        response = [
            WriteResult(text="First"),
            SynthesisReset(content="Reset"),
            WriteResult(text="After reset"),
            AppendResult(text=" More"),
        ]

        filtered = synthesiser.filter_synthesis_response(response)

        # Should only have WriteResult and AppendResult after the reset
        assert len(filtered) == 2
        assert isinstance(filtered[0], WriteResult)
        assert isinstance(filtered[1], AppendResult)

    def test_filter_synthesis_response_no_reset(self):
        """Test filter_synthesis_response with no reset."""
        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=MockOpenAI())

        response = [
            WriteResult(text="First"),
            AppendResult(text=" More"),
            ReplacePartResult(search="First", replace="Replaced"),
        ]

        filtered = synthesiser.filter_synthesis_response(response)

        # Should have all operations
        assert len(filtered) == 3
        assert isinstance(filtered[0], WriteResult)
        assert isinstance(filtered[1], AppendResult)
        assert isinstance(filtered[2], ReplacePartResult)

    def test_filter_synthesis_response_empty(self):
        """Test filter_synthesis_response with empty response."""
        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=MockOpenAI())

        response = []

        filtered = synthesiser.filter_synthesis_response(response)

        assert filtered == []

    def test_synthesize_handles_empty_synthesis_result(self):
        """Test synthesis when LLM returns empty list."""
        mock_client = MockOpenAI()
        mock_client.set_return_values(json.dumps([]))

        synthesiser = RollingDocumentUpdateSynthesiser(llm_client=mock_client)

        task = create_test_sub_task("Task 1")
        prev_result = create_accumulated_result(task, result_content="Previous")

        result = synthesiser.synthesize(
            user_request="Test",
            completed_sub_tasks=[],
            accumulated_results=[prev_result],
            current_sub_task=task,
            sub_tasks=[task],
        )

        # Should use previous result's content
        assert isinstance(result, AccumulatedResult)
        assert result.chat_response.content == "Previous"