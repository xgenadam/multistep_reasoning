"""arms.py end to end over an httpx mock transport (Q-02 stage 0).

Single-model calls get canned replies keyed on their prompt; harness calls
go to test_harness_pipeline's FakeServer, keyed on the pipeline's llm_step
label. Every call goes through the stock OpenAI client and the harness seam.
"""

import json

import httpx
import pytest
import yaml
from openai import OpenAI

from tests.test_baseline.test_harness_pipeline import FakeServer

MODEL = 'qwen3.8-flash-next'


def _bench(tmp_path, frozen=False):
    bench = tmp_path / 'bench'
    (bench / 'prompts').mkdir(parents=True)
    prompts = {
        'r01': 'Write a short report on tickets.',
        'r01f': 'Extend the report with a migration section. Reply with the complete report.',
        'c01': 'Write wordcount.py.',
    }
    for pid, text in prompts.items():
        (bench / 'prompts' / f'{pid}.md').write_text(text + '\n')
    manifest = {'version': 'test', 'frozen': frozen, 'prompts': [
        {'id': 'r01', 'domain': 'report', 'subsets': ['g3']},
        {'id': 'r01f', 'domain': 'report', 'follows': 'r01', 'subsets': ['g3']},
        {'id': 'c01', 'domain': 'code', 'long': True},
    ]}
    (bench / 'manifest.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False))
    return bench


class ArmsServer:
    """Single-model replies: the first answer to a prompt stops on `length`
    once, so the driver must continue it; critiques and revisions stop."""

    def __init__(self, fail_on=None):
        self.pipeline = FakeServer()
        self.requests: list[dict] = []
        self.fail_on = fail_on

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={'object': 'list', 'data': [
                {'id': MODEL, 'object': 'model', 'created': 0, 'owned_by': 'x'}]})
        body = json.loads(request.content)
        from reasoning_sub_agents.progress import live
        if live() is not None:  # a harness turn
            return self.pipeline.handle(request)
        self.requests.append(body)
        last = body['messages'][-1]['content']
        if self.fail_on and self.fail_on in last:
            return httpx.Response(500, json={'error': {'message': 'boom'}})
        if last.startswith('Continue exactly'):
            text, finish = ' (rest)', 'stop'
        elif last.startswith('You are reviewing'):
            text, finish = 'Problem: too short.', 'stop'
        elif last.startswith('## Task'):
            text, finish = 'REVISED', 'stop'
        else:
            text, finish = f'ANSWER[{last[:12]}]', 'length'
        return httpx.Response(200, json={
            'id': 'c', 'object': 'chat.completion', 'created': 0, 'model': MODEL,
            'choices': [{'index': 0, 'finish_reason': finish,
                         'message': {'role': 'assistant', 'content': text}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 4, 'total_tokens': 14},
        })


@pytest.fixture
def arms(monkeypatch):
    from tests.test_baseline.conftest import load_baseline_module
    module = load_baseline_module('arms')
    monkeypatch.delenv('LLM_BASE_URL', raising=False)
    monkeypatch.setenv('LLM_MODEL', MODEL)  # restored after the test
    return module


def _wire(monkeypatch, arms, server):
    def client(base_url=None, **_):
        return OpenAI(base_url=base_url, api_key='sk-no-key-needed', max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(server.handle)))
    monkeypatch.setattr(arms, 'create_llama_client', client)


def _run(arms, bench, out, *extra):
    return arms.main(['run', '--bench', str(bench), '--generator', 'flash-next',
                      '--base-url', 'http://arms.test/v1', '--jobs', '1', '--out', str(out),
                      '--label', 't', *extra])


def _load(out):
    [path] = [p for p in out.glob('*.json')]
    return path, json.loads(path.read_text())


