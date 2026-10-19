"""Per-turn attribution is exact under concurrent scenarios (0-14, N14/N15/N16).

Three scenarios run at ``jobs=3`` against a fake server whose barrier makes
them call in lockstep, so their calls interleave in the global call order.
Every fake reply carries a prompt-token count unique to the turn that sent
it: a call attributed to the wrong turn shows up as a foreign tag.
"""

import threading
from types import SimpleNamespace

import pytest

from reasoning_sub_agents.progress import llm_step
from reasoning_sub_agents.schemas import TaskStatus

N_SCENARIOS = 3
TURNS = 2
# (status event, [(llm_step label, streamed)]): the orchestrator's real
# status texts, one call per llm_step.
PLAN = [
    ('Decomposing the request into sub-tasks…',
     [('Initial decomposition (JSON)', False), ('Critique decomposition', True)]),
    ('Decomposed 1 sub-tasks: a', []),
    ('Executing 1/1: a', [('Execute a (turn 1)', False), ('Oracle ask', False),
                          ('Execute a (turn 2)', False)]),
    ('Composing after 1/1: a', [('Compose document ops (JSON)', False)]),
    ('Updating summary after 1/1: a', [('Rolling summary', True)]),
    ('Consolidating document', [('Consolidate document ops (JSON)', False)]),
    ('Updating summary after consolidation', [('Rolling summary', True)]),
]
CALLS_PER_TURN = sum(len(calls) for _, calls in PLAN)
EXPECTED_KINDS = {
    'decompose': 1, 'decompose_critique': 1, 'executor_turn': 2, 'oracle': 1,
    'compose': 1, 'summary': 2, 'consolidate': 1,
}


def _tag(scenario: int, turn: int) -> int:
    """Prompt tokens the fake server reports for this turn's calls."""
    return 1000 * (scenario + 1) + turn


class FakeCompletions:
    """chat.completions stand-in: lockstep barrier, tagged usage."""

    def __init__(self, parties: int, usage_on_stream: bool = True):
        self.barrier = threading.Barrier(parties) if parties > 1 else None
        self.usage_on_stream = usage_on_stream
        self.requests: list[dict] = []
        self._lock = threading.Lock()

    def create(self, **kwargs):
        with self._lock:
            self.requests.append(kwargs)
        if self.barrier is not None:
            self.barrier.wait(timeout=10)
        tag = int(kwargs['messages'][0]['content'])
        usage = SimpleNamespace(prompt_tokens=tag, completion_tokens=1)
        if not kwargs.get('stream'):
            choice = SimpleNamespace(message=SimpleNamespace(content='{}'), finish_reason='stop')
            return SimpleNamespace(choices=[choice], usage=usage)
        include = (kwargs.get('stream_options') or {}).get('include_usage')
        return self._stream(usage if include and self.usage_on_stream else None)

    @staticmethod
    def _stream(usage):
        for text, finish in (('sum', None), ('mary', 'stop')):
            delta = SimpleNamespace(content=text)
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=None
            )
        if usage is not None:
            yield SimpleNamespace(choices=[], usage=usage)


class FakeExecutor:
    def __init__(self):
        self.history: list = []

    def execute_one(self, sub_task, **kwargs):
        sub_task.status = TaskStatus.COMPLETED
        self.history.append({'completed_sub_task': {'status': 'completed'}})
        return sub_task


class FakeOrchestrator:
    """Yields the orchestrator's status sequence and calls under llm_step."""

    def __init__(self, client, scenario: int):
        self.client = client
        self.scenario = scenario
        self.history: list = []
        self.agent_executor = FakeExecutor()

    def iter_query(self, text, document=None, turn_id=None):
        turn = int(text)
        for status, calls in PLAN:
            yield ('status', status)
            if status.startswith('Executing'):
                self.agent_executor.execute_one(SimpleNamespace(status=None))
            for label, streamed in calls:
                with llm_step(label):
                    resp = self.client.chat.completions.create(
                        model='llama',
                        messages=[{'role': 'user', 'content': str(_tag(self.scenario, turn))}],
                        stream=streamed,
                    )
                    if streamed:
                        # The pipeline indexes choices[0] on every chunk it sees.
                        ''.join(c.choices[0].delta.content for c in resp)
        self.history.append({'execution_results': self.agent_executor.history})
        yield ('done', SimpleNamespace(document_snapshot={'parts': [], 'op_log': []}))


def _scenarios():
    return [
        {'id': f'fake{s}', 'turns': [{'text': str(t)} for t in range(TURNS)]}
        for s in range(N_SCENARIOS)
    ]


