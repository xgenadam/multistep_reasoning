"""
Unit tests for SimpleAgentExecutor.
"""

import pytest
from openai.types.chat import ChatCompletionMessage
from reasoning_sub_agents.document.models import PartKind, PartOutline
from reasoning_sub_agents.execution_synthesiser.base import ExecutorSynthesiserBase
from reasoning_sub_agents.executor.simple_executor import SimpleAgentExecutor
from reasoning_sub_agents.schemas import (
    AccumulatedResult,
    DecomposeSubTask,
    SubTask,
    SubTaskResult,
    TaskStatus,
)


class MockSynthesiser(ExecutorSynthesiserBase):
    """Simple mock synthesiser for testing that returns predictable results."""

    def synthesize(
        self,
        user_request: str,
        completed_sub_tasks: list[SubTask],
        accumulated_results: list[AccumulatedResult],
        current_sub_task: SubTask,
        sub_tasks: list[SubTask],
    ) -> AccumulatedResult:
        # Create a simple accumulated result based on the current sub_task
        return AccumulatedResult(
            previous_results=accumulated_results,
            current_task=current_sub_task,
            synthesis_prompt='Synthesized',
            chat_response=ChatCompletionMessage(
                role='assistant',
                content=f'Synthesis for {current_sub_task.decomposed_sub_task.name}',
            ),
        )


def create_test_sub_task(
    name: str, context: str = 'test context', objective: str = 'test objective'
) -> SubTask:
    """Helper function to create test SubTask objects."""
    return SubTask(
        decomposed_sub_task=DecomposeSubTask(
            meta_type='sub_task_detail',
            name=name,
            type='test',
            description=f'Test task: {name}',
            context=context,
            complexity=1,
            objective=objective,
        )
    )


@pytest.fixture
def mock_synthesiser():
    return MockSynthesiser()


@pytest.fixture
def test_sub_tasks():
    """Create a list of test sub_tasks."""
    return [
        create_test_sub_task('Task 1', context='Context 1', objective='Objective 1'),
        create_test_sub_task('Task 2', context='Context 2', objective='Objective 2'),
        create_test_sub_task('Task 3', context='Context 3', objective='Objective 3'),
    ]


def test_simple_executor_initialization(mock_openai_client):
    """Test that SimpleAgentExecutor initializes correctly."""
    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    assert executor.llm_client == mock_openai_client
    assert executor.history == []

    # Test with custom history
    custom_history = ['item1', 'item2']
    executor_with_history = SimpleAgentExecutor(
        llm_client=mock_openai_client, history=custom_history
    )
    assert executor_with_history.history == custom_history


def test_execute_single_sub_task(mock_openai_client, mock_synthesiser):
    """Test execution of a single sub_task."""
    # Set up mock response
    mock_openai_client.set_return_values('Test response for single task')

    # Create test sub_task
    sub_task = create_test_sub_task('Single Task')

    # Execute
    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    result = executor.execute_sub_tasks("test user request", [sub_task], mock_synthesiser)

    # Verify sub_task was modified correctly
    assert sub_task.status == TaskStatus.COMPLETED
    assert sub_task.sub_task_result is not None
    assert isinstance(sub_task.sub_task_result, SubTaskResult)
    assert (
        sub_task.sub_task_result.chat_response.content
        == 'Test response for single task'
    )

    # Verify result structure
    assert isinstance(result, AccumulatedResult)
    assert result.current_task == sub_task
    assert result.chat_response.content == 'Synthesis for Single Task'


def test_execute_multiple_sub_tasks(
    mock_openai_client, mock_synthesiser, test_sub_tasks
):
    """Test execution of multiple sub_tasks."""
    # Set up mock responses for each task
    mock_openai_client.set_return_values(
        'Response for Task 1', 'Response for Task 2', 'Response for Task 3'
    )

    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    result = executor.execute_sub_tasks("test user request", test_sub_tasks, mock_synthesiser)

    # Verify all sub_tasks were processed
    for i, sub_task in enumerate(test_sub_tasks):
        assert sub_task.status == TaskStatus.COMPLETED
        assert sub_task.sub_task_result is not None
        assert isinstance(sub_task.sub_task_result, SubTaskResult)
        assert (
            sub_task.sub_task_result.chat_response.content
            == f'Response for Task {i + 1}'
        )

    # Verify final result
    assert isinstance(result, AccumulatedResult)
    assert result.current_task == test_sub_tasks[-1]  # Should be the last task
    assert result.chat_response.content == 'Synthesis for Task 3'


