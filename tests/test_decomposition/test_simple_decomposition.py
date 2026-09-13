"""Test suite for reasoning_sub_agents.task_decomposition module."""

import pytest
from reasoning_sub_agents.schemas import DecomposeReset, DecomposeSubTask, SubTask
from reasoning_sub_agents.task_decomposition.simple_decomposition import SimpleTaskDecomposer
from tests.mock_openai import MockOpenAI


def test_task_decomposer_initialization():
    """Test SimpleTaskDecomposer initialization with default and custom history."""
    mock_client = MockOpenAI()

    # Test with default history
    decomposer_default = SimpleTaskDecomposer(llm_client=mock_client)
    assert decomposer_default.history == {}
    assert decomposer_default.llm_client == mock_client

    # Test with custom history
    custom_history = {'test_key': 'test_value'}
    decomposer_custom = SimpleTaskDecomposer(llm_client=mock_client, history=custom_history)
    assert decomposer_custom.history == custom_history
    assert decomposer_custom.llm_client == mock_client


def test_generate_sub_tasks_integration(mock_openai_client):
    """Test the full generate_sub_tasks flow with mock responses."""
    # Import necessary models
    import unittest.mock

    from reasoning_sub_agents.schemas import DecomposeSubTask

    # Set up mock response with DecomposeSubTask items
    decompose_sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Research competitors',
        type='research',
        description='Research main competitors in the market',
        context='Understand competitive landscape',
        complexity=3,
        objective='Research the top 3 competitors and their market share',
    )

    decompose_sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Analyze findings',
        type='analysis',
        description='Analyze research findings',
        context='Extract insights from competitor research',
        complexity=2,
        objective='Create a summary analysis of competitor strengths and weaknesses',
    )

    # Mock the instructor call by patching the function where it's used
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
    ) as mock_get_streamed_json_response:
        mock_get_streamed_json_response.return_value = [
            decompose_sub_task_1,
            decompose_sub_task_2,
        ]

        # Initialize decomposer
        decomposer = SimpleTaskDecomposer(llm_client=mock_openai_client)
        user_input = 'Research competitors and analyze findings'

        # Call the method
        result = decomposer.generate_sub_tasks(user_input=user_input)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(task, SubTask) for task in result)

        # Verify sub_tasks have correct decomposed_sub_task
        assert result[0].decomposed_sub_task.name == 'Research competitors'
        assert result[1].decomposed_sub_task.name == 'Analyze findings'

        # Verify history is updated
        assert 'user_input' in decomposer.history
        assert decomposer.history['user_input'] == user_input
        assert 'initial_tasks' in decomposer.history
        assert len(decomposer.history['initial_tasks']) == 2


def test_generate_initial_sub_tasks(mock_openai_client):
    """Test generate_initial_sub_tasks method."""
    # Import necessary models
    import unittest.mock

    from reasoning_sub_agents.schemas import DecomposeSubTask

    # Set up mock response
    decompose_sub_task = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Write report',
        type='writing',
        description='Write a market research report',
        context='Create comprehensive market analysis',
        complexity=4,
        objective='Write a detailed market research report with insights',
    )

    # Mock the instructor call by patching the function where it's used
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
    ) as mock_get_streamed_json_response:
        mock_get_streamed_json_response.return_value = [decompose_sub_task]

        # Initialize decomposer
        decomposer = SimpleTaskDecomposer(llm_client=mock_openai_client)
        user_input = 'Write a comprehensive market research report'

        # Call the method
        result = decomposer.generate_initial_sub_tasks(user_input=user_input)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], SubTask)
        assert result[0].decomposed_sub_task.name == 'Write report'

        # Verify history is updated (note: generate_initial_sub_tasks doesn't store user_input)
        assert 'decomposition_prompt' in decomposer.history
        assert 'decompose_response' in decomposer.history
        assert 'initial_tasks' in decomposer.history
        # user_input is NOT stored by generate_initial_sub_tasks, only by generate_sub_tasks


def test_filter_decompose_response_no_reset():
    """Test filter_decompose_response when no reset items are present."""
    decomposer = SimpleTaskDecomposer(llm_client=MockOpenAI())

    # Create test data with only sub tasks
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 1',
        type='research',
        description='First task',
        context='Context 1',
        complexity=1,
        objective='Prompt 1',
    )

    sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 2',
        type='analysis',
        description='Second task',
        context='Context 2',
        complexity=2,
        objective='Prompt 2',
    )

    decomposition_response = [sub_task_1, sub_task_2]

    # Call the method
    result = decomposer.filter_decompose_response(decomposition_response)

    # Should return both sub tasks
    assert len(result) == 2
    assert all(isinstance(item, DecomposeSubTask) for item in result)
    assert result[0].name == 'Task 1'
    assert result[1].name == 'Task 2'


