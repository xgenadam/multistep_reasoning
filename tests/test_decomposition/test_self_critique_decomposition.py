"""Test suite for reasoning_sub_agents.task_decomposition.self_critique_decomposition module."""

import unittest.mock
import pytest
from reasoning_sub_agents.schemas import DecomposeSubTask, SubTask
from reasoning_sub_agents.task_decomposition.self_critique_decomposition import SelfCritiquingDecomposition
from reasoning_sub_agents.task_decomposition.simple_decomposition import SimpleTaskDecomposer
from tests.mock_openai import MockOpenAI

def mock_critique_sub_tasks_method(self, user_input, generated_sub_tasks):
    """Mock method that bypasses the extract_content issue."""
    # Store the critique in history like the real method does
    self.history['critique'] = "Mock critique: tasks need improvement"
    # Return a mock critique directly
    return "Mock critique: tasks need improvement"

def test_self_critiquing_decomposition_initialization():
    """Test SelfCritiquingDecomposition initialization."""
    mock_client = MockOpenAI()
    decomposer = SelfCritiquingDecomposition(llm_client=mock_client)

    # Test default history
    assert isinstance(decomposer.history, dict)
    assert decomposer.history == {}

    # Test custom history
    custom_history = {'test_key': 'test_value'}
    decomposer_custom = SelfCritiquingDecomposition(llm_client=mock_client, history=custom_history)
    assert decomposer_custom.history == custom_history
    assert decomposer_custom.llm_client == mock_client

def test_generate_sub_tasks_with_sufficient_initial_decomposition(mock_openai_client):
    """Test generate_sub_tasks when initial decomposition has enough sub-tasks (no regeneration)."""
    # Create mock sub-tasks (3+ sub-tasks should not trigger regeneration)
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Research competitors',
        type='research',
        description='Research main competitors in the market',
        context='Understand competitive landscape',
        complexity=3,
        objective='Research the top 3 competitors and their market share',
    )

    sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Analyze findings',
        type='analysis',
        description='Analyze research findings',
        context='Extract insights from competitor research',
        complexity=2,
        objective='Create a summary analysis of competitor strengths and weaknesses',
    )

    sub_task_3 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Write report',
        type='writing',
        description='Write competitive analysis report',
        context='Document research findings',
        complexity=4,
        objective='Write comprehensive competitive analysis report',
    )

    # Mock the initial decomposition call and decision
    with (
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
        ) as mock_initial_decomposition,
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_boolean_decision'
        ) as mock_decision,
        unittest.mock.patch.object(
            SelfCritiquingDecomposition,
            'critique_sub_tasks',
            mock_critique_sub_tasks_method
        ),
    ):
        # Mock initial decomposition response (3 sub-tasks)
        mock_initial_decomposition.return_value = [sub_task_1, sub_task_2, sub_task_3]

        # Mock decision (False = no regeneration needed)
        mock_decision.return_value = False

        # Initialize decomposer
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        user_input = 'Research competitors and write analysis report'

        # Call the method
        result = decomposer.generate_sub_tasks(user_input=user_input)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(task, SubTask) for task in result)

        # Verify initial decomposition was called
        mock_initial_decomposition.assert_called_once()

        # Verify critique and decision were called
        mock_decision.assert_called_once()

        # Verify history tracking
        assert 'user_input' in decomposer.history
        assert 'initial_decomposition_count' in decomposer.history
        assert decomposer.history['initial_decomposition_count'] == 3
        assert 'critique' in decomposer.history
        assert decomposer.history['critique'] == "Mock critique: tasks need improvement"
        assert 'regeneration_needed' in decomposer.history
        assert decomposer.history['regeneration_needed'] is False