def _run(harness, n_jobs: int, usage_on_stream: bool = True):
    fake = FakeCompletions(parties=n_jobs, usage_on_stream=usage_on_stream)
    measured = harness.MeasuredCompletions(fake)
    client = SimpleNamespace(chat=SimpleNamespace(completions=measured))
    scenarios = _scenarios()
    results: list = [None] * len(scenarios)
    errors: list[str] = []

    def work(i, scenario):
        try:
            results[i] = harness.run_scenario(
                scenario, client, measured, 0,
                build_orchestrator=lambda: FakeOrchestrator(client, i),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(repr(exc))

    harness.run_jobs(scenarios, work, n_jobs)
    assert not errors
    return fake, measured, results


def test_per_turn_stats_are_exact_at_jobs_3(harness):
    fake, measured, results = _run(harness, n_jobs=3)

    records = measured.all_records()
    assert len(records) == N_SCENARIOS * TURNS * CALLS_PER_TURN
    # The calls really interleaved: the old global-counter slice of a turn
    # (its first to last call index) holds calls from other turns.
    first_turn = [r for r in records if r.turn == records[0].turn]
    old_slice = measured.records_between(first_turn[0].index, first_turn[-1].index + 1)
    assert {r.turn for r in old_slice} != {records[0].turn}

    for s, rec in enumerate(results):
        for t, turn in enumerate(rec['turns']):
            tag = _tag(s, t)
            calls = turn['calls']
            assert turn['turn_id'] == f'fake{s}#r0:t{t}'
            assert len(calls) == CALLS_PER_TURN
            # No call from a concurrent turn: every tag is this turn's.
            assert {c['prompt_tokens'] for c in calls} == {tag}
            assert turn['llm']['prompt_tokens'] == tag * CALLS_PER_TURN
            assert turn['llm']['completion_tokens'] == CALLS_PER_TURN

    summary = harness.attribution_summary(measured, results)
    assert summary['calls_unattributed'] == 0
    assert summary['calls_in_turns'] == summary['calls'] == len(records)
    assert summary['prompt_tokens_in_turns'] == summary['prompt_tokens']
    assert summary['completion_tokens_in_turns'] == summary['completion_tokens']
    # Jobs ran in copied contexts: nothing leaked into the caller's.
    assert harness._current_turn.get() is None


def test_every_call_is_phase_labelled(harness):
    _, _, results = _run(harness, n_jobs=3)
    for rec in results:
        for turn in rec['turns']:
            llm = turn['llm']
            assert llm['label_sources'] == {'phase': CALLS_PER_TURN}
            kinds = {k: v['count'] for k, v in llm['by_kind'].items()}
            assert kinds == EXPECTED_KINDS
            assert sum(kinds.values()) == llm['calls']
            # Per-kind token sums (llm_stats item 6) add up to the turn.
            assert sum(v['prompt_tokens'] for v in llm['by_kind'].values()) == llm['prompt_tokens']
            cons_summary = llm['by_phase'][harness.CONSOLIDATION_SUMMARY_PHASE]
            assert cons_summary['count'] == 1


def test_streamed_calls_carry_usage(harness):
    fake, _, results = _run(harness, n_jobs=1)
    streamed = [r for r in fake.requests if r.get('stream')]
    assert streamed and all(
        r['stream_options'] == {'include_usage': True} for r in streamed
    )
    llm = results[0]['turns'][0]['llm']
    assert llm['streamed_calls'] == 3
    assert llm['calls_without_usage'] == 0
    assert llm['tokens_partial'] is False
    for call in results[0]['turns'][0]['calls']:
        assert call['usage_reported'] is True


def test_server_without_stream_usage_marks_totals_partial(harness):
    _, _, results = _run(harness, n_jobs=1, usage_on_stream=False)
    llm = results[0]['turns'][0]['llm']
    assert llm['calls_without_usage'] == llm['streamed_calls'] == 3
    assert llm['tokens_partial'] is True
    streamed = [c for c in results[0]['turns'][0]['calls'] if c['stream']]
    assert all(c['prompt_tokens'] is None and not c['usage_reported'] for c in streamed)


def test_sub_task_statuses_are_real(harness):
    class Executor:
        def __init__(self):
            self.history = []

        def execute_one(self, sub_task, **kwargs):
            if sub_task.name == 'boom':
                raise RuntimeError('executor failed')
            sub_task.status = TaskStatus.COMPLETED
            entry = {'completed_sub_task': {'status': 'completed'}}
            if sub_task.name == 'slow':
                entry['budget_exhausted'] = True
            self.history.append(entry)
            return sub_task

    executor = Executor()
    statuses = harness.track_sub_task_statuses(executor)
    for name in ('ok', 'slow', 'boom'):
        try:
            executor.execute_one(SimpleNamespace(name=name, status=TaskStatus.PENDING))
        except RuntimeError:
            pass
    assert statuses == ['completed', 'budget_exhausted', 'failed']

    health = harness.turn_health({'execution_results': executor.history}, statuses)
    assert health['exec_status_counts'] == {'completed': 1, 'budget_exhausted': 1, 'failed': 1}
    # Without the tracker the history still gives real values (no failures).
    fallback = harness.turn_health({'execution_results': executor.history})
    assert fallback['exec_status_counts'] == {'completed': 1, 'budget_exhausted': 1}


def test_a_call_that_raises_stays_in_its_turn(harness):
    class Failing:
        def create(self, **kwargs):
            raise ConnectionError('server went away')

    measured = harness.MeasuredCompletions(Failing())
    token = harness._current_turn.set('t-err')
    try:
        with pytest.raises(ConnectionError):
            measured.create(model='llama', messages=[], stream=False)
    finally:
        harness._current_turn.reset(token)
    [record] = measured.records_for_turn('t-err')
    assert record.error == 'ConnectionError'
    assert harness.llm_stats([record])['calls_raised'] == 1


def test_a_turn_that_raises_keeps_its_calls(harness):
    class Exploding(FakeOrchestrator):
        def iter_query(self, text, document=None, turn_id=None):
            for i, event in enumerate(super().iter_query(text, document)):
                if i == 1:  # after decompose's two calls
                    raise RuntimeError('pipeline blew up')
                yield event

    fake = FakeCompletions(parties=1)
    measured = harness.MeasuredCompletions(fake)
    client = SimpleNamespace(chat=SimpleNamespace(completions=measured))
    record = harness.run_scenario(
        _scenarios()[0], client, measured, 0,
        build_orchestrator=lambda: Exploding(client, 0),
    )
    assert record['error'] == "RuntimeError('pipeline blew up')"
    [turn] = record['turns']  # the scenario stops at the failed turn
    assert turn['error'] == record['error']
    assert turn['llm']['calls'] == measured.total_calls == 2
    assert harness.attribution_summary(measured, [record])['calls_in_turns'] == 2