def test_filter_decompose_response_with_reset():
    """Test filter_decompose_response when reset items are present."""
    decomposer = SimpleTaskDecomposer(llm_client=MockOpenAI())

    # Create test data with reset in the middle
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Old Task 1',
        type='research',
        description='Old first task',
        context='Old context 1',
        complexity=1,
        objective='Old objective 1',
    )

    reset_item = DecomposeReset(
        meta_type='reset', reasoning='Need to restart decomposition'
    )

    sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 2',
        type='analysis',
        description='Second task',
        context='Context 2',
        complexity=2,
        objective='Prompt 2',
    )

    sub_task_3 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 3',
        type='writing',
        description='Third task',
        context='Context 3',
        complexity=3,
        objective='Prompt 3',
    )

    decomposition_response = [sub_task_1, reset_item, sub_task_2, sub_task_3]

    # Call the method
    result = decomposer.filter_decompose_response(decomposition_response)

    # Should return only tasks after the last reset
    assert len(result) == 2
    assert all(isinstance(item, DecomposeSubTask) for item in result)
    assert result[0].name == 'Task 2'
    assert result[1].name == 'Task 3'


def test_filter_decompose_response_multiple_resets():
    """Test filter_decompose_response with multiple reset items."""
    decomposer = SimpleTaskDecomposer(llm_client=MockOpenAI())

    # Create test data with multiple resets
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Old Task 1',
        type='research',
        description='Old first task',
        context='Old context 1',
        complexity=1,
        objective='Old objective 1',
    )

    reset_item_1 = DecomposeReset(meta_type='reset', reasoning='First reset')

    sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 2',
        type='analysis',
        description='Second task',
        context='Context 2',
        complexity=2,
        objective='Prompt 2',
    )

    reset_item_2 = DecomposeReset(meta_type='reset', reasoning='Second reset')

    sub_task_3 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 3',
        type='writing',
        description='Third task',
        context='Context 3',
        complexity=3,
        objective='Prompt 3',
    )

    sub_task_4 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 4',
        type='review',
        description='Fourth task',
        context='Context 4',
        complexity=2,
        objective='Prompt 4',
    )

    decomposition_response = [
        sub_task_1,
        reset_item_1,
        sub_task_2,
        reset_item_2,
        sub_task_3,
        sub_task_4,
    ]

    # Call the method
    result = decomposer.filter_decompose_response(decomposition_response)

    # Should return only tasks after the last reset
    assert len(result) == 2
    assert all(isinstance(item, DecomposeSubTask) for item in result)
    assert result[0].name == 'Task 3'
    assert result[1].name == 'Task 4'


def test_filter_decompose_response_no_reset_items():
    """Test filter_decompose_response when no reset items exist in response."""
    decomposer = SimpleTaskDecomposer(llm_client=MockOpenAI())

    # Test when ValueError is raised (no reset items)
    decomposition_response = []  # Empty list, no reset items

    # This should not raise an error, just return empty list
    result = decomposer.filter_decompose_response(decomposition_response)
    assert len(result) == 0


def test_create_sub_tasks():
    """Test create_sub_tasks method."""
    decomposer = SimpleTaskDecomposer(llm_client=MockOpenAI())

    # Create test decomposed sub tasks
    decomposed_sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Research',
        type='research',
        description='Conduct market research',
        context='Market analysis context',
        complexity=3,
        objective='Research the market thoroughly',
    )

    decomposed_sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Analysis',
        type='analysis',
        description='Analyze research data',
        context='Data analysis context',
        complexity=2,
        objective='Analyze the collected data',
    )

    decomposed_sub_tasks = [decomposed_sub_task_1, decomposed_sub_task_2]

    # Call the method
    result = decomposer.create_sub_tasks(decomposed_sub_tasks)

    # Verify results
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(task, SubTask) for task in result)
    assert result[0].decomposed_sub_task.name == 'Research'
    assert result[1].decomposed_sub_task.name == 'Analysis'
    assert result[0].meta_type == 'sub_task'  # Check meta_type
    assert result[1].meta_type == 'sub_task'  # Check meta_type
    assert result[0].status == 'pending'  # Default status
    assert result[1].status == 'pending'  # Default status


def test_decomposition_prompt_generation(mock_openai_client):
    """Test that the decomposition objective is correctly generated."""
    import unittest.mock

    # Mock the instructor call by patching the function where it's used
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
    ) as mock_get_streamed_json_response:
        mock_get_streamed_json_response.return_value = []

        decomposer = SimpleTaskDecomposer(llm_client=mock_openai_client)
        user_input = 'Test user input'

        # Call generate_initial_decomposition to trigger objective generation
        decomposer.generate_initial_decomposition(user_input=user_input)

        # Verify the objective was generated and stored in history
        assert 'decomposition_prompt' in decomposer.history
        prompt = decomposer.history['decomposition_prompt']

        # Verify objective contains expected elements
        assert user_input in prompt