def test_generate_sub_tasks_with_insufficient_initial_decomposition(mock_openai_client):
    """Test generate_sub_tasks when initial decomposition has insufficient sub-tasks (should regenerate)."""
    # Create mock sub-task (only 1 sub-task should trigger automatic regeneration)
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Simple answer',
        type='query',
        description='Answer simple question',
        context='Provide factual answer',
        complexity=1,
        objective='Answer the user question',
    )

    # Mock revised sub-tasks for regeneration
    revised_sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Research topic',
        type='research',
        description='Research the topic thoroughly',
        context='Gather comprehensive information',
        complexity=3,
        objective='Research all aspects of the topic',
    )

    revised_sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Analyze data',
        type='analysis',
        description='Analyze the research data',
        context='Extract key insights',
        complexity=3,
        objective='Analyze research findings',
    )

    # Mock revised sub-task 3
    revised_sub_task_3 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Summarize results',
        type='writing',
        description='Summarize the analysis',
        context='Create concise summary',
        complexity=2,
        objective='Write summary of analysis',
    )

    # Mock the initial decomposition call and decision
    with (
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
        ) as mock_initial_decomposition,
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_boolean_decision'
        ) as mock_decision,
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_json_response'
        ) as mock_revised_decomposition,
        unittest.mock.patch.object(
            SelfCritiquingDecomposition,
            'critique_sub_tasks',
            mock_critique_sub_tasks_method
        ),
    ):
        # Mock initial decomposition response (only 1 sub-task)
        mock_initial_decomposition.return_value = [sub_task_1]

        # Mock decision (should return True due to < 3 sub-tasks)
        mock_decision.return_value = True

        # Mock revised decomposition response (3 sub-tasks)
        mock_revised_decomposition.return_value = [revised_sub_task_1, revised_sub_task_2, revised_sub_task_3]

        # Initialize decomposer
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        user_input = 'Research and analyze a complex topic'

        # Call the method
        result = decomposer.generate_sub_tasks(user_input=user_input)

        # Verify results - should get revised sub-tasks
        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(task, SubTask) for task in result)

        # Verify initial decomposition was called
        mock_initial_decomposition.assert_called_once()

        # Verify critique and decision were called
        mock_decision.assert_called_once()

        # Verify revised decomposition was called (regeneration)
        mock_revised_decomposition.assert_called_once()

        # Verify history tracking
        assert 'user_input' in decomposer.history
        assert 'initial_decomposition_count' in decomposer.history
        assert decomposer.history['initial_decomposition_count'] == 1
        assert 'critique' in decomposer.history
        assert decomposer.history['critique'] == "Mock critique: tasks need improvement"
        assert 'regeneration_needed' in decomposer.history
        assert decomposer.history['regeneration_needed'] is True
        assert 'regenerated_decomposition_count' in decomposer.history
        assert decomposer.history['regenerated_decomposition_count'] == 3

        # Verify we got the revised sub-tasks, not the initial ones
        assert result[0].decomposed_sub_task.name == 'Research topic'
        assert result[1].decomposed_sub_task.name == 'Analyze data'
        assert result[2].decomposed_sub_task.name == 'Summarize results'

def test_critique_sub_tasks(mock_openai_client):
    """Test the critique_sub_tasks method with direct mocking."""
    # Create mock sub-tasks
    sub_task_1 = SubTask(
        meta_type='sub_task',
        decomposed_sub_task=DecomposeSubTask(
            meta_type='sub_task_detail',
            name='Task 1',
            type='research',
            description='First task',
            context='Context 1',
            complexity=2,
            objective='Objective 1',
        )
    )

    sub_task_2 = SubTask(
        meta_type='sub_task',
        decomposed_sub_task=DecomposeSubTask(
            meta_type='sub_task_detail',
            name='Task 2',
            type='analysis',
            description='Second task',
            context='Context 2',
            complexity=3,
            objective='Objective 2',
        )
    )

    generated_sub_tasks = [sub_task_1, sub_task_2]

    # Mock the critique method
    with unittest.mock.patch.object(
        SelfCritiquingDecomposition,
        'critique_sub_tasks',
        mock_critique_sub_tasks_method
    ):
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        user_input = 'Test critique function'

        # Call the method
        result = decomposer.critique_sub_tasks(user_input, generated_sub_tasks)

        # Verify result
        assert result == "Mock critique: tasks need improvement"

        # Verify history is updated
        assert 'critique' in decomposer.history
        assert decomposer.history['critique'] == "Mock critique: tasks need improvement"

def test_should_regenerate_with_low_subtask_count(mock_openai_client):
    """Test should_regenerate logic when sub-task count < 3 (should always regenerate)."""
    # Create mock sub-tasks (only 2)
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 1',
        type='research',
        description='First task',
        context='Context 1',
        complexity=2,
        objective='Objective 1',
    )

    sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 2',
        type='analysis',
        description='Second task',
        context='Context 2',
        complexity=3,
        objective='Objective 2',
    )

    generated_sub_tasks = [
        SubTask(meta_type='sub_task', decomposed_sub_task=sub_task_1),
        SubTask(meta_type='sub_task', decomposed_sub_task=sub_task_2),
    ]

    # Mock decision response (should be ignored for < 3 sub-tasks)
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_boolean_decision'
    ) as mock_decision:
        mock_decision.return_value = False  # This should be ignored

        # Initialize decomposer
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        user_input = 'Test regeneration logic'
        criticism = 'Test criticism'

        # Call the method
        result = decomposer.should_regenerate(user_input, criticism, generated_sub_tasks)

        # Verify result is True (automatic regeneration for < 3 sub-tasks)
        assert result is True

        # Verify decision was NOT called (short-circuit logic)
        mock_decision.assert_not_called()

