"""arms.py end to end over an httpx mock transport (Q-02 stage 0).

Single-model calls get canned replies keyed on their prompt; harness calls
go to test_harness_pipeline's FakeServer, keyed on the pipeline's llm_step
label. Every call goes through the stock OpenAI client and the harness seam.
"""

import json
from pathlib import Path

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
                      '--intermediates', str(out.parent / 'intermediates'), '--label', 't', *extra])


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
    with pytest.raises(SystemExit, match='needs --refine-budget or --refine-rounds'):
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
    assert report['completion_p50'] == {'b': 6500, 'a2@1': 2500}
    assert report['within_25pct'] == {'a2@1': False}
    assert report['predicted_rounds'] == 4  # (6500 - 1000) / (300 + 1200) = 3.7


def test_drafts_are_skipped_and_a_frozen_bench_refuses_them(tmp_path, arms):
    bench = _bench(tmp_path)
    manifest = yaml.safe_load((bench / 'manifest.yaml').read_text())
    manifest['prompts'].append({'id': 'c02', 'domain': 'code', 'status': 'draft'})
    (bench / 'manifest.yaml').write_text(yaml.safe_dump(manifest))
    loaded = arms.load_bench(bench)
    assert 'c02' not in loaded['prompts'] and loaded['drafts'] == ['c02']
    manifest['frozen'] = True
    (bench / 'manifest.yaml').write_text(yaml.safe_dump(manifest))
    with pytest.raises(ValueError, match='frozen bench has draft'):
        arms.load_bench(bench)


