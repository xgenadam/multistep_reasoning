"""Thinking on through the real pipeline: switched, captured, never fed back (0-15, P0-10).

The 0-14 fake server runs the real TaskOrchestrator; here every reply also
carries reasoning, in `message.reasoning` on JSON calls and as a leading
<think> block on streamed ones. The reasoning must reach the harness record
(capped) and the side log, and no later request, summary or part.
"""

import json
from datetime import datetime, timezone

import httpx
import pytest
from openai import OpenAI

from reasoning_sub_agents.config.schema import OptionsConfig, OrchestratorConfig
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

from .test_harness_pipeline import MAX_ROUNDS, FakeServer

MARK = 'ZQXREASONING'
REASONING_TOKENS = 4


class ThinkingServer(FakeServer):
    def __init__(self):
        super().__init__()
        self.bodies: list[dict] = []
        self.n = 0

    def _mark(self) -> str:
        self.n += 1
        return f'{MARK}-{self.n} ' + 'x' * 600  # longer than the excerpt cap

    def _sse(self, text, usage):
        return FakeServer._sse(f'<think>{self._mark()}</think>\n\n{text}', usage)

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        response = super().handle(request)
        if body.get('stream') or response.status_code != 200:
            return response
        data = json.loads(response.content)
        data['choices'][0]['message']['reasoning'] = self._mark()
        data['usage']['completion_tokens_details'] = {'reasoning_tokens': REASONING_TOKENS}
        return httpx.Response(200, json=data)


def _run(harness, tmp_path, thinking: str):
    server = ThinkingServer()
    client = OpenAI(
        base_url='http://pipeline.test/v1', api_key='sk-no-key-needed', max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(server.handle)),
    )
    measured = harness.install_instrumentation(client)
    cfg = OrchestratorConfig(options=OptionsConfig(
        consolidation=True, max_oracle_rounds=MAX_ROUNDS, thinking=thinking,
        thinking_log_dir=str(tmp_path)))
    record = harness.run_scenario(
        {'id': 'pipe', 'turns': [{'text': 'Write a short report.'}]}, client, measured, 0,
        build_orchestrator=lambda: TaskOrchestrator.from_orchestrator_config(
            cfg, llm_client=client),
        log_tag='tag_',
    )
    [turn] = record['turns']
    assert 'error' not in turn
    return server, turn


@pytest.fixture(scope='module')
def thinking_on(harness, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp('thinking')
    return (tmp_path, *_run(harness, tmp_path, 'on'))


def test_every_call_is_sent_with_thinking_on(thinking_on):
    _, server, turn = thinking_on
    assert server.bodies
    assert {b['chat_template_kwargs']['enable_thinking'] for b in server.bodies} == {True}
    llm = turn['llm']
    assert llm['thinking_calls'] == llm['calls'] == len(server.bodies)
    assert llm['calls_without_switch'] == 0


def test_reasoning_never_reaches_a_prompt_summary_or_part(thinking_on):
    _, server, turn = thinking_on
    assert server.n > 0  # reasoning was produced ...
    for body in server.bodies:  # ... and no later request carried it
        assert MARK not in json.dumps(body)
    snapshot = json.dumps(turn['snapshot'])
    assert MARK not in snapshot
    assert turn['snapshot']['summary']  # the summary was written, without it


def test_run_file_keeps_capped_reasoning_per_call_and_kind(harness, thinking_on):
    _, _, turn = thinking_on
    answered = [c for c in turn['calls'] if c['error'] is None]
    assert answered
    for call in answered:
        assert call['reasoning_excerpt'].startswith(MARK)
        assert len(call['reasoning_excerpt']) == harness.REASONING_EXCERPT_CHARS
        assert call['reasoning_chars'] > harness.REASONING_EXCERPT_CHARS
        # The server's per-call count, read at the seam (instructor's own
        # summed usage drops it).
        expected = None if call['stream'] else REASONING_TOKENS
        assert call['reasoning_tokens'] == expected
    llm = turn['llm']
    non_streamed = sum(not c['stream'] for c in answered)
    assert llm['reasoning_tokens'] == REASONING_TOKENS * non_streamed
    assert llm['reasoning_chars'] == sum(c['reasoning_chars'] for c in answered)
    for kind, agg in llm['by_kind'].items():
        assert agg['reasoning_chars'] > 0, kind


def test_side_log_holds_the_full_text(thinking_on):
    tmp_path, _, turn = thinking_on
    day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    path = tmp_path / day / 'tag_pipe_r0_t0.jsonl'
    records = [json.loads(line) for line in path.read_text().splitlines()]
    answered = [c for c in turn['calls'] if c['error'] is None]
    assert len(records) == len(answered)
    assert all(r['text'].startswith(MARK) and r['chars'] == len(r['text']) for r in records)
    assert {r['setting'] for r in records} == {'on'}
    assert {r['turn_id'] for r in records} == {'tag_pipe#r0:t0'}
    assert {r['kind'] for r in records} == {c['kind'] for c in answered}


def test_thinking_off_is_sent_and_logs_nothing(harness, tmp_path):
    server, turn = _run(harness, tmp_path, 'off')
    assert {b['chat_template_kwargs']['enable_thinking'] for b in server.bodies} == {False}
    assert turn['llm']['thinking_calls'] == 0
    assert not any(tmp_path.iterdir())
