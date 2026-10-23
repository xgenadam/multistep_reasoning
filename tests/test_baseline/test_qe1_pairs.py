"""qe1_pairs.py: the pre-registered outcome rule turned into judge pairs (Q-02)."""

import json

import pytest
import yaml

from tests.test_baseline.conftest import load_baseline_module


@pytest.fixture(scope='module')
def qp():
    return load_baseline_module('qe1_pairs')


def _bench(tmp_path):
    bench = tmp_path / 'bench'
    (bench / 'prompts').mkdir(parents=True)
    texts = {'c1': 'Write a.py.', 'c2': 'Write b.py.', 'c3': 'Write c.py.', 'c4': 'Write d.py.',
             'r1': 'Write a memo.', 'r1f': 'Add a section. Reply with the complete updated document.',
             'r2': 'Write a plan.'}
    for pid, text in texts.items():
        (bench / 'prompts' / f'{pid}.md').write_text(text)
    entries = [{'id': p, 'domain': 'code' if p.startswith('c') else 'report'} for p in texts]
    entries[5]['follows'] = 'r1'
    (bench / 'manifest.yaml').write_text(yaml.safe_dump({'version': 't', 'prompts': entries}))
    return bench


def _result(pid, arm, text='out', error=None):
    return {'prompt_id': pid, 'arm': arm, 'run': 0, 'error': error,
            'output': {'text': text, 'snapshot': None}}


def _test(pid, arm, passed, n=4, ok=True):
    return {'prompt_id': pid, 'arm': arm, 'run': 0, 'n_tests': n, 'extraction_ok': ok,
            'tests': {'passed': passed}}


def _write_run(tmp_path, name, arm, results, tests):
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps({'generator': 'g', 'manifest_sha256': 'm', 'results': results}))
    path.with_suffix('.tests.json').write_text(json.dumps({'results': tests}))
    return path


def test_outcome_rule(tmp_path, qp):
    bench = _bench(tmp_path)
    rb = _write_run(tmp_path, 'b', 'b', [
        _result('c1', 'b'), _result('c2', 'b'), _result('c3', 'b'), _result('c4', 'b', error='boom'),
        _result('r1', 'b', 'memo B'), _result('r1f', 'b', 'memo B+'), _result('r2', 'b', '')],
        [_test('c1', 'b', 4), _test('c2', 'b', 2), _test('c3', 'b', 0, ok=False)])
    ra = _write_run(tmp_path, 'a2', 'a2', [
        _result('c1', 'a2'), _result('c2', 'a2'), _result('c3', 'a2'), _result('c4', 'a2'),
        _result('r1', 'a2', 'memo A'), _result('r1f', 'a2', 'memo A+'), _result('r2', 'a2', 'plan')],
        [_test('c1', 'a2', 3), _test('c2', 'a2', 2), _test('c3', 'a2', 1), _test('c4', 'a2', 4)])
    built = qp.build([rb, ra], 'b', 'a2', bench)
    decided = {d['prompt_id']: (d['winner'], d['by']) for d in built['decided']}
    assert decided == {'c1': ('b', 'tests'),          # 4/4 beats 3/4
                       'c3': ('a2', 'failure'),       # nothing extracted on b's side
                       'c4': ('a2', 'failure'),       # b errored
                       'r2': ('a2', 'failure')}       # b's output was empty
    pairs = {p['pair_id']: p for p in built['pairs']}
    assert set(pairs) == {'c2', 'r1', 'r1f'}
    assert pairs['c2']['tests'] == {'a': '2/4 passed', 'b': '2/4 passed'}
    assert 'tests' not in pairs['r1']
    assert pairs['r1f']['task'].startswith('The user first asked:\n\nWrite a memo.')
    assert 'memo B' not in pairs['r1f']['task']  # never an arm's earlier deliverable


def test_manifest_loads_in_quality_and_hides_the_arms(tmp_path, qp):
    bench = _bench(tmp_path)
    rb = _write_run(tmp_path, 'b', 'b', [_result('r1', 'b', 'memo B')], [])
    ra = _write_run(tmp_path, 'a2', 'a2', [_result('r1', 'a2', 'memo A')], [])
    path = qp.write(qp.build([rb, ra], 'b', 'a2', bench), tmp_path / 'out')
    quality = load_baseline_module('quality')
    [pair] = quality.load_pairs(path)
    assert (pair['a_text'], pair['b_text']) == ('memo B', 'memo A')
    messages = quality.build_messages('rubric', pair['task'], pair['a_text'], pair['b_text'])
    assert 'arm' not in messages[1]['content'].lower()
    decided = json.loads((tmp_path / 'out' / 'decided.json').read_text())
    assert decided['pair_meta']['r1']['domain'] == 'report'


def test_refuses_mixed_generators(tmp_path, qp):
    bench = _bench(tmp_path)
    one = tmp_path / 'one.json'
    one.write_text(json.dumps({'generator': 'g1', 'manifest_sha256': 'm', 'results': []}))
    two = tmp_path / 'two.json'
    two.write_text(json.dumps({'generator': 'g2', 'manifest_sha256': 'm', 'results': []}))
    with pytest.raises(SystemExit, match='more than one generator'):
        qp.build([one, two], 'b', 'a2', bench)
