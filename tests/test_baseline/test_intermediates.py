"""intermediates.py: every intermediate output scored, final beside the best (Q-02)."""

import json

import pytest
import yaml

from tests.test_baseline.conftest import load_baseline_module

GOOD = 'def add(a, b):\n    return a + b\n'
BAD = 'def add(a, b):\n    return a - b\n'


@pytest.fixture(scope='module')
def inter():
    return load_baseline_module('intermediates')


def _bench(tmp_path):
    bench = tmp_path / 'bench'
    for d in ('prompts', 'tests/c01', 'reference/c01', 'checklists'):
        (bench / d).mkdir(parents=True)
    (bench / 'manifest.yaml').write_text(yaml.safe_dump({'version': 't', 'prompts': [
        {'id': 'c01', 'domain': 'code', 'files': ['calc.py']},
        {'id': 'r01', 'domain': 'report'}]}))
    (bench / 'tests/c01/test_calc.py').write_text(
        'from calc import add\n\n'
        'def test_one():\n    assert add(1, 1) == 2\n\n'
        'def test_two():\n    assert add(2, 3) == 5\n')
    (bench / 'reference/c01/calc.py').write_text(GOOD)
    (bench / 'checklists/r01.yaml').write_text(yaml.safe_dump({'items': [
        {'id': 'risks', 'check': 'heading', 'pattern': '(?i)risks'},
        {'id': 'plan', 'check': 'heading', 'pattern': '(?i)plan'}]}))
    return bench


def _code(body):
    return f'calc.py\n```python\n{body}```\n'


def test_scores_self_refine_rounds_and_harness_steps(inter, tmp_path):
    bench = _bench(tmp_path)
    turn_dir = tmp_path / 'intermediates' / 'run' / 'b_r01_r0_t0'
    turn_dir.mkdir(parents=True)
    # The harness's Document after step 1 has both headings; its final one lost one.
    doc1 = {'parts': [{'id': 'a', 'kind': 'section', 'title': 'Risks', 'body': 'x'},
                      {'id': 'b', 'kind': 'section', 'title': 'Plan', 'body': 'y'}]}
    doc2 = {'parts': [{'id': 'a', 'kind': 'section', 'title': 'Risks', 'body': 'x'}]}
    for i, (step, snap, tok) in enumerate([(1, doc1, 100), (2, doc2, 250)], start=2):
        (turn_dir / f'{i:02d}_document_{step}.json').write_text(json.dumps(
            {'kind': 'document', 'step': step, 'completion_tokens': tok, 'snapshot': snap}))
    run = tmp_path / 'run.json'
    run.write_text(json.dumps({'generator': 'flash-next', 'results': [
        {'prompt_id': 'c01', 'arm': 'a2', 'run': 0, 'error': None, 'stratum': 'code-short',
         'output': {'text': _code(GOOD)},
         'rounds': [{'round': 0, 'draft': _code(BAD), 'completion_tokens': 10},
                    {'round': 1, 'draft': _code(GOOD), 'completion_tokens': 20},
                    {'round': 2, 'draft': '', 'completion_tokens': 5, 'discarded': True}]},
        {'prompt_id': 'r01', 'arm': 'b', 'run': 0, 'error': None, 'stratum': 'report-short',
         'output': {'text': '', 'snapshot': doc2},
         'intermediates': {'dir': str(turn_dir), 'files': 2}},
    ]}))
    report = inter.score_run(run, bench, jobs=1)
    a2, b = report['results']
    assert [(s['step'], s['tokens'], s['score'], s['discarded']) for s in a2['steps']] == [
        (0, 10, 0.0, False), (1, 30, 1.0, False), (2, 35, 0.0, True)]
    assert a2['final']['score'] == 1.0 and a2['best'] == {'step': 1, 'score': 1.0, 'tokens': 30}
    assert a2['final_is_best'] is True
    assert [(s['step'], s['score']) for s in b['steps']] == [(1, 1.0), (2, 0.5)]
    assert b['final']['score'] == 0.5 and b['best']['step'] == 1 and b['final_is_best'] is False
    assert report['summary']['b/report'] == {'prompts': 1, 'final_mean': 0.5, 'best_mean': 1.0,
                                             'final_is_best_share': 0.0, 'steps_median': 2}
