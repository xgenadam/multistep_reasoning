"""qe1_analysis.py: Q-E1's pre-registered analysis on synthetic run, score and
verdict files (Q-02 stage 2; the pre-registration as amended 2026-10-24)."""

import hashlib
import json
import math

import pytest
import yaml

from tests.test_baseline.conftest import load_baseline_module


@pytest.fixture(scope='module')
def qa():
    return load_baseline_module('qe1_analysis')


@pytest.fixture(scope='module')
def qp():
    return load_baseline_module('qe1_pairs')


# ---------------------------------------------------------------------------
# Independent reference implementations (not the module's)
# ---------------------------------------------------------------------------


def ref_wilson(k, n, z=1.96):
    p = k / n
    a = p + z * z / (2 * n)
    b = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    d = 1 + z * z / n
    return (a - b) / d, (a + b) / d


def ref_power(n, p, gain=True):
    total = 0.0
    for k in range(n + 1):
        lo = ref_wilson(k, n)[0]
        if lo > 0.5 and (not gain or 10 * k >= 7 * n):
            total += math.comb(n, k) * p ** k * (1 - p) ** (n - k)
    return total


def stats(qa, wins, losses, ties=0, no_verdict=0):
    return qa.tally(['win'] * wins + ['loss'] * losses + ['tie'] * ties
                    + ['no_verdict'] * no_verdict)


# ---------------------------------------------------------------------------
# Pure statistics
# ---------------------------------------------------------------------------


def test_tally_counts_and_rates(qa):
    s = stats(qa, 7, 3, ties=2, no_verdict=1)
    assert (s['n'], s['decisive'], s['wins'], s['ties'], s['no_verdict']) == (12, 10, 7, 2, 1)
    assert s['decisive_rate'] == pytest.approx(0.7)
    assert s['all_pairs_rate'] == pytest.approx(8 / 12)
    # D-019's own example: 7/10 gives 0.40-0.89.
    assert s['wilson95'] == pytest.approx(ref_wilson(7, 10))
    assert s['wilson95'][0] == pytest.approx(0.3968, abs=1e-4)
    assert s['wilson95'][1] == pytest.approx(0.8922, abs=1e-4)
    assert qa.tally([])['decisive_rate'] is None


@pytest.mark.parametrize('k,n', [(35, 50), (33, 49), (20, 23), (4, 22), (0, 5), (5, 5)])
def test_wilson_matches_an_independent_formula(qa, k, n):
    assert stats(qa, k, n - k)['wilson95'] == pytest.approx(ref_wilson(k, n), abs=1e-12)


def test_effect_is_exact(qa):
    assert qa.meets_effect(35, 50)       # 0.70 exactly counts
    assert qa.meets_effect(7, 10)
    assert not qa.meets_effect(34, 49)   # 0.6939
    assert not qa.meets_effect(0, 0)


def test_power_matches_independent_and_the_amendment(qa):
    for n in (44, 46, 49, 52):
        for p in (0.5, 0.70, 0.75, 0.80):
            assert qa.power(n, p) == pytest.approx(ref_power(n, p), abs=1e-12)
            assert qa.power(n, p, gain=False) == pytest.approx(ref_power(n, p, False), abs=1e-12)
    # The amendment: gain bar ~47-50 % at 0.70, 76-79 % at 0.75, 94-96 % at 0.80
    # for n 46-52; "better" alone 81 % at 0.70; the coordinator's 48 % at n = 49.
    for n in (46, 49, 52):
        assert 0.465 <= qa.power(n, 0.70) <= 0.505
        assert 0.755 <= qa.power(n, 0.75) <= 0.795
        assert 0.935 <= qa.power(n, 0.80) <= 0.965
        assert qa.power(n, 0.50) <= 0.0025
        assert qa.power(n, 0.70, gain=False) == pytest.approx(0.81, abs=0.01)
    assert qa.power(49, 0.70) == pytest.approx(0.484, abs=0.001)
    note = qa.power_note(49)
    assert set(note['gain_bar']) == {'0.70', '0.75', '0.80'}
    assert note['null_gain_bar'] == pytest.approx(ref_power(49, 0.5))


# ---------------------------------------------------------------------------
# The amended Test, branch by branch
# ---------------------------------------------------------------------------


