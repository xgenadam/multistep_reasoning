"""quality.py: the judge protocol, scoring and verdict file (Q-01 stage 2)."""

import json
from types import SimpleNamespace as NS

import openai
import pytest
import yaml

from tests.test_baseline.conftest import load_baseline_module


@pytest.fixture(scope='module')
def quality():
    return load_baseline_module('quality')


def verdict(winner: str) -> str:
    return json.dumps({'requested_items': [], 'winner': winner, 'reason': 'r'})


def test_wilson_matches_d019_example(quality):
    lo, hi = quality.wilson(7, 10)
    assert (round(lo, 2), round(hi, 2)) == (0.40, 0.89)
    assert quality.wilson(0, 0) is None


@pytest.mark.parametrize('text, winner', [
    (verdict('A'), 'A'),
    ('```json\n' + verdict('b') + '\n```', 'B'),
    ('<think>{"winner": "A"} hmm</think>\n' + verdict('TIE'), 'tie'),
    ('Sure! ' + verdict('B') + ' Hope that helps.', 'B'),
])
def test_parse_verdict_accepts(quality, text, winner):
    assert quality.parse_verdict(text)['winner'] == winner


@pytest.mark.parametrize('text', ['', 'no json', '{"winner": "C"}', '[1, 2]', '{"winner": '])
def test_parse_verdict_rejects(quality, text):
    assert quality.parse_verdict(text) is None


def test_both_orders_rule(quality):
    # In order ba the judge's "A" is candidate b.
    assert quality.side_of('A', 'ab') == 'a'
    assert quality.side_of('A', 'ba') == 'b'
    assert quality.side_of('tie', 'ba') == 'tie'
    assert quality.pair_outcome('a', 'a') == 'a'
    assert quality.pair_outcome('a', 'b') == 'tie'  # position-driven: not decisive
    assert quality.pair_outcome('tie', 'tie') == 'tie'
    assert quality.pair_outcome('a', None) == 'no_verdict'


def test_rates_exclude_no_verdict(quality):
    r = quality.rates(['win', 'win', 'win', 'b', 'tie', 'no_verdict'])
    assert (r['n'], r['decisive'], r['wins'], r['ties']) == (5, 4, 3, 1)
    assert r['decisive_win_rate'] == 0.75
    assert r['all_pairs_rate'] == 0.7


def _call(pid, order, repeat, side):
    return {'pair_id': pid, 'order': order, 'repeat': repeat, 'side': side,
            'attempts': [{}], 'seconds': 1.0, 'prompt_tokens': 10, 'completion_tokens': 2}


def test_summarise_scores_each_kind(quality):
    pairs = [{'pair_id': 'R1', 'kind': 'real', 'expected': None},
             {'pair_id': 'W1', 'kind': 'damaged', 'expected': 'a'},
             {'pair_id': 'W2', 'kind': 'damaged', 'expected': 'a'},
             {'pair_id': 'L1', 'kind': 'padded', 'expected': 'a'},
             {'pair_id': 'L2', 'kind': 'padded', 'expected': 'a'}]
    sides = {'R1': ('a', 'b'), 'W1': ('a', 'a'), 'W2': ('a', None),
             'L1': ('tie', 'a'), 'L2': ('a', 'b')}
    calls = [_call(pid, o, r, s) for r in (0, 1) for pid, ss in sides.items()
             for o, s in zip(('ab', 'ba'), ss)]
    s = quality.summarise(pairs, calls)
    by = {p['pair_id']: p for p in s['pairs']}
    assert by['W1']['pass'] == [True, True]
    assert by['W2']['repeats'][0]['outcome'] == 'no_verdict'
    assert by['W2']['pass'][0] is False
    assert by['L1']['pass'][0] is True   # a tie and a win: padding never preferred
    assert by['L2']['pass'][0] is False  # the padded side won one order
    assert s['q1']['real']['status'] == 'pending'
    assert s['q1']['damaged']['passed'] == 1
    assert s['q1']['padded']['passed'] == 1
    # Q-5: every pair-order repeats identically except W2 ba, which has no verdict.
    assert (s['q5']['pair_orders'], s['q5']['agree']) == (10, 9)
    assert s['no_verdict_calls'] == 2
    assert s['cost']['calls'] == 20