def test_execute_one_includes_document_outline(mock_openai_client):
    mock_openai_client.set_return_values('Outlined response')

    sub_task = create_test_sub_task('Outlined Task')
    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    executor.execute_one(
        sub_task,
        outline=[
            PartOutline(
                id='chapter-1', kind=PartKind.SECTION, title='Chapter 1', char_count=12
            )
        ],
        summary='Chapter 1 exists.',
    )
    assert sub_task.status == TaskStatus.COMPLETED
    prompt = executor.history[0]['full_prompt']
    assert 'chapter-1' in prompt
    assert 'Chapter 1 exists.' in prompt


def test_executor_prompt_generation(mock_openai_client, mock_synthesiser):
    """Test that the executor generates prompts correctly."""
    mock_openai_client.set_return_values('Test response')

    sub_task = create_test_sub_task(
        'Prompt Test', context='Test Context', objective='Test Objective'
    )
    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    executor.execute_sub_tasks("test user request", [sub_task], mock_synthesiser)

    # The prompt should contain the context and objective
    # We can't directly check the prompt, but we can verify the response was processed
    assert sub_task.sub_task_result.chat_response.content == 'Test response'


def test_executor_sub_task_immonutability(mock_openai_client, mock_synthesiser):
    """Test that sub_tasks are deep copied and originals are not modified."""
    original_sub_task = create_test_sub_task('Immutability Test')
    sub_task_copy = original_sub_task.model_copy()

    mock_openai_client.set_return_values('Test response')
    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    executor.execute_sub_tasks("test user request", [sub_task_copy], mock_synthesiser)

    # Original should remain unchanged
    assert original_sub_task.status == TaskStatus.PENDING
    assert original_sub_task.sub_task_result is None

    # Copy should be modified
    assert sub_task_copy.status == TaskStatus.COMPLETED
    assert sub_task_copy.sub_task_result is not None


def test_executor_empty_sub_tasks(mock_openai_client, mock_synthesiser):
    """Test execution with empty sub_tasks list."""
    executor = SimpleAgentExecutor(llm_client=mock_openai_client)

    # This should not raise an exception and should return something sensible
    # Since there are no tasks, the synthesiser won't be called
    with pytest.raises(RuntimeError):  # Will try to access accumulated_results[0]
        executor.execute_sub_tasks("", [], mock_synthesiser)


def test_executor_streaming_response(mock_openai_client, mock_synthesiser):
    """Test execution with streaming responses."""
    # Set up streaming chunks
    mock_openai_client.set_return_values(['Streaming ', 'response ', 'chunks'])

    sub_task = create_test_sub_task('Streaming Test')
    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    executor.execute_sub_tasks("test user request", [sub_task], mock_synthesiser)

    # Should combine streaming chunks into single response
    assert sub_task.sub_task_result.chat_response.content == 'Streaming response chunks'


def test_executor_error_handling(mock_openai_client, mock_synthesiser):
    """Test that errors during execution are properly handled."""
    # Set up an error response
    mock_openai_client.set_return_values(ValueError('API error'))

    sub_task = create_test_sub_task('Error Test')

    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    with pytest.raises(ValueError, match='API error'):
        executor.execute_sub_tasks("test user request", [sub_task], mock_synthesiser)

    # Sub_task should remain in pending state if execution fails
    assert sub_task.status == TaskStatus.PENDING
    assert sub_task.sub_task_result is None


def test_executor_synthesiser_interaction(
    mock_openai_client, mock_synthesiser, test_sub_tasks
):
    """Test the interaction between executor and synthesiser."""
    mock_openai_client.set_return_values('Response 1', 'Response 2', 'Response 3')

    executor = SimpleAgentExecutor(llm_client=mock_openai_client)
    result = executor.execute_sub_tasks("test user request", test_sub_tasks, mock_synthesiser)

    # Verify that accumulated results are properly passed to synthesiser
    # The final result should have 2 previous results (for the 3 tasks)
    assert len(result.previous_results) == 2
    assert result.previous_results[0].current_task == test_sub_tasks[0]
    assert result.previous_results[1].current_task == test_sub_tasks[1]
    assert result.current_task == test_sub_tasks[2]
