"""A fresh harness run of the real pipeline labels every call (0-14, P0-6).

The real TaskOrchestrator (default components plus consolidation) runs over
an httpx mock transport, so every call goes through the stock OpenAI client,
instructor and the harness seam. The fake server picks its reply from the
llm_step label the pipeline set, and never looks at prompt text.
"""

import inspect
import json
import re

import httpx
import pytest
from openai import OpenAI

from reasoning_sub_agents.config.schema import OptionsConfig, OrchestratorConfig
from reasoning_sub_agents.llama_utils import get_streamed_json_response
from reasoning_sub_agents.progress import live
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

SUB_TASKS = ('alpha', 'beta', 'gamma')  # completes / runs out of rounds / fails
MAX_ROUNDS = 2
PROMPT_TOKENS, COMPLETION_TOKENS = 11, 5
# instructor retries gamma's HTTP 400 this many times before it raises.
JSON_ATTEMPTS = inspect.signature(get_streamed_json_response).parameters['max_retries'].default


def _sub_task(name: str) -> dict:
    return {
        'meta_type': 'sub_task_detail', 'name': name, 'type': 'writing',
        'description': name, 'context': 'ctx', 'complexity': 3, 'objective': name,
    }


class FakeServer:
    def __init__(self, usage_on_stream: bool = True):
        self.usage_on_stream = usage_on_stream
        self.composed = 0

    def reply(self, label: str) -> str | None:
        """JSON body for a non-streamed call; None means HTTP 400."""
        if label == 'Initial decomposition (JSON)':
            return json.dumps({'content': [_sub_task(n) for n in SUB_TASKS]})
        if m := re.fullmatch(r'Execute (\w+) \(turn (\d+)\)', label):
            name, turn = m.group(1), int(m.group(2))
            if name == 'gamma':
                return None
            if name == 'alpha' and turn == 2:
                return json.dumps({'result': 'alpha deliverable'})
            tool = {'name': 'ask', 'question': 'what exists?'} if name == 'alpha' else {
                'name': 'list_parts'}
            return json.dumps({'tool_calls': [tool]})
        if label == 'Oracle ask':
            return json.dumps({'answer': 'nothing yet', 'citations': []})
        if label == 'Compose document ops (JSON)':
            self.composed += 1
            n = self.composed
            return json.dumps({'ops': [{
                'type': 'add_part', 'id': f'p{n}', 'kind': 'section',
                'title': f'Part {n}', 'body_source': 'current_result',
            }]})
        if label == 'Consolidate document ops (JSON)':
            return json.dumps({'ops': [{'type': 'merge_parts', 'ids': ['p1', 'p2']}]})
        raise AssertionError(f'unexpected non-streamed call under {label!r}')

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        state = live()
        label = state.llm_label if state is not None else ''
        usage = {'prompt_tokens': PROMPT_TOKENS, 'completion_tokens': COMPLETION_TOKENS,
                 'total_tokens': PROMPT_TOKENS + COMPLETION_TOKENS}
        if body.get('stream'):
            assert label in ('Critique decomposition', 'Rolling summary'), label
            include = (body.get('stream_options') or {}).get('include_usage')
            return self._sse('No critique.' if label.startswith('Critique') else 'A summary.',
                             usage if include and self.usage_on_stream else None)
        content = self.reply(label)
        if content is None:
            return httpx.Response(400, json={'error': {'message': 'bad request'}})
        return httpx.Response(200, json={
            'id': 'c', 'object': 'chat.completion', 'created': 0, 'model': 'llama',
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': content}}],
            'usage': usage,
        })

    @staticmethod
    def _sse(text: str, usage: dict | None) -> httpx.Response:
        def chunk(choices, usage=None):
            return {'id': 'c', 'object': 'chat.completion.chunk', 'created': 0,
                    'model': 'llama', 'choices': choices, 'usage': usage}

        events = [
            chunk([{'index': 0, 'delta': {'role': 'assistant', 'content': text},
                    'finish_reason': None}]),
            chunk([{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]),
        ]
        if usage is not None:
            events.append(chunk([], usage))
        payload = ''.join(f'data: {json.dumps(e)}\n\n' for e in events) + 'data: [DONE]\n\n'
        return httpx.Response(200, content=payload.encode(),
                              headers={'content-type': 'text/event-stream'})


def _run(harness, usage_on_stream: bool = True) -> tuple[dict, object]:
    server = FakeServer(usage_on_stream)
    client = OpenAI(
        base_url='http://pipeline.test/v1', api_key='sk-no-key-needed', max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(server.handle)),
    )
    measured = harness.install_instrumentation(client)
    assert measured is not None
    cfg = OrchestratorConfig(options=OptionsConfig(consolidation=True,
                                                   max_oracle_rounds=MAX_ROUNDS))
    scenario = {'id': 'pipe', 'turns': [{'text': 'Write a short report.'}]}
    record = harness.run_scenario(
        scenario, client, measured, 0,
        build_orchestrator=lambda: TaskOrchestrator.from_orchestrator_config(
            cfg, llm_client=client),
    )
    [turn] = record['turns']
    assert 'error' not in turn
    return turn, measured