def test_gain(qa):
    c = qa.classify(stats(qa, 40, 10), stats(qa, 30, 15), 1.0)
    assert c['verdict'] == 'gain' and c['counts_for_trigger']
    assert not c['judges_disagree']


def test_better_below_the_effect(qa):
    rec = stats(qa, 33, 17)               # 0.66, Wilson lower 0.52
    assert rec['wilson95'][0] > 0.5
    c = qa.classify(rec, stats(qa, 30, 10), 1.0)
    assert c['verdict'] == 'better'
    assert c['label'].startswith('better, below the pre-registered effect')
    assert not c['counts_for_trigger']


def test_worse_and_inconclusive(qa):
    worse = qa.classify(stats(qa, 15, 35), stats(qa, 15, 35), 1.0)
    assert worse['verdict'] == 'worse' and not worse['counts_for_trigger']
    inc = qa.classify(stats(qa, 25, 25, ties=10), stats(qa, 25, 25), 1.0)
    assert inc['verdict'] == 'inconclusive'
    assert qa.classify(qa.tally([]), qa.tally([]), 1.0)['verdict'] == 'inconclusive'


def test_concurrence_disagreement_blocks_a_gain(qa):
    c = qa.classify(stats(qa, 40, 10), stats(qa, 20, 25), 1.0)
    assert c['verdict'] == 'better'
    assert 'concurrence judge does not favour' in c['label']
    assert c['conditions']['point_at_least_0.70'] and not c['conditions']['concurrence_above_0.5']
    assert c['judges_disagree'] and not c['counts_for_trigger']
    # Exactly 0.5 is not "above 0.5".
    assert qa.classify(stats(qa, 40, 10), stats(qa, 20, 20), 1.0)['verdict'] == 'better'


def test_over_resourced_relabels_worse_but_a_gain_stands(qa):
    worse = qa.classify(stats(qa, 15, 35), stats(qa, 15, 35), 1.40)
    assert worse['verdict'] == 'not_better_at_compute'
    assert worse['label'].startswith('not better at 1.40x compute')
    gain = qa.classify(stats(qa, 40, 10), stats(qa, 30, 15), 1.40)
    assert gain['verdict'] == 'gain' and gain['counts_for_trigger']
    assert 'over-resourced' in gain['label']
    # 1.25 itself is not over-resourced.
    assert qa.classify(stats(qa, 15, 35), stats(qa, 15, 35), 1.25)['verdict'] == 'worse'


def test_under_resourced_gain_does_not_trigger(qa):
    c = qa.classify(stats(qa, 40, 10), stats(qa, 30, 15), 0.60)
    assert c['verdict'] == 'gain' and not c['counts_for_trigger']
    assert 'Q-7 not met' in c['label']
    assert not qa.classify(stats(qa, 40, 10), stats(qa, 30, 15), None)['counts_for_trigger']


def test_replan_trigger(qa):
    def claim(gen, dom, status, counts):
        return {'generator': gen, 'domain': dom, 'status': status, 'counts_for_trigger': counts}
    assert qa.replan([claim('g', 'code', 'verdict', True),
                      claim('g', 'report', 'withheld', False)])['status'] == 'met'
    assert qa.replan([claim('g', 'code', 'verdict', False),
                      claim('g', 'report', 'withheld', False)])['status'] == 'undetermined'
    assert qa.replan([claim('g', 'code', 'verdict', False)])['status'] == 'not met'


def test_judge_outcomes_both_orders(qa):
    calls = [{'pair_id': 'p1', 'order': 'ab', 'repeat': 0, 'side': 'a'},
             {'pair_id': 'p1', 'order': 'ba', 'repeat': 0, 'side': 'a'},
             {'pair_id': 'p2', 'order': 'ab', 'repeat': 0, 'side': 'a'},
             {'pair_id': 'p2', 'order': 'ba', 'repeat': 0, 'side': 'b'},
             {'pair_id': 'p3', 'order': 'ab', 'repeat': 0, 'side': None},
             {'pair_id': 'p3', 'order': 'ba', 'repeat': 0, 'side': 'b'},
             {'pair_id': 'p4', 'order': 'ab', 'repeat': 0, 'side': 'b'},
             {'pair_id': 'p1', 'order': 'ab', 'repeat': 1, 'side': 'b'}]
    out, half = qa.judge_outcomes(calls)
    assert out == {'p1': 'a', 'p2': 'tie', 'p3': 'no_verdict'}
    assert half == ['p4']


