"""Test suite for TaskOrchestrator class."""

import pytest
from openai.types.chat import ChatCompletionMessage
from unittest.mock import MagicMock

from reasoning_sub_agents.execution_synthesiser.document_composer import DocumentComposer
from reasoning_sub_agents.executor.oracle_loop_executor import OracleLoopExecutor
from reasoning_sub_agents.schemas import DecomposeSubTask, SubTask
from reasoning_sub_agents.task_decomposition.self_critique_decomposition import (
    SelfCritiquingDecomposition,
)
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator
from tests.mock_openai import MockOpenAI

class TestTaskOrchestratorInitialization:
    """Tests for TaskOrchestrator initialization."""

    def test_initialization_with_default_history(self):
        """Test TaskOrchestrator initialization with default history."""
        mock_decomposer = MagicMock()
        mock_executor = MagicMock()
        mock_synthesiser = MagicMock()
        mock_client = MockOpenAI()

        orchestrator = TaskOrchestrator(
            decomposer=mock_decomposer,
            agent_executor=mock_executor,
            result_synthesiser=mock_synthesiser,
            llm_client=mock_client,
        )

        assert orchestrator.decomposer == mock_decomposer
        assert orchestrator.agent_executor == mock_executor
        assert orchestrator.result_synthesiser == mock_synthesiser
        assert orchestrator.llm_client == mock_client
        assert orchestrator.history == []

    def test_initialization_with_custom_history(self):
        """Test TaskOrchestrator initialization with custom history."""
        mock_decomposer = MagicMock()
        mock_executor = MagicMock()
        mock_synthesiser = MagicMock()
        mock_client = MockOpenAI()
        custom_history = [{'test': 'value'}]

        orchestrator = TaskOrchestrator(
            decomposer=mock_decomposer,
            agent_executor=mock_executor,
            result_synthesiser=mock_synthesiser,
            llm_client=mock_client,
            history=custom_history,
        )

        assert orchestrator.history == custom_history

    def test_rejects_both_synthesiser_and_document_composer(self):
        mock_client = MockOpenAI()
        with pytest.raises(ValueError, match='Cannot provide both'):
            TaskOrchestrator(
                decomposer=MagicMock(),
                agent_executor=MagicMock(),
                result_synthesiser=MagicMock(),
                llm_client=mock_client,
                document_composer=MagicMock(),
            )

    def test_requires_a_composer_or_synthesiser(self):
        with pytest.raises(ValueError, match='Provide result_synthesiser or document_composer'):
            TaskOrchestrator(
                decomposer=MagicMock(),
                agent_executor=MagicMock(),
                llm_client=MockOpenAI(),
            )

class TestTaskOrchestratorInstantiate:
    """Tests for TaskOrchestrator.instantiate class method."""

    def test_instantiate_with_llm_client(self):
        """Test instantiate with llm_client parameter."""
        mock_client = MockOpenAI()

        orchestrator = TaskOrchestrator.instantiate(llm_client=mock_client)

        assert orchestrator.llm_client == mock_client
        assert isinstance(orchestrator.decomposer, SelfCritiquingDecomposition)
        assert isinstance(orchestrator.agent_executor, OracleLoopExecutor)
        assert isinstance(orchestrator.document_composer, DocumentComposer)
        assert orchestrator.result_synthesiser is None
        assert orchestrator.oracle_factory is not None
        assert orchestrator.history == []

    def test_instantiate_requires_config_or_client(self):
        """Test that instantiate raises ValueError without config or llm_client."""
        with pytest.raises(ValueError, match='Neither config nor llm_client provided'):
            TaskOrchestrator.instantiate()

    def test_instantiate_rejects_both_config_and_client(self):
        """Test that instantiate raises ValueError with both config and llm_client."""
        mock_client = MockOpenAI()
        config = {'key_word_args': {'--host': '127.0.0.1', '--port': '8000'}}

        with pytest.raises(ValueError, match='Cannot provide both config and llm_client'):
            TaskOrchestrator.instantiate(config=config, llm_client=mock_client)