def test_single_arms_continue_refine_and_carry_history(tmp_path, monkeypatch, arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    server = ArmsServer()
    _wire(monkeypatch, arms, server)
    assert _run(arms, bench, out, '--arm', 'a', '--arm', 'a1', '--arm', 'a2',
                '--refine-rounds', 'code=1,report=2') == 0
    _, data = _load(out)
    rows = {(r['arm'], r['prompt_id']): r for r in data['results']}
    assert len(rows) == 9 and all(r['error'] is None for r in rows.values())

    a = rows[('a', 'r01')]
    assert a['output']['text'] == 'ANSWER[Write a shor] (rest)'
    assert a['continuations'] == 1 and a['capped'] == 0
    assert [c['kind'] for c in a['calls']] == ['single', 'single']
    assert all(c['label_source'] == 'phase' and c['thinking'] is False for c in a['calls'])
    assert all(c['thinking'] is True for c in rows[('a1', 'r01')]['calls'])

    # The follow-up sees the parent exchange as history, with this arm's answer.
    followups = [b for b in server.requests if b['messages'][-1]['content'].startswith('Extend')]
    a_follow = followups[0]['messages']
    assert [m['role'] for m in a_follow] == ['user', 'assistant', 'user']
    assert a_follow[1]['content'] == 'ANSWER[Write a shor] (rest)'

    refine = rows[('a2', 'r01')]
    kinds = [c['kind'] for c in refine['calls']]
    assert kinds == ['refine_draft', 'refine_draft'] + ['refine_critique', 'refine_revise'] * 2
    assert refine['refine_rounds'] == 2 and refine['output']['text'] == 'REVISED'
    assert rows[('a2', 'c01')]['refine_rounds'] == 1
    # The reviser of a follow-up gets the earlier deliverable spelled out.
    revise = [b for b in server.requests if b['messages'][-1]['content'].startswith('## Task')
              and 'The user then asked' in b['messages'][-1]['content']]
    assert revise and 'REVISED' in revise[0]['messages'][-1]['content']

    assert len(data['commit']) == 40 and data['model'] == MODEL
    assert data['prompts_version'] == arms.PROMPTS_VERSION
    assert set(data['arm_elapsed_seconds']) == {'a', 'a1', 'a2'}
    assert data['summary']['a/report']['prompts'] == 2
    assert data['summary']['a/report']['continuations_sum'] == 2


def test_harness_arm_continues_the_document(tmp_path, monkeypatch, arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    _run(arms, bench, out, '--arm', 'b', '--subset', 'g3')
    _, data = _load(out)
    rows = {r['prompt_id']: r for r in data['results']}
    assert set(rows) == {'r01', 'r01f'}
    assert all(r['error'] is None for r in rows.values())
    t0, t1 = rows['r01'], rows['r01f']
    assert t0['output']['snapshot'] and 'op_log' not in t0['output']['snapshot']
    assert t0['output']['text'].startswith('## Part')
    # Turn 1 continues turn 0's parts (FakeServer adds parts p1.. per compose).
    assert t1['document']['part_count'] > t0['document']['part_count']
    assert t1['llm']['label_sources'] == {'phase': t1['llm']['calls']}
    assert data['config']['options']['consolidation'] is False


def test_arm_c_turns_consolidation_on(tmp_path, monkeypatch, arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    _run(arms, bench, out, '--arm', 'c', '--prompt', 'r01')
    _, data = _load(out)
    [row] = data['results']
    assert 'consolidate' in row['llm']['by_kind']


def test_failed_parent_skips_the_follow_up_and_resume_reruns_the_chain(tmp_path, monkeypatch,
                                                                       arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer(fail_on='Extend the report'))
    assert _run(arms, bench, out, '--arm', 'a') == 1
    path, data = _load(out)
    rows = {r['prompt_id']: r for r in data['results']}
    assert rows['r01']['error'] is None and rows['r01f']['error'] is not None
    assert rows['c01']['error'] is None

    server = ArmsServer()
    _wire(monkeypatch, arms, server)
    assert arms.main(['run', '--bench', str(bench), '--generator', 'flash-next',
                      '--base-url', 'http://arms.test/v1', '--jobs', '1', '--arm', 'a',
                      '--resume', str(path)]) == 0
    data = json.loads(path.read_text())
    rows = {r['prompt_id']: r for r in data['results']}
    assert len(data['results']) == 3 and all(r['error'] is None for r in rows.values())
    # The whole r01 chain re-ran (its parent too); c01 was kept.
    asked = [b['messages'][-1]['content'][:6] for b in server.requests
             if not b['messages'][-1]['content'].startswith('Continue')]
    assert asked == ['Write ', 'Extend']


def test_resume_refuses_a_changed_setting(tmp_path, monkeypatch, arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    _run(arms, bench, out, '--arm', 'a', '--prompt', 'c01')
    path, _ = _load(out)
    with pytest.raises(SystemExit, match='overrides differs'):
        arms.main(['run', '--bench', str(bench), '--generator', 'flash-next',
                   '--base-url', 'http://arms.test/v1', '--arm', 'a', '--resume', str(path),
                   '--set', 'options.max_oracle_rounds=2'])


def test_refusals(tmp_path, monkeypatch, arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    with pytest.raises(SystemExit, match='needs --refine-rounds'):
        _run(arms, bench, out, '--arm', 'a2')
    with pytest.raises(SystemExit, match='unknown key'):
        _run(arms, bench, out, '--set', 'options.nope=1')
    monkeypatch.setenv('LLM_MODEL', 'llama')
    with pytest.raises(SystemExit, match='contradicts'):
        _run(arms, bench, out)
    monkeypatch.setenv('LLM_MODEL', 'qwen3.8-27b')
    with pytest.raises(SystemExit, match='not served'):
        arms.main(['run', '--bench', str(bench), '--generator', 'qwen3.8-27b',
                   '--base-url', 'http://arms.test/v1', '--out', str(out)])


def test_bench_links_and_selection(tmp_path, arms):
    bench = _bench(tmp_path)
    loaded = arms.load_bench(bench)
    prompts = loaded['prompts']
    assert arms.select(prompts, 'followup', None, None) == ['r01f']
    assert arms.select(prompts, 'long', None, None) == ['c01']
    assert arms.plan_chains(prompts, ['r01', 'r01f', 'c01']) == [['r01', 'r01f'], ['c01']]
    assert arms.plan_chains(prompts, ['r01f']) == [['r01', 'r01f']]
    manifest = yaml.safe_load((bench / 'manifest.yaml').read_text())
    manifest['prompts'].append({'id': 'c01', 'domain': 'code'})
    (bench / 'manifest.yaml').write_text(yaml.safe_dump(manifest))
    with pytest.raises(ValueError, match='duplicate'):
        arms.load_bench(bench)
    manifest['prompts'][-1] = {'id': 'r02', 'domain': 'report', 'follows': 'r01'}
    (bench / 'prompts' / 'r02.md').write_text('x')
    (bench / 'manifest.yaml').write_text(yaml.safe_dump(manifest))
    with pytest.raises(ValueError, match='two follow-ups'):
        arms.load_bench(bench)


def test_match_report_predicts_rounds(tmp_path, arms):
    def row(arm, ctok, calls=(), rounds=None):
        return {'arm': arm, 'domain': 'code', 'error': None, 'refine_rounds': rounds,
                'llm': {'completion_tokens': ctok}, 'calls': list(calls)}
    calls = [{'kind': 'refine_draft', 'completion_tokens': 1000},
             {'kind': 'refine_critique', 'completion_tokens': 300},
             {'kind': 'refine_revise', 'completion_tokens': 1200}]
    data = {'generator': 'g', 'results': [row('b', 6000), row('b', 7000), row('a2', 2500, calls, 1)]}
    path = tmp_path / 'r.json'
    path.write_text(json.dumps(data))
    report = arms.match_report([path])['g/code']
    assert report['completion_p50'] == {'b': 6500, 'a2': 2500}
    assert report['within_25pct'] == {'a2': False}
    assert report['predicted_rounds'] == 4  # (6500 - 1000) / (300 + 1200) = 3.7