# ---------------------------------------------------------------------------
# Synthetic campaign files
# ---------------------------------------------------------------------------

N = 24  # prompts per domain


def _bench(tmp_path, name='bench', ids=None, frozen=True):
    bench = tmp_path / name
    (bench / 'prompts').mkdir(parents=True)
    entries = []
    for pid in ids or ([f'c{i:02d}' for i in range(1, N + 1)]
                       + [f'r{i:02d}' for i in range(1, N + 1)]):
        dom = 'code' if pid[0] in 'cs' and not pid.startswith('sr') else 'report'
        i = int(pid[-2:])
        e = {'id': pid, 'domain': dom, 'status': 'written'}
        if i % 3 == 0:
            e['long'] = True
        if ids is None and i == N:
            e['follows'] = f'{pid[0]}{N - 1:02d}'
        if ids is None and i in (1, 2):
            e['subsets'] = ['g3']
        if ids is None and pid == 'c05':
            e['overlap'] = True
        if dom == 'code':
            e['files'] = ['task.py']
        entries.append(e)
        (bench / 'prompts' / f'{pid}.md').write_text(f'Task {pid}.')
    (bench / 'manifest.yaml').write_text(yaml.safe_dump(
        {'version': name, 'frozen': frozen, 'prompts': entries}, sort_keys=False))
    return bench


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_sha(bench):
    return hashlib.sha256((bench / 'manifest.yaml').read_text().encode()).hexdigest()


def _result(pid, arm, domain, ctok=1000, text=None, error=None, **extra):
    text = f'{arm} answer to {pid}' if text is None else text
    return {'prompt_id': pid, 'arm': arm, 'run': 0, 'domain': domain, 'error': error,
            'stratum': None, 'wall_seconds': 1.0,
            'llm': {'calls': 1, 'prompt_tokens': 100, 'completion_tokens': ctok,
                    'reasoning_tokens': 0, **extra.pop('llm', {})},
            'output': {'text': text, 'snapshot': None, 'chars': len(text)}, **extra}


def _write_run(path, bench, results, tests=None, label='q02-campaign', header=None):
    data = {'kind': 'q-e1-arms', 'generator': 'flash-next', 'bench_frozen': True,
            'manifest_sha256': _manifest_sha(bench), 'label': label, **(header or {}),
            'results': results}
    path.write_text(json.dumps(data))
    if tests is not None:
        rows = [{'prompt_id': pid, 'arm': arm, 'run': 0, 'n_tests': n, 'extraction_ok': True,
                 'tests': {'passed': k, 'collection_error': False}}
                for (pid, arm), (k, n) in tests.items()]
        path.with_suffix('.tests.json').write_text(json.dumps(
            {'run_file_sha256': _sha(path), 'results': rows}))
    return path


def _verdict(tmp_path, pairs_yaml, outcomes, model, name):
    """outcomes: pair_id -> 'a' | 'b' | 'tie' (both orders agree on a / b;
    a tie is a position flip)."""
    calls = []
    for pid, o in outcomes.items():
        sides = {'a': ('a', 'a'), 'b': ('b', 'b'), 'tie': ('a', 'b')}[o]
        for order, side in zip(('ab', 'ba'), sides):
            calls.append({'pair_id': pid, 'order': order, 'repeat': 0, 'side': side})
    text = pairs_yaml.read_text()
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps({
        'judge_model': model, 'rubric': 'pairwise_v1', 'settings': {'max_tokens': 4096},
        'pairs_path': str(pairs_yaml),
        'pairs_sha256': hashlib.sha256(text.encode()).hexdigest(), 'calls': calls}))
    return path


# Code: c01-c16 tests decide for b; c17-c20 tie on tests and go to the judge;
# c21 a2 errored; c22, c23 and the follow-up c24 tests decide for a2.
# Report: r01-r04 judged for b, r05-r20 for a2, r21-r22 ties, r23 b empty,
# r24 (follow-up) for a2.
CODE_TESTS = {**{f'c{i:02d}': ((4, 4), (2, 4)) for i in range(1, 17)},
              **{f'c{i:02d}': ((3, 4), (3, 4)) for i in range(17, 21)},
              'c21': ((4, 4), None),
              **{f'c{i:02d}': ((1, 4), (4, 4)) for i in (22, 23, 24)}}