@pytest.fixture(scope='module')
def fresh(harness):
    return _run(harness)


def test_every_call_carries_a_phase_label(harness, check, fresh):
    turn, measured = fresh
    llm = turn['llm']
    assert llm['calls'] == measured.total_calls
    assert llm['label_sources'] == {'phase': llm['calls']}
    kinds = {k: v['count'] for k, v in llm['by_kind'].items()}
    assert sum(kinds.values()) == llm['calls']
    assert set(kinds) == {'decompose', 'decompose_critique', 'executor_turn', 'oracle',
                          'compose', 'summary', 'consolidate'}
    # alpha: 2 rounds, beta: MAX_ROUNDS rounds, gamma: one round whose
    # attempts all raised.
    assert kinds['executor_turn'] == 2 + MAX_ROUNDS + JSON_ATTEMPTS
    assert kinds['oracle'] == 1
    assert kinds['compose'] == len(SUB_TASKS)
    assert kinds['summary'] == len(SUB_TASKS) + 1  # + the one consolidation triggers
    assert llm['calls_raised'] == JSON_ATTEMPTS
    name, ok, _ = check.label_check(turn)
    assert ok is True, name


def test_streamed_calls_carry_usage(fresh):
    turn, _ = fresh
    llm = turn['llm']
    streamed = [c for c in turn['calls'] if c['stream']]
    assert {c['kind'] for c in streamed} == {'decompose_critique', 'summary'}
    assert all(c['usage_reported'] and c['prompt_tokens'] == PROMPT_TOKENS for c in streamed)
    assert llm['tokens_partial'] is False
    answered = llm['calls'] - llm['calls_raised']
    assert llm['prompt_tokens'] == PROMPT_TOKENS * answered


def test_server_without_stream_usage_is_reported_partial(harness):
    turn, _ = _run(harness, usage_on_stream=False)
    llm = turn['llm']
    assert llm['tokens_partial'] is True
    assert llm['calls_without_usage'] == llm['streamed_calls']


def test_executor_statuses_are_real(fresh):
    turn, _ = fresh
    health = turn['sub_tasks']
    assert health['sub_task_statuses'] == ['completed', 'budget_exhausted', 'failed']
    assert health['exec_status_counts'] == {'completed': 1, 'budget_exhausted': 1, 'failed': 1}


def test_marginal_consolidation_tokens(compare, fresh):
    turn, _ = fresh
    marginal, detail = compare.marginal_tokens(turn['llm'])
    per_call = PROMPT_TOKENS + COMPLETION_TOKENS
    assert marginal == 2 * per_call, detail  # the consolidate call + its summary