class TestTaskOrchestratorQuery:
    """Tests for TaskOrchestrator.query method."""

    def test_query_basic_flow(self):
        """Test basic query flow through decomposition, execution, synthesis."""
        mock_client = MockOpenAI()
        mock_decomposer = MagicMock()
        mock_executor = MagicMock()
        mock_synthesiser = MagicMock()

        # Set up mock responses
        user_input = "Test user input"
        mock_sub_tasks = [
            SubTask(
                decomposed_sub_task=DecomposeSubTask(
                    meta_type='sub_task_detail',
                    name='Task 1',
                    type='test',
                    description='Test task',
                    context='Test',
                    complexity=1,
                    objective='Test objective',
                )
            )
        ]
        mock_decomposer.generate_sub_tasks.return_value = mock_sub_tasks

        mock_result = MagicMock()
        mock_result.chat_response = ChatCompletionMessage(content="Final result", role='assistant')
        mock_executor.execute_sub_tasks.return_value = mock_result

        orchestrator = TaskOrchestrator(
            decomposer=mock_decomposer,
            agent_executor=mock_executor,
            result_synthesiser=mock_synthesiser,
            llm_client=mock_client,
        )

        result = orchestrator.query(user_input)

        assert isinstance(result, ChatCompletionMessage)
        assert result.content == "Final result"
        assert len(orchestrator.history) == 1
        assert orchestrator.history[0]['user_input'] == user_input

    def test_query_returns_sub_tasks(self):
        """Test query with return_sub_tasks=True."""
        mock_client = MockOpenAI()
        mock_decomposer = MagicMock()
        mock_executor = MagicMock()
        mock_synthesiser = MagicMock()

        user_input = "Test user input"
        mock_sub_tasks = [
            SubTask(
                decomposed_sub_task=DecomposeSubTask(
                    meta_type='sub_task_detail',
                    name='Task 1',
                    type='test',
                    description='Test task',
                    context='Test',
                    complexity=1,
                    objective='Test objective',
                )
            )
        ]
        mock_decomposer.generate_sub_tasks.return_value = mock_sub_tasks

        mock_result = MagicMock()
        mock_result.chat_response = ChatCompletionMessage(content="Final result", role='assistant')
        mock_executor.execute_sub_tasks.return_value = mock_result

        orchestrator = TaskOrchestrator(
            decomposer=mock_decomposer,
            agent_executor=mock_executor,
            result_synthesiser=mock_synthesiser,
            llm_client=mock_client,
        )

        result = orchestrator.query(user_input, return_sub_tasks=True)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], ChatCompletionMessage)
        assert result[0].content == "Final result"
        assert result[1] == mock_result

    def test_query_multiple_calls_accumulates_history(self):
        """Test that multiple query calls accumulate history."""
        mock_client = MockOpenAI()
        mock_decomposer = MagicMock()
        mock_executor = MagicMock()
        mock_synthesiser = MagicMock()

        mock_sub_tasks = [
            SubTask(
                decomposed_sub_task=DecomposeSubTask(
                    meta_type='sub_task_detail',
                    name='Task 1',
                    type='test',
                    description='Test task',
                    context='Test',
                    complexity=1,
                    objective='Test objective',
                )
            )
        ]
        mock_decomposer.generate_sub_tasks.return_value = mock_sub_tasks

        mock_result = MagicMock()
        mock_result.chat_response = ChatCompletionMessage(content="Result", role='assistant')
        mock_executor.execute_sub_tasks.return_value = mock_result

        orchestrator = TaskOrchestrator(
            decomposer=mock_decomposer,
            agent_executor=mock_executor,
            result_synthesiser=mock_synthesiser,
            llm_client=mock_client,
        )

        orchestrator.query("Input 1")
        orchestrator.query("Input 2")
        orchestrator.query("Input 3")

        assert len(orchestrator.history) == 3
        assert orchestrator.history[0]['user_input'] == "Input 1"
        assert orchestrator.history[1]['user_input'] == "Input 2"
        assert orchestrator.history[2]['user_input'] == "Input 3"

    def test_query_history_includes_component_histories(self):
        """Test that query history includes decomposer, executor, and synthesiser histories."""
        mock_client = MockOpenAI()
        mock_decomposer = MagicMock()
        mock_executor = MagicMock()
        mock_synthesiser = MagicMock()

        mock_sub_tasks = [
            SubTask(
                decomposed_sub_task=DecomposeSubTask(
                    meta_type='sub_task_detail',
                    name='Task 1',
                    type='test',
                    description='Test task',
                    context='Test',
                    complexity=1,
                    objective='Test objective',
                )
            )
        ]
        mock_decomposer.generate_sub_tasks.return_value = mock_sub_tasks
        mock_decomposer.history = {'decomposer': 'history'}

        mock_result = MagicMock()
        mock_result.chat_response = ChatCompletionMessage(content="Result", role='assistant')
        mock_executor.execute_sub_tasks.return_value = mock_result
        mock_executor.history = {'executor': 'history'}

        mock_synthesiser.history = {'synthesiser': 'history'}

        orchestrator = TaskOrchestrator(
            decomposer=mock_decomposer,
            agent_executor=mock_executor,
            result_synthesiser=mock_synthesiser,
            llm_client=mock_client,
        )

        orchestrator.query("Test input")

        assert len(orchestrator.history) == 1
        history_entry = orchestrator.history[0]
        assert history_entry['user_input'] == "Test input"
        assert history_entry['decomposition_history'] == {'decomposer': 'history'}
        assert history_entry['execution_results'] == {'executor': 'history'}
        assert history_entry['synthesis_history'] == {'synthesiser': 'history'}