RECORD = {'c17': 'a', 'c18': 'a', 'c19': 'a', 'c20': 'tie',
          **{f'r{i:02d}': 'a' for i in range(1, 5)},
          **{f'r{i:02d}': 'b' for i in range(5, 21)}, 'r21': 'tie', 'r22': 'tie', 'r24': 'b'}
CONCUR = {**RECORD, 'c18': 'b', 'c19': 'tie', 'c20': 'b'}


@pytest.fixture
def campaign(tmp_path, qp):
    bench = _bench(tmp_path)
    b_rows, a2_rows, tests = [], [], {}
    for i in range(1, N + 1):
        c, r = f'c{i:02d}', f'r{i:02d}'
        b_rows += [_result(c, 'b', 'code'), _result(r, 'b', 'report', text='' if i == 23 else None)]
        tb, ta = CODE_TESTS[c]
        tests[(c, 'b')] = tb
        a2_rows += [_result(c, 'a2', 'code', ctok=900, error='boom' if i == 21 else None,
                            refine_budget={'budget': 1000}),
                    _result(r, 'a2', 'report', ctok=1500, refine_budget={'budget': 1000})]
        if ta:
            tests[(c, 'a2')] = ta
    b_file = _write_run(tmp_path / 'b.json', bench, b_rows,
                        {k: v for k, v in tests.items() if k[1] == 'b'})
    a2_file = _write_run(tmp_path / 'a2.json', bench, a2_rows,
                         {k: v for k, v in tests.items() if k[1] == 'a2'},
                         header={'refine_budget': {'source': 'run-file', 'sha256': _sha(b_file)}})
    pairs = qp.write(qp.build([b_file, a2_file], 'b', 'a2', bench), tmp_path / 'pairs' / 'ba2')
    rec = _verdict(tmp_path, pairs, RECORD, 'qwen3.8-flash-next', 'v-record')
    conc = _verdict(tmp_path, pairs, CONCUR, 'devstral-2-123b-q3km', 'v-concur')
    spec = {'bench': str(bench), 'conditions': {'judge_labels': 'pass', 'spot_check': 'done'},
            'generators': {'flash-next': {
                'runs': [str(b_file), str(a2_file)],
                'verdicts': {'b:a2': {'record': str(rec), 'concurrence': str(conc)}}}}}
    return {'bench': bench, 'b': b_file, 'a2': a2_file, 'pairs': pairs, 'spec': spec,
            'tmp': tmp_path}


def _claim(rep, gen, domain):
    [c] = [c for c in rep['claims'] if (c['generator'], c['domain']) == (gen, domain)]
    return c


def test_end_to_end_claims(qa, campaign):
    rep = qa.analyse(campaign['spec'])
    code = _claim(rep, 'flash-next', 'code')
    assert code['status'] == 'verdict'
    assert code['decided_by'] == {'tests': 19, 'failure': 1, 'judge': 4}
    # Record: 16 test wins + c17-c19 judged + c21 by failure; c22-c24 lost; c20 tie.
    assert (code['record']['wins'], code['record']['losses'], code['record']['ties']) == (20, 3, 1)
    # The code tie-break re-run with Devstral: test- and failure-decided
    # prompts count the same, only c17-c20 change.
    assert (code['concurrence']['wins'], code['concurrence']['losses'],
            code['concurrence']['ties']) == (18, 5, 1)
    assert code['judges_agreement'] == {'pairs': 4, 'same': 1, 'rate': 0.25}
    assert code['q7_ratio'] == pytest.approx(0.9)
    assert code['verdict'] == 'gain' and code['counts_for_trigger']
    assert code['record']['wilson95'] == pytest.approx(ref_wilson(20, 23))
    assert code['power']['n'] == 23
    assert code['power']['gain_bar']['0.70'] == pytest.approx(ref_power(23, 0.70))

    report = _claim(rep, 'flash-next', 'report')
    assert (report['record']['wins'], report['record']['losses'], report['record']['ties']) \
        == (4, 18, 2)
    assert report['q7_ratio'] == pytest.approx(1.5)
    assert report['verdict'] == 'not_better_at_compute'    # worse, but a'' had 1.5x
    assert rep['replan_trigger']['status'] == 'met'
    assert rep['replan_trigger']['gain_cells'] == ['flash-next/code']
    # The two generators with no inputs are withheld, never guessed.
    other = _claim(rep, 'qwen3.8-27b', 'code')
    assert other['status'] == 'withheld' and other['verdict'] is None
    assert any('no run files' in r for r in other['withheld_because'])


