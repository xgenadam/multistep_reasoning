"""TaskOrchestrator's on_step observer and options.token_ceiling (Q-02, 2026-10-24).

on_step is logging only: it sees the plan and every Document state and
changes nothing. token_ceiling is off by default; when a turn's completion
tokens reach it, no further sub-task starts and the turn returns the
Document as it stands.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from openai.types.chat import ChatCompletionMessage

from reasoning_sub_agents.config.schema import OptionsConfig
from reasoning_sub_agents.document import AddPart
from reasoning_sub_agents.execution_synthesiser.document_composer import DocumentComposer
from reasoning_sub_agents.llama_utils import meter_completion
from reasoning_sub_agents.oracle import DocumentOracle
from reasoning_sub_agents.schemas import SubTaskResult, TaskStatus
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator
from tests.mock_openai import MockOpenAI
from tests.test_orchestrator.test_document_pipeline import _task

SPEND = 100  # completion tokens each sub-task's executor "spends"


def _orchestrator(n_tasks, options=None, on_step=None):
    tasks = [_task(f'Chapter {i + 1}') for i in range(n_tasks)]
    decomposer = MagicMock()
    decomposer.generate_sub_tasks.return_value = tasks
    decomposer.history = {'initial_tasks': [t.decomposed_sub_task.name for t in tasks]}
    executor = MagicMock()

    def run_one(sub_task, **kwargs):
        meter_completion(SimpleNamespace(completion_tokens=SPEND), '')  # what a real call adds
        sub_task.sub_task_result = SubTaskResult(chat_response=ChatCompletionMessage(
            content=f'Body of {sub_task.decomposed_sub_task.name}.', role='assistant'))
        sub_task.status = TaskStatus.COMPLETED
        return sub_task

    executor.execute_one.side_effect = run_one
    executor.history = []
    oracle = MagicMock(spec=DocumentOracle)
    oracle.update_summary.return_value = 'summary'
    orch = TaskOrchestrator(decomposer=decomposer, agent_executor=executor,
                            llm_client=MockOpenAI(),
                            document_composer=DocumentComposer(llm_client=MockOpenAI()),
                            oracle_factory=lambda document: oracle,
                            options=options, on_step=on_step)
    return orch, tasks


def _run(orch):
    from reasoning_sub_agents.execution_synthesiser.document_composer import ComposerResponse
    counter = {'n': 0}

    def fake_json(**kwargs):
        counter['n'] += 1
        i = counter['n']
        return ComposerResponse(ops=[AddPart(id=f'chapter-{i}', kind='section',
                                             title=f'Chapter {i}', body_source='current_result')])

    with patch('reasoning_sub_agents.execution_synthesiser.document_composer'
               '.get_streamed_json_response', side_effect=fake_json):
        return orch.query('Write a book', return_sub_tasks=True)


def test_on_step_sees_the_plan_and_every_document_state():
    events = []
    orch, _ = _orchestrator(3, on_step=lambda kind, payload: events.append((kind, payload)))
    _, accumulated = _run(orch)
    kinds = [k for k, _ in events]
    assert kinds == ['plan', 'document', 'document', 'document']
    plan = events[0][1]
    assert [t['name'] for t in plan['sub_tasks']] == ['Chapter 1', 'Chapter 2', 'Chapter 3']
    assert plan['decomposition_history'] == {'initial_tasks': ['Chapter 1', 'Chapter 2', 'Chapter 3']}
    docs = [p for k, p in events if k == 'document']
    assert [d['step'] for d in docs] == [1, 2, 3] and all(d['of'] == 3 for d in docs)
    assert [len(d['snapshot']['parts']) for d in docs] == [1, 2, 3]
    assert [d['completion_tokens'] for d in docs] == [100, 200, 300]
    assert docs[-1]['snapshot'] == accumulated.document_snapshot
    entry = orch.history[-1]
    assert entry['completion_tokens'] == 300 and entry['token_ceiling'] is None
    assert entry['estimated_calls'] == 0


def test_observer_errors_never_change_the_turn():
    def boom(kind, payload):
        raise RuntimeError('observer broke')
    orch, _ = _orchestrator(2, on_step=boom)
    _, accumulated = _run(orch)
    assert len(accumulated.document_snapshot['parts']) == 2


def test_token_ceiling_off_by_default_runs_every_sub_task():
    assert OptionsConfig().token_ceiling is None
    orch, tasks = _orchestrator(3)
    _run(orch)
    assert all(t.status == TaskStatus.COMPLETED for t in tasks)


def test_token_ceiling_stops_and_returns_the_document_as_it_stands():
    events = []
    orch, tasks = _orchestrator(4, options=OptionsConfig(token_ceiling=150, consolidation=True),
                                on_step=lambda kind, payload: events.append((kind, payload)))
    response, accumulated = _run(orch)
    # 100 after chapter 1 (under), 200 after chapter 2 (over): chapters 3 and 4 never start.
    assert [t.status for t in tasks] == [TaskStatus.COMPLETED, TaskStatus.COMPLETED,
                                         TaskStatus.PENDING, TaskStatus.PENDING]
    assert [p['title'] for p in accumulated.document_snapshot['parts']] == ['Chapter 1', 'Chapter 2']
    assert 'Body of Chapter 2.' in response.content
    assert orch.history[-1]['token_ceiling'] == {'ceiling': 150, 'spent': 200,
                                                 'completed_sub_tasks': 2,
                                                 'skipped': ['Chapter 3', 'Chapter 4']}
    # No consolidation pass after a ceiling stop.
    assert [p['step'] for k, p in events if k == 'document'] == [1, 2]


def test_document_steps_carry_the_result_and_that_steps_composer_attempts():
    events = []
    orch, _ = _orchestrator(2, on_step=lambda kind, payload: events.append((kind, payload)))
    _run(orch)
    docs = [p for k, p in events if k == 'document']
    assert [d['result'] for d in docs] == ['Body of Chapter 1.', 'Body of Chapter 2.']
    assert [[a['attempt'] for a in d['compose_attempts']] for d in docs] == [[1], [1]]
    assert docs[1]['compose_attempts'][0]['ops'][0]['id'] == 'chapter-2'


def test_a_failed_compose_is_recorded_before_the_turn_fails():
    import pytest
    from reasoning_sub_agents.execution_synthesiser.document_composer import ComposerResponse
    events = []
    orch, _ = _orchestrator(1, on_step=lambda kind, payload: events.append((kind, payload)))
    bad = ComposerResponse(ops=[AddPart(id='x', kind='section', title='X', body='not the result')])
    with patch('reasoning_sub_agents.execution_synthesiser.document_composer'
               '.get_streamed_json_response', return_value=bad), pytest.raises(Exception):
        orch.query('Write a book')
    kind, failed = events[-1]
    assert kind == 'compose_failed' and failed['step'] == 1
    assert failed['result'] == 'Body of Chapter 1.' and 'composer failed' in failed['error']
    assert len(failed['compose_attempts']) == 3 and all(a['error'] for a in failed['compose_attempts'])