def test_commit_is_read_at_the_start_and_resume_needs_the_same_commit(tmp_path, monkeypatch,
                                                                       arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    heads = iter(['a' * 40] + ['b' * 40] * 10)
    monkeypatch.setattr(arms.harness, 'git_commit',
                        lambda: {'commit': next(heads), 'dirty': False})
    _run(arms, bench, out, '--arm', 'a', '--prompt', 'c01')
    path, data = _load(out)
    assert data['commit'] == 'a' * 40 and data['commit_at_end'] == 'b' * 40
    with pytest.raises(SystemExit, match='pinned at that commit'):
        arms.main(['run', '--bench', str(bench), '--generator', 'flash-next',
                   '--base-url', 'http://arms.test/v1', '--arm', 'a', '--resume', str(path)])


def test_a2_logs_every_round_without_changing_what_it_sends(tmp_path, monkeypatch, arms):
    """D-023: the `rounds` log is logging only. The requests are the ones
    the pre-registered arm makes, and the output is the last round's draft."""
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    server = ArmsServer()
    _wire(monkeypatch, arms, server)
    assert _run(arms, bench, out, '--arm', 'a2', '--prompt', 'r01', '--refine-rounds', '2') == 0
    _, data = _load(out)
    [row] = data['results']
    log = row['rounds']
    assert [r['round'] for r in log] == [0, 1, 2]
    # Each round also logs its completion tokens: the draft is 2 calls x 4, a round 2 x 4.
    assert log[0] == {'round': 0, 'draft': 'ANSWER[Write a shor] (rest)', 'completion_tokens': 8}
    assert all(r['critique'] == 'Problem: too short.' and r['draft'] == 'REVISED'
               and r['completion_tokens'] == 8 for r in log[1:])
    assert row['refine_budget'] is None and row['stratum'] == 'report-short'
    assert row['output']['text'] == log[-1]['draft']
    # Each revision request carries the previous round's draft, as before.
    revisions = [b['messages'][-1]['content'] for b in server.requests
                 if b['messages'][-1]['content'].startswith('## Task')]
    assert 'ANSWER[Write a shor] (rest)' in revisions[0] and 'REVISED' in revisions[1]
    assert len(server.requests) == 2 + 2 * 2  # draft + its continuation, then 2 x (critique, revision)


def test_single_and_harness_arms_carry_no_rounds_log(tmp_path, monkeypatch, arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    _run(arms, bench, out, '--arm', 'a', '--arm', 'b', '--prompt', 'r01')
    _, data = _load(out)
    assert all(r.get('rounds') is None for r in data['results'])


def test_jobs_default_per_generator(tmp_path, monkeypatch, arms):
    """Without --jobs, a llama.cpp generator runs 5 chains (its 5 slots) and flash-next 3."""
    assert set(arms.DEFAULT_JOBS) == set(arms.GENERATORS)
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    monkeypatch.setitem(globals(), 'MODEL', arms.GENERATORS['qwen3.8-27b'])  # what the mock serves
    monkeypatch.setenv('LLM_MODEL', arms.GENERATORS['qwen3.8-27b'])
    assert arms.main(['run', '--bench', str(bench), '--generator', 'qwen3.8-27b',
                      '--base-url', 'http://arms.test/v1', '--out', str(out), '--label', 't',
                      '--arm', 'a']) == 0
    _, data = _load(out)
    assert data['jobs'] == 5


def _budget_file(tmp_path, **tokens):
    path = tmp_path / 'budget.yaml'
    path.write_text(yaml.safe_dump({'budgets': {'flash-next': tokens}}))
    return path


@pytest.mark.parametrize('budget, rounds, stop', [
    (30, 3, 'budget'),    # 8 + 8 + 8 + 8 = 32: a fourth round would end at 40, farther from 30
    (21, 2, 'budget'),    # 24 is 3 over, 16 would be 5 under: the nearer side
    (6, 1, 'budget'),     # the draft alone is over, but at least one round runs (ceiling 18)
    (10_000, 8, 'cap'),   # never reaches the budget: stops at REFINE_CAP
])
def test_a2_token_budget(tmp_path, monkeypatch, arms, budget, rounds, stop):
    """--refine-budget: after the draft, a round runs while spent + half the last
    round is below the stratum's budget; at least one round, at most REFINE_CAP."""
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    server = ArmsServer()
    _wire(monkeypatch, arms, server)
    path = _budget_file(tmp_path, **{'report-short': budget, 'code-long': 99})
    assert _run(arms, bench, out, '--arm', 'a2', '--prompt', 'r01',
                '--refine-budget', str(path)) == 0
    _, data = _load(out)
    [row] = data['results']
    assert row['refine_rounds'] == rounds and len(row['rounds']) == rounds + 1
    assert row['refine_budget'] == {'stratum': 'report-short', 'budget': budget,
                                    'ceiling': 3 * budget,
                                    'spent': 8 + 8 * rounds, 'rounds': rounds, 'stop': stop,
                                    'cap': arms.REFINE_CAP, 'min_rounds': 1}
    assert data['refine_budget']['tokens'] == {'report-short': budget, 'code-long': 99}
    assert data['refine_cap'] == arms.REFINE_CAP and data['refine_rounds'] == {}
    assert row['llm']['completion_tokens'] == 8 + 8 * rounds  # the seam agrees with the rule


def test_a2_budget_refusals(tmp_path, monkeypatch, arms):
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    path = _budget_file(tmp_path, **{'report-short': 30})
    with pytest.raises(SystemExit, match='no flash-next budget for code-long'):
        _run(arms, bench, out, '--arm', 'a2', '--refine-budget', str(path))
    with pytest.raises(SystemExit):  # one rule or the other, never both
        _run(arms, bench, out, '--arm', 'a2', '--refine-budget', str(path), '--refine-rounds', '1')


def test_budget_and_match_by_stratum(tmp_path, arms):
    """`budget` takes the harness's error-free median per stratum; `match`
    reports a2@budget beside b per domain and per stratum."""
    bench = _bench(tmp_path)

    def row(pid, arm, ctok, error=None, **extra):
        return {'prompt_id': pid, 'arm': arm, 'run': 0, 'domain': 'code' if pid == 'c01' else 'report',
                'error': error, 'llm': {'completion_tokens': ctok}, 'calls': [], **extra}
    f = tmp_path / 'pilot.json'
    f.write_text(json.dumps({'generator': 'flash-next', 'results': [
        row('r01', 'b', 100), row('r01f', 'b', 300), row('c01', 'b', 50),
        row('c01', 'b', 999, error='boom') | {'run': 1},
        row('r01', 'a2', 90, refine_budget={'stop': 'budget'}, stratum='report-short'),
    ]}))
    report = arms.budget_report([f], bench)
    assert report['flash-next']['report-short'] == {'tokens': 200, 'n': 2,
                                                    'prompts': {'r01': 100, 'r01f': 300}}
    assert report['flash-next']['code-long']['tokens'] == 50  # the errored run is left out
    m = arms.match_report([f], strata={'r01': 'report-short', 'r01f': 'report-short',
                                       'c01': 'code-long'})
    assert m['flash-next/report-short']['completion_p50'] == {'b': 200, 'a2@budget': 90}
    assert m['flash-next/report']['within_25pct'] == {'a2@budget': False}


def test_a2_hard_ceiling_discards_the_cut_round_and_keeps_the_last_draft(tmp_path, monkeypatch,
                                                                        arms):
    """Ceiling 3 x 4 = 12: the draft spends 8 and the first critique 4, so the
    revision has no room. The round is discarded (logged) and the output is
    the draft; the ceiling overrides the one-round minimum."""
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    server = ArmsServer()
    _wire(monkeypatch, arms, server)
    path = _budget_file(tmp_path, **{'report-short': 4})
    assert _run(arms, bench, out, '--arm', 'a2', '--prompt', 'r01',
                '--refine-budget', str(path)) == 0
    _, data = _load(out)
    [row] = data['results']
    assert row['refine_budget']['stop'] == 'ceiling' and row['refine_budget']['ceiling'] == 12
    assert row['refine_rounds'] == 0 and row['refine_budget']['spent'] == 12
    assert row['output']['text'] == 'ANSWER[Write a shor] (rest)'
    assert row['rounds'][-1] == {'round': 1, 'critique': 'Problem: too short.', 'draft': '',
                                 'completion_tokens': 4, 'discarded': True}
    # Each call asked for no more than the room left under the ceiling.
    assert [b['max_tokens'] for b in server.requests] == [12, 8, 4]


def test_harness_intermediates_go_to_their_own_directory(tmp_path, monkeypatch, arms):
    """Arm b writes each turn's plan and every Document state to
    <intermediates>/<run stem>/<turn id>/, with a manifest the run file hashes."""
    bench, out = _bench(tmp_path), tmp_path / 'runs'
    _wire(monkeypatch, arms, ArmsServer())
    assert _run(arms, bench, out, '--arm', 'b', '--prompt', 'r01f') == 0
    path, data = _load(out)
    root = tmp_path / 'intermediates' / path.stem
    assert data['intermediates_dir'] == str(root)
    rows = {r['prompt_id']: r for r in data['results']}
    for pid in ('r01', 'r01f'):  # the follow-up's chain runs its parent too
        inter = rows[pid]['intermediates']
        files = sorted(p.name for p in Path(inter['dir']).glob('*.json'))
        assert inter['files'] == len(files) >= 2
        assert files[0].startswith('01_plan') and any('_document_' in f for f in files)
        doc = json.loads(sorted(Path(inter['dir']).glob('*_document_*.json'))[-1].read_text())
        assert doc['turn_id'].endswith(':t0' if pid == 'r01' else ':t1')
        assert doc['snapshot']['parts']
    manifest = json.loads((root / 'manifest.json').read_text())
    assert data['intermediates']['files'] == len(manifest) and len(manifest) >= 4