def test_roots_only_drops_follow_ups(qa, campaign):
    rep = qa.analyse(campaign['spec'])
    [ro] = [r for r in rep['roots_only'] if (r['generator'], r['domain'])
            == ('flash-next', 'code')]
    assert (ro['record']['wins'], ro['record']['losses'], ro['record']['ties']) == (20, 2, 1)
    assert ro['verdict'] == 'gain' and ro['agrees_with_full']
    [rr] = [r for r in rep['roots_only'] if (r['generator'], r['domain'])
            == ('flash-next', 'report')]
    assert rr['record']['losses'] == 17                 # r24 is a follow-up


def test_long_short_split(qa, campaign):
    rep = qa.analyse(campaign['spec'])
    [ls] = [r for r in rep['long_short'] if (r['generator'], r['domain'])
            == ('flash-next', 'code')]
    long_ids = {f'c{i:02d}' for i in range(3, N + 1, 3)}         # c03, c06, ..., c24
    code = _claim(rep, 'flash-next', 'code')
    lw = sum(r['flash-next'] == 'win' for r in code['rows'] if r['prompt_id'] in long_ids)
    ll = sum(r['flash-next'] == 'loss' for r in code['rows'] if r['prompt_id'] in long_ids)
    assert (ls['long']['wins'], ls['long']['losses']) == (lw, ll)
    assert ls['long']['wilson95'] == pytest.approx(ref_wilson(lw, lw + ll))
    assert ls['long']['decisive'] + ls['short']['decisive'] == code['record']['decisive']


def test_q7_table(qa, campaign):
    rep = qa.analyse(campaign['spec'])
    q = rep['q7']['flash-next']
    assert q['code']['a2_arm'] == 'a2@budget'
    assert q['code']['q7_met'] and not q['code']['over_resourced']
    assert q['report']['over_resourced']
    assert q['report']['per_prompt_ratio']['median'] == pytest.approx(1.5)
    assert q['code']['per_prompt_ratio']['n'] == N - 1           # c21's a2 errored
    assert q['budget_problems'] == []


def test_missing_concurrence_withholds_every_claim(qa, campaign):
    spec = campaign['spec']
    del spec['generators']['flash-next']['verdicts']['b:a2']['concurrence']
    rep = qa.analyse(spec)
    for dom in ('code', 'report'):
        c = _claim(rep, 'flash-next', dom)
        assert c['status'] == 'withheld' and c['verdict'] is None
        assert any('no devstral verdict file' in r for r in c['withheld_because'])
        assert c['record'] is not None          # the record judge's data still shows
    assert rep['replan_trigger']['status'] == 'undetermined'


def test_unjudged_pair_withholds(qa, campaign):
    rec = {k: v for k, v in RECORD.items() if k != 'c17'}
    path = _verdict(campaign['tmp'], campaign['pairs'], rec, 'qwen3.8-flash-next', 'v-partial')
    campaign['spec']['generators']['flash-next']['verdicts']['b:a2']['record'] = str(path)
    rep = qa.analyse(campaign['spec'])
    code = _claim(rep, 'flash-next', 'code')
    assert code['status'] == 'withheld'
    assert any('without a verdict: c17' in r for r in code['withheld_because'])
    assert _claim(rep, 'flash-next', 'report')['status'] == 'verdict'


def test_missing_arm_is_not_a_win(qa, campaign):
    """Without the a2 run file, every prompt would be an a2 'loss by failure'
    and a spurious gain; the analysis withholds instead."""
    campaign['spec']['generators']['flash-next']['runs'] = [str(campaign['b'])]
    rep = qa.analyse(campaign['spec'])
    for dom in ('code', 'report'):
        c = _claim(rep, 'flash-next', dom)
        assert c['status'] == 'withheld'
        assert any('arm a2 has no result' in r for r in c['withheld_because'])
    assert rep['replan_trigger']['status'] == 'undetermined'