def test_decomposition_prompt_includes_chat_context(mock_openai_client):
    import unittest.mock

    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
    ) as mock_get_streamed_json_response:
        mock_get_streamed_json_response.return_value = []
        decomposer = SimpleTaskDecomposer(llm_client=mock_openai_client)
        decomposer.generate_sub_tasks(
            user_input='Make chapter 3 darker',
            chat_context='User: write a book\nAssistant: Chapter 1...',
        )
        prompt = decomposer.history['decomposition_prompt']
        assert 'Previous conversation' in prompt
        assert 'Chapter 1...' in prompt
        assert 'Make chapter 3 darker' in prompt


def test_history_update_during_decomposition(mock_openai_client):
    """Test that history is properly updated during decomposition."""
    # Import necessary models
    import unittest.mock

    from reasoning_sub_agents.schemas import DecomposeSubTask

    # Set up mock response
    decompose_sub_task = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Test Task',
        type='test',
        description='Test description',
        context='Test context',
        complexity=1,
        objective='Test objective',
    )

    # Mock the instructor call by patching the function where it's used
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
    ) as mock_get_streamed_json_response:
        mock_get_streamed_json_response.return_value = [decompose_sub_task]

        # Initialize decomposer
        decomposer = SimpleTaskDecomposer(llm_client=mock_openai_client)
        user_input = 'Test decomposition'

        # Call the method that stores user_input in history
        decomposer.generate_sub_tasks(user_input=user_input)

        # Verify all expected history entries
        assert 'user_input' in decomposer.history
        assert decomposer.history['user_input'] == user_input

        assert 'decomposition_prompt' in decomposer.history
        assert isinstance(decomposer.history['decomposition_prompt'], str)

        assert 'decompose_response' in decomposer.history
        assert isinstance(decomposer.history['decompose_response'], list)

        assert 'initial_tasks' in decomposer.history
        assert isinstance(decomposer.history['initial_tasks'], list)
        assert len(decomposer.history['initial_tasks']) == 1


def test_empty_decomposition_response(mock_openai_client):
    """Test handling of empty decomposition response."""
    import unittest.mock

    # Mock the instructor call by patching the function where it's used
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
    ) as mock_get_streamed_json_response:
        mock_get_streamed_json_response.return_value = []

        decomposer = SimpleTaskDecomposer(llm_client=mock_openai_client)
        user_input = 'Test empty response'

        # Call the method that stores user_input in history
        result = decomposer.generate_sub_tasks(user_input=user_input)

        # Should return empty list
        assert isinstance(result, list)
        assert len(result) == 0

        # History should still be updated
        assert 'user_input' in decomposer.history
        assert decomposer.history['user_input'] == user_input
        assert 'decomposition_prompt' in decomposer.history
        assert 'decompose_response' in decomposer.history
        assert decomposer.history['decompose_response'] == []


def test_decomposition_with_mixed_items(mock_openai_client):
    """Test filtering when decomposition response contains mixed item types."""
    # Import necessary models
    import unittest.mock

    from reasoning_sub_agents.schemas import DecomposeReset, DecomposeSubTask

    # Mock the instructor call by patching the function where it's used
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
    ) as mock_get_streamed_json_response:
        # Create mixed items (including non-DecomposeSubTask items)
        sub_task_1 = DecomposeSubTask(
            meta_type='sub_task_detail',
            name='Task 1',
            type='research',
            description='First task',
            context='Context 1',
            complexity=1,
            objective='Prompt 1',
        )

        # This would be filtered out by filter_decompose_response
        reset_item = DecomposeReset(meta_type='reset', reasoning='Test reset')

        sub_task_2 = DecomposeSubTask(
            meta_type='sub_task_detail',
            name='Task 2',
            type='analysis',
            description='Second task',
            context='Context 2',
            complexity=2,
            objective='Prompt 2',
        )

        mock_get_streamed_json_response.return_value = [
            sub_task_1,
            reset_item,
            sub_task_2,
        ]

        decomposer = SimpleTaskDecomposer(llm_client=mock_openai_client)

        # Call the method that goes through the full flow
        result = decomposer.generate_initial_sub_tasks(user_input='Test mixed items')

        # Should only get sub tasks after filtering
        assert len(result) == 1  # sub_task_2 (after reset)
        assert result[0].decomposed_sub_task.name == 'Task 2'


if __name__ == '__main__':
    pytest.main([__file__])
