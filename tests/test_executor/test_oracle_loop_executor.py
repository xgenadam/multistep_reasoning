from unittest.mock import MagicMock, patch

import pytest

from reasoning_sub_agents.document import AddPart, Document
from reasoning_sub_agents.executor.oracle_loop_executor import OracleLoopExecutor
from reasoning_sub_agents.oracle import DocumentOracle, ExecutorTurn, ListPartsTool
from reasoning_sub_agents.schemas import DecomposeSubTask, SubTask, TaskStatus
from tests.mock_openai import MockOpenAI


def _task(name: str = 'Write chapter 2') -> SubTask:
    return SubTask(
        decomposed_sub_task=DecomposeSubTask(
            meta_type='sub_task_detail',
            name=name,
            type='writing',
            description=name,
            context='ctx',
            complexity=3,
            objective=name,
        )
    )


def test_oracle_loop_queries_then_returns_result():
    doc = Document.empty()
    doc.apply(
        [
            AddPart(
                id='chapter-1',
                kind='section',
                title='Chapter 1',
                body='Hermione arrived at Hogwarts.',
            )
        ]
    )
    oracle = DocumentOracle(doc)
    executor = OracleLoopExecutor(llm_client=MockOpenAI(), max_oracle_rounds=4)
    task = _task()
    with patch(
        'reasoning_sub_agents.executor.oracle_loop_executor.get_streamed_json_response'
    ) as mock_json:
        mock_json.side_effect = [
            ExecutorTurn(tool_calls=[ListPartsTool()], result=None),
            ExecutorTurn(
                thinking='enough context',
                result='Chapter 2 continues at Hogwarts.',
            ),
        ]
        result = executor.execute_one(
            task, outline=doc.outline(), summary=doc.summary, oracle=oracle
        )
    assert result.status == TaskStatus.COMPLETED
    assert result.sub_task_result is not None
    assert (
        result.sub_task_result.chat_response.content
        == 'Chapter 2 continues at Hogwarts.'
    )
    assert mock_json.call_count == 2
    assert len(executor.history[0]['oracle_rounds']) == 1


def test_oracle_loop_requires_oracle():
    executor = OracleLoopExecutor(llm_client=MockOpenAI())
    with pytest.raises(TypeError, match='requires a DocumentOracle'):
        executor.execute_one(_task())


def test_oracle_loop_budget_exceeded():
    executor = OracleLoopExecutor(llm_client=MockOpenAI(), max_oracle_rounds=2)
    oracle = DocumentOracle(Document.empty())
    with patch(
        'reasoning_sub_agents.executor.oracle_loop_executor.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ExecutorTurn(
            tool_calls=[ListPartsTool()], result=None
        )
        with pytest.raises(RuntimeError, match='exceeded 2 rounds'):
            executor.execute_one(_task(), oracle=oracle)


def test_executor_turn_null_result_is_not_a_deliverable():
    turn = ExecutorTurn.model_validate(
        {'thinking': 'planning', 'tool_calls': None, 'result': None}
    )
    assert turn.result is None
    assert not turn.tool_calls
    nested = ExecutorTurn.model_validate({'result': {'result': None}})
    assert nested.result is None


def test_oracle_loop_retries_empty_result_then_succeeds():
    executor = OracleLoopExecutor(llm_client=MockOpenAI(), max_oracle_rounds=4)
    oracle = DocumentOracle(Document.empty())
    task = _task('Draft the intro')
    with patch(
        'reasoning_sub_agents.executor.oracle_loop_executor.get_streamed_json_response'
    ) as mock_json:
        mock_json.side_effect = [
            ExecutorTurn(thinking='still thinking', result=None),
            ExecutorTurn(result='Here is the introduction.'),
        ]
        result = executor.execute_one(task, oracle=oracle)
    assert result.sub_task_result.chat_response.content == 'Here is the introduction.'
    assert mock_json.call_count == 2
    assert executor.history[0]['oracle_rounds'][0]['observation'] == '(empty result; retrying)'


def test_execute_sub_tasks_not_supported():
    executor = OracleLoopExecutor(llm_client=MockOpenAI())
    with pytest.raises(TypeError, match='execute_sub_tasks'):
        executor.execute_sub_tasks('req', [], MagicMock())