def test_missing_test_scores_withhold_code_only(qa, campaign):
    campaign['a2'].with_suffix('.tests.json').unlink()
    rep = qa.analyse(campaign['spec'])
    assert _claim(rep, 'flash-next', 'code')['status'] == 'withheld'
    assert _claim(rep, 'flash-next', 'report')['status'] == 'verdict'


def test_reversed_manifest_is_refused(qa, qp, campaign):
    """Verdicts judged on an a2:b manifest would flip every outcome."""
    rev = qp.write(qp.build([campaign['b'], campaign['a2']], 'a2', 'b', campaign['bench']),
                   campaign['tmp'] / 'pairs' / 'a2b')
    path = _verdict(campaign['tmp'], rev, RECORD, 'qwen3.8-flash-next', 'v-rev')
    conc = _verdict(campaign['tmp'], rev, CONCUR, 'devstral-2-123b-q3km', 'v-rev-c')
    campaign['spec']['generators']['flash-next']['verdicts']['b:a2'] = {
        'record': str(path), 'concurrence': str(conc)}
    rep = qa.analyse(campaign['spec'])
    c = _claim(rep, 'flash-next', 'report')
    assert c['status'] == 'withheld'
    assert any('expected a = b, b = a2' in r for r in c['withheld_because'])


def test_wrong_judge_model_is_refused(qa, campaign):
    swapped = campaign['spec']['generators']['flash-next']['verdicts']['b:a2']
    swapped['record'], swapped['concurrence'] = swapped['concurrence'], swapped['record']
    rep = qa.analyse(campaign['spec'])
    assert _claim(rep, 'flash-next', 'code')['status'] == 'withheld'


def test_pilot_run_files_are_refused(qa, campaign, tmp_path):
    data = json.loads(campaign['b'].read_text())
    data['label'] = 'q02-pilot-code'
    campaign['b'].write_text(json.dumps(data))
    rep = qa.analyse(campaign['spec'])
    c = _claim(rep, 'flash-next', 'report')
    assert c['status'] == 'withheld' and any('pilot' in r for r in c['withheld_because'])


def test_conditions_mark_the_verdict_provisional(qa, campaign):
    campaign['spec']['conditions'] = {}
    rep = qa.analyse(campaign['spec'])
    prov = rep['conditions']['provisional']
    assert any('R1-R5' in p for p in prov) and any('blind spot' in p for p in prov)
    assert _claim(rep, 'flash-next', 'code')['provisional'] == prov


def test_judge_of_record_swaps_if_flash_next_fails_the_labels(qa, campaign):
    campaign['spec']['conditions']['judge_labels'] = 'fail'
    rep = qa.analyse(campaign['spec'])
    assert rep['pre_registered']['judge_of_record'] == 'devstral'
    code = _claim(rep, 'flash-next', 'code')
    assert code['record']['wins'] == 18 and code['concurrence']['wins'] == 20


# ---------------------------------------------------------------------------
# Secondary pairings, the A/A control and the standard slice
# ---------------------------------------------------------------------------


def test_c_vs_b_on_the_overlap_subset(qa, qp, campaign):
    tmp, bench = campaign['tmp'], campaign['bench']
    overlap = ['c05', 'c24', 'r24']                       # c05's flag, and the follow-ups
    cons = {'by_kind': {'consolidate': {'count': 1}},
            'by_phase': {'Updating summary after consolidation': {'count': 1}}}
    rows = [_result(p, 'c', 'code' if p[0] == 'c' else 'report',
                    llm=cons if p == 'c05' else {'by_kind': {'consolidate': {'count': 1}}})
            for p in overlap]
    c_file = _write_run(tmp / 'c.json', bench, rows,
                        {('c05', 'c'): (4, 4), ('c24', 'c'): (1, 4)})
    runs = [campaign['b'], campaign['a2'], c_file]
    pairs = qp.write(qp.build(runs, 'c', 'b', bench, subset='overlap'), tmp / 'pairs' / 'cb')
    v = _verdict(tmp, pairs, {'c05': 'b', 'c24': 'a', 'r24': 'tie'}, 'qwen3.8-flash-next',
                 'v-cb')
    g = campaign['spec']['generators']['flash-next']
    g['runs'].append(str(c_file))
    g['verdicts']['c:b'] = {'record': str(v)}
    rep = qa.analyse(campaign['spec'])
    sec = {(s['pairing'], s['domain']): s for s in rep['secondary']
           if s['generator'] == 'flash-next'}
    code, report = sec[('c vs b', 'code')], sec[('c vs b', 'report')]
    # c05 and c24 tie on tests (4/4, 1/4 each) and go to the judge.
    assert code['prompts'] == 2 and code['missing'] is None
    assert (code['record']['wins'], code['record']['losses']) == (1, 1)
    assert code['consolidation'] == {'turns': 2, 'error_free': 2, 'consolidate_called': 2,
                                     'changed': 1}
    # Prompts outside the subset are never "c not run" wins for b.
    assert report['record']['n'] == 1 and report['record']['ties'] == 1
    assert report['consolidation']['turns'] == 1