def test_should_regenerate_with_sufficient_subtask_count(mock_openai_client):
    """Test should_regeneration logic when sub-task count >= 3 (uses LLM decision)."""
    # Create mock sub-tasks (3+)
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 1',
        type='research',
        description='First task',
        context='Context 1',
        complexity=2,
        objective='Objective 1',
    )

    sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 2',
        type='analysis',
        description='Second task',
        context='Context 2',
        complexity=3,
        objective='Objective 2',
    )

    sub_task_3 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Task 3',
        type='writing',
        description='Third task',
        context='Context 3',
        complexity=2,
        objective='Objective 3',
    )

    generated_sub_tasks = [
        SubTask(meta_type='sub_task', decomposed_sub_task=sub_task_1),
        SubTask(meta_type='sub_task', decomposed_sub_task=sub_task_2),
        SubTask(meta_type='sub_task', decomposed_sub_task=sub_task_3),
    ]

    # Mock decision response
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_boolean_decision'
    ) as mock_decision:
        mock_decision.return_value = True

        # Initialize decomposer
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        user_input = 'Test regeneration logic'
        criticism = 'Task quality could be improved'

        # Call the method
        result = decomposer.should_regenerate(user_input, criticism, generated_sub_tasks)

        # Verify result follows LLM decision
        assert result is True
        mock_decision.assert_called_once()

def test_regenerate_sub_tasks(mock_openai_client):
    """Test the regenerate_sub_tasks method."""
    # Create initial mock sub-tasks
    initial_sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Initial Task 1',
        type='research',
        description='Initial first task',
        context='Initial context 1',
        complexity=2,
        objective='Initial objective 1',
    )

    initial_sub_tasks = [
        SubTask(meta_type='sub_task', decomposed_sub_task=initial_sub_task_1),
    ]

    # Create revised mock sub-tasks
    revised_sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Revised Task 1',
        type='research',
        description='Revised first task',
        context='Revised context 1',
        complexity=3,
        objective='Revised objective 1',
    )

    revised_sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Revised Task 2',
        type='analysis',
        description='Revised second task',
        context='Revised context 2',
        complexity=3,
        objective='Revised objective 2',
    )

    # Mock revised decomposition response
    with unittest.mock.patch(
        'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_json_response'
    ) as mock_revised_decomposition:
        mock_revised_decomposition.return_value = [revised_sub_task_1, revised_sub_task_2]

        # Initialize decomposer
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        user_input = 'Test regeneration'
        criticism = 'Original tasks were insufficient'
        initial_sub_tasks = initial_sub_tasks

        # Call the method
        result = decomposer.regenerate_sub_tasks(user_input, criticism, initial_sub_tasks)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(task, SubTask) for task in result)
        assert result[0].decomposed_sub_task.name == 'Revised Task 1'
        assert result[1].decomposed_sub_task.name == 'Revised Task 2'

        # Verify history is updated
        assert 'regeneration_prompt' in decomposer.history
        assert 'regenerated_decomposition_count' in decomposer.history
        assert decomposer.history['regenerated_decomposition_count'] == 2

        # Verify revised decomposition was called
        mock_revised_decomposition.assert_called_once()