class FakeJudge:
    """Prefers the response without BAD; the first answer for SLOW is garbage."""

    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        user = kwargs['messages'][1]['content']
        first = user.split('<<<RESPONSE A>>>')[1].split('<<<END RESPONSE A>>>')[0]
        if 'SLOW' in user and sum('SLOW' in c['messages'][1]['content'] for c in self.calls) == 1:
            content = 'I think A.'
        else:
            content = verdict('B' if 'BAD' in first else 'A')
        return NS(choices=[NS(message=NS(content=content, model_extra={}), finish_reason='stop')],
                  usage=NS(prompt_tokens=100, completion_tokens=20,
                           completion_tokens_details=None))


@pytest.fixture
def manifest(tmp_path):
    (tmp_path / 'c').mkdir()
    for name, text in [('g', 'good'), ('bad', 'BAD answer'), ('slow', 'SLOW good')]:
        (tmp_path / 'c' / f'{name}.md').write_text(text)
    pairs = {'pairs': [
        {'pair_id': 'W1', 'kind': 'damaged', 'task': 't', 'a': 'c/g.md', 'b': 'c/bad.md',
         'expected': 'a'},
        {'pair_id': 'W2', 'kind': 'damaged', 'task': 't', 'a': 'c/slow.md', 'b': 'c/bad.md',
         'expected': 'a', 'tests': {'a': '3/3 passed', 'b': '1/3 passed'}},
    ]}
    path = tmp_path / 'pairs.yaml'
    path.write_text(yaml.safe_dump(pairs))
    return path


def _run(quality, monkeypatch, tmp_path, manifest, *extra):
    fake, built = FakeJudge(), []

    def factory(**kwargs):
        client = openai.OpenAI(**kwargs)
        client.chat.completions.create = fake.create
        client.models.list = lambda: NS(data=[NS(id='judge-m')])
        built.append(client)
        return client

    monkeypatch.setattr(quality, 'OpenAI', factory)
    monkeypatch.setattr('sys.argv', [
        'quality.py', 'judge', '--pairs', str(manifest), '--judge-base-url',
        'http://judge.invalid/v1', '--judge-model', 'judge-m', '--repeat', '2',
        '--out', str(tmp_path / 'out'), '--label', 't', *extra])
    assert quality.main() == 0
    return fake, built


def test_judge_end_to_end_and_resume(quality, monkeypatch, tmp_path, manifest):
    fake, built = _run(quality, monkeypatch, tmp_path, manifest)
    # The seam: a stock OpenAI instance (AGENTS.md), explicit thinking switch.
    assert isinstance(built[0], openai.OpenAI)
    assert all(c['extra_body'] == {'chat_template_kwargs': {'enable_thinking': False}}
               and c['temperature'] == 0 for c in fake.calls)
    assert len(fake.calls) == 9  # 2 pairs x 2 orders x 2 repeats, one retry
    assert any('tests: 3/3 passed' in c['messages'][1]['content'] for c in fake.calls)

    [out] = (tmp_path / 'out').glob('*_t.json')
    data = json.loads(out.read_text())
    assert data['judge_model'] == 'judge-m'
    assert data['rubric'] == 'pairwise_v1'
    assert len(data['commit']) == 40
    retried = [c for c in data['calls'] if len(c['attempts']) == 2]
    assert len(retried) == 1 and retried[0]['side'] == 'a'
    assert retried[0]['attempts'][1]['repair'] is True
    repair = next(c for c in fake.calls if len(c['messages']) == 4)
    assert repair['messages'][2] == {'role': 'assistant', 'content': 'I think A.'}
    s = data['summary']
    assert s['q1']['damaged']['passed'] == 2
    assert s['q5']['rate'] == 1.0
    assert s['position_consistency']['rate'] == 1.0
    assert s['expected_side_rates']['decisive_win_rate'] == 1.0

    fake, _ = _run(quality, monkeypatch, tmp_path, manifest, '--resume', str(out))
    assert fake.calls == []  # every pair-order already has a verdict


def test_no_silent_judge_default(quality, monkeypatch, manifest):
    monkeypatch.delenv('JUDGE_BASE_URL', raising=False)
    monkeypatch.setattr('sys.argv', ['quality.py', 'judge', '--pairs', str(manifest),
                                     '--judge-model', 'm'])
    with pytest.raises(SystemExit, match='no judge endpoint'):
        quality.main()


def test_validation_manifest_loads(quality):
    path = quality.REPO_ROOT / 'journal/baseline/bench/validation/pairs.yaml'
    pairs = quality.load_pairs(path)
    kinds = [p['kind'] for p in pairs]
    assert (kinds.count('real'), kinds.count('damaged'), kinds.count('padded')) == (5, 5, 2)
    assert all(p['a_text'] != p['b_text'] for p in pairs)