def test_secondary_without_verdicts_reports_missing(qa, campaign):
    rep = qa.analyse(campaign['spec'])
    [s] = [s for s in rep['secondary'] if s['generator'] == 'flash-next'
           and s['pairing'] == 'b vs a' and s['domain'] == 'code']
    assert s['record'] is None and any('arm a has no result' in m for m in s['missing'])


def test_aa_control(qa, qp, campaign):
    tmp, bench = campaign['tmp'], campaign['bench']
    rep_rows = [_result(p, 'b', 'code' if p[0] == 'c' else 'report')
                for p in ('c01', 'c02', 'r01', 'r02')]
    rep_file = _write_run(tmp / 'b-repeat.json', bench, rep_rows,
                          {('c01', 'b'): (4, 4), ('c02', 'b'): (3, 4)}, label='q02-aa-repeat')
    built = qp.build([campaign['b']], 'b', 'b', bench, repeat_files=[rep_file], subset='g3')
    assert {d['prompt_id']: d['winner'] for d in built['decided']} == {'c02': 'a'}
    assert {p['pair_id'] for p in built['pairs']} == {'c01', 'r01', 'r02'}
    pairs = qp.write(built, tmp / 'pairs' / 'aa-b')
    v = _verdict(tmp, pairs, {'c01': 'tie', 'r01': 'tie', 'r02': 'b'}, 'qwen3.8-flash-next',
                 'v-aa-b')
    campaign['spec']['generators']['flash-next']['aa'] = {
        'runs': [str(rep_file)], 'verdicts': {'b': str(v)}}
    rep = qa.analyse(campaign['spec'])
    aa = rep['aa']['flash-next']
    assert aa['b']['code']['stats']['all_pairs_rate'] == pytest.approx(0.75)   # c02 win, c01 tie
    assert aa['b']['report']['stats']['all_pairs_rate'] == pytest.approx(0.25)  # tie, loss
    assert aa['a2']['code']['stats'] is None and aa['a2']['code']['missing']