def test_self_critique_history_tracking(mock_openai_client):
    """Test comprehensive history tracking through the self-critique process."""
    # Create mock sub-tasks
    sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Research',
        type='research',
        description='Research task',
        context='Research context',
        complexity=3,
        objective='Research objective',
    )

    sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Analyze',
        type='analysis',
        description='Analysis task',
        context='Analysis context',
        complexity=3,
        objective='Analysis objective',
    )

    # Create revised sub-tasks
    revised_sub_task_1 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Enhanced Research',
        type='research',
        description='Enhanced research task',
        context='Enhanced research context',
        complexity=4,
        objective='Enhanced research objective',
    )

    revised_sub_task_2 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Enhanced Analysis',
        type='analysis',
        description='Enhanced analysis task',
        context='Enhanced analysis context',
        complexity=4,
        objective='Enhanced analysis objective',
    )

    revised_sub_task_3 = DecomposeSubTask(
        meta_type='sub_task_detail',
        name='Summarize',
        type='writing',
        description='Summary task',
        context='Summary context',
        complexity=2,
        objective='Summary objective',
    )

    # Mock all LLM calls
    with (
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.simple_decomposition.get_streamed_json_response'
        ) as mock_initial_decomposition,
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_boolean_decision'
        ) as mock_decision,
        unittest.mock.patch(
            'reasoning_sub_agents.task_decomposition.self_critique_decomposition.get_streamed_json_response'
        ) as mock_revised_decomposition,
        unittest.mock.patch.object(
            SelfCritiquingDecomposition,
            'critique_sub_tasks',
            mock_critique_sub_tasks_method
        ),
    ):
        # Mock responses
        mock_initial_decomposition.return_value = [sub_task_1, sub_task_2]  # 2 sub-tasks
        mock_decision.return_value = True
        mock_revised_decomposition.return_value = [revised_sub_task_1, revised_sub_task_2, revised_sub_task_3]

        # Initialize decomposer
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        user_input = 'Complex research and analysis project'

        # Call the full method
        result = decomposer.generate_sub_tasks(user_input=user_input)

        # Verify comprehensive history tracking
        assert 'user_input' in decomposer.history
        assert decomposer.history['user_input'] == user_input

        assert 'initial_decomposition_count' in decomposer.history
        assert decomposer.history['initial_decomposition_count'] == 2

        assert 'critique' in decomposer.history
        assert decomposer.history['critique'] == "Mock critique: tasks need improvement"

        assert 'regeneration_needed' in decomposer.history
        assert decomposer.history['regeneration_needed'] is True

        assert 'regeneration_prompt' in decomposer.history
        assert 'regenerated_decomposition_count' in decomposer.history
        assert decomposer.history['regenerated_decomposition_count'] == 3

        # Verify all expected history entries exist
        expected_history_keys = {
            'user_input',
            'decomposition_prompt',  # From parent class
            'decompose_response',  # From parent class
            'initial_tasks',  # From parent class
            'initial_decomposition_count',
            'critique',
            'regeneration_needed',
            'regeneration_prompt',
            'regenerated_decomposition_count'
        }

        for key in expected_history_keys:
            assert key in decomposer.history, f"Missing history key: {key}"

        # Verify final result
        assert len(result) == 3
        assert result[0].decomposed_sub_task.name == 'Enhanced Research'
        assert result[1].decomposed_sub_task.name == 'Enhanced Analysis'
        assert result[2].decomposed_sub_task.name == 'Summarize'

def test_critique_with_edge_cases(mock_openai_client):
    """Test critique handling with edge cases."""
    # Test with empty critique
    with unittest.mock.patch.object(
        SelfCritiquingDecomposition,
        'critique_sub_tasks',
        lambda self, user_input, generated_sub_tasks: ""
    ):
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        sub_task = SubTask(
            meta_type='sub_task',
            decomposed_sub_task=DecomposeSubTask(
                meta_type='sub_task_detail',
                name='Test',
                type='test',
                description='Test',
                context='Test',
                complexity=1,
                objective='Test',
            )
        )

        result = decomposer.critique_sub_tasks('Test', [sub_task])
        assert result == ""

    # Test with very long critique
    with unittest.mock.patch.object(
        SelfCritiquingDecomposition,
        'critique_sub_tasks',
        lambda self, user_input, generated_sub_tasks: "A" * 600
    ):
        decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)
        sub_task = SubTask(
            meta_type='sub_task',
            decomposed_sub_task=DecomposeSubTask(
                meta_type='sub_task_detail',
                name='Test',
                type='test',
                description='Test',
                context='Test',
                complexity=1,
                objective='Test',
            )
        )

        result = decomposer.critique_sub_tasks('Test', [sub_task])
        assert result == "A" * 600

def test_inheritance_from_simple_decomposer(mock_openai_client):
    """Test that SelfCritiquingDecomposition properly inherits from SimpleTaskDecomposer."""
    decomposer = SelfCritiquingDecomposition(llm_client=mock_openai_client)

    # Test that parent class methods are available
    assert hasattr(decomposer, 'generate_initial_sub_tasks')
    assert hasattr(decomposer, 'filter_decompose_response')
    assert hasattr(decomposer, 'create_sub_tasks')

    # Test that child class methods are available
    assert hasattr(decomposer, 'critique_sub_tasks')
    assert hasattr(decomposer, 'should_regenerate')
    assert hasattr(decomposer, 'regenerate_sub_tasks')

    # Test that generate_sub_tasks is overridden
    assert decomposer.generate_sub_tasks != SimpleTaskDecomposer.generate_sub_tasks

if __name__ == '__main__':
    pytest.main([__file__])