def test_standard_slice(qa, qp, campaign):
    tmp = campaign['tmp']
    std = _bench(tmp, 'std', ids=['sc01', 'sc02', 'sr01', 'sr02', 'sr03'])
    rows = [_result('sc01', 'b', 'code'), _result('sc01', 'a2', 'code'),
            _result('sc02', 'b', 'code'), _result('sc02', 'a2', 'code'),
            _result('sr01', 'b', 'report'), _result('sr01', 'a2', 'report'),
            _result('sr02', 'b', 'report'), _result('sr02', 'a2', 'report'),
            _result('sr03', 'b', 'report', error='boom'), _result('sr03', 'a2', 'report')]
    run = _write_run(tmp / 'std.json', std, rows,
                     {('sc01', 'b'): (5, 5), ('sc01', 'a2'): (3, 5),
                      ('sc02', 'b'): (2, 5), ('sc02', 'a2'): (2, 5)}, label='q02-std')

    def ife(pid, arm, flags):
        return {'prompt_id': pid, 'arm': arm, 'run': 0,
                'strict': {'all': all(flags),
                           'per_instruction': {f'i{k}': f for k, f in enumerate(flags)}}}
    run.with_suffix('.ifeval.json').write_text(json.dumps({'results': [
        ife('sr01', 'b', [True, True, True]), ife('sr01', 'a2', [True, False, True]),
        ife('sr02', 'b', [True, False]), ife('sr02', 'a2', [False, True]),
        # an errored output trivially "follows" a no-comma rule: it still loses
        ife('sr03', 'b', [True]), ife('sr03', 'a2', [False])], 'summary': {}}))
    pairs = qp.write(qp.build([run], 'b', 'a2', std), tmp / 'pairs' / 'std')
    v = _verdict(tmp, pairs, {'sc02': 'a'}, 'qwen3.8-flash-next', 'v-std')
    campaign['spec']['std_bench'] = str(std)
    campaign['spec']['generators']['flash-next']['std'] = {
        'runs': [str(run)], 'verdicts': {'b:a2': {'record': str(v)}}}
    rep = qa.analyse(campaign['spec'])
    s = rep['std']['flash-next']
    assert s['code']['stats']['wins'] == 2 and s['code']['decided_by']['tests'] == 1
    assert s['code']['task_pass']['b']['passed'] == 1
    assert s['code']['task_pass']['a2']['passed'] == 0
    r = s['report']['stats']
    assert (r['wins'], r['losses'], r['ties']) == (1, 1, 1)
    # Beside v1's short strata only.
    code_rows = _claim(rep, 'flash-next', 'code')['rows']
    short = [x for x in code_rows if not x['long']]
    assert s['v1_short']['code']['n'] == len(short)


def test_cli_writes_json_and_markdown(qa, campaign):
    spec = campaign['tmp'] / 'spec.yaml'
    spec.write_text(yaml.safe_dump(campaign['spec']))
    out = campaign['tmp'] / 'out'
    assert qa.main(['report', '--spec', str(spec), '--out', str(out)]) == 0
    rep = json.loads((out / 'qe1_analysis.json').read_text())
    assert rep['replan_trigger']['status'] == 'met'
    assert rep['spec']['sha256'] == _sha(spec)
    md = (out / 'qe1_analysis.md').read_text()
    assert 'Re-plan trigger: met' in md
    assert 'not better at 1.50x compute' in md
    assert str(campaign['a2']) in rep['inputs']


def test_budget_from_another_file_is_a_caveat(qa, campaign):
    data = json.loads(campaign['a2'].read_text())
    data['refine_budget'] = {'source': 'run-file', 'sha256': '0' * 64, 'path': 'elsewhere.json'}
    campaign['a2'].write_text(json.dumps(data))
    # Re-score so the sidecar matches the edited run file.
    side = campaign['a2'].with_suffix('.tests.json')
    scored = json.loads(side.read_text())
    scored['run_file_sha256'] = _sha(campaign['a2'])
    side.write_text(json.dumps(scored))
    rep = qa.analyse(campaign['spec'])
    code = _claim(rep, 'flash-next', 'code')
    assert code['status'] == 'withheld'      # the pairs manifest was built from the old a2 file
    assert any('not in the spec' in r for r in code['withheld_because'])
    assert any('b run file not in the spec' in c for c in code['caveats'])


def test_stale_test_scores_withhold_code(qa, campaign):
    side = campaign['b'].with_suffix('.tests.json')
    scored = json.loads(side.read_text())
    scored['run_file_sha256'] = 'f' * 64
    side.write_text(json.dumps(scored))
    rep = qa.analyse(campaign['spec'])
    code = _claim(rep, 'flash-next', 'code')
    assert code['status'] == 'withheld'
    assert any('scored another version' in r for r in code['withheld_because'])


def test_q7_ratio_is_not_rounded(qa, tmp_path):
    bench = _bench(tmp_path)
    rows = []
    for i in range(1, N + 1):
        c = f'c{i:02d}'
        rows += [_result(c, 'b', 'code', ctok=10000),
                 _result(c, 'a2', 'code', ctok=7496, refine_budget={'budget': 10000})]
    run = _write_run(tmp_path / 'r.json', bench, rows)
    results, _, _ = qa.load_all([run])
    q = qa.q7_report([run], qa.arms.load_bench(bench)['prompts'], results, 'flash-next')
    assert q['code']['ratio_of_medians'] == pytest.approx(0.7496)
    assert q['code']['q7_met'] is False      # match_report's 3-place rounding would say 0.75
