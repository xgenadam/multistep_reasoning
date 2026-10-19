"""Re-scoring the tracked run files reproduces S-002's verdicts (0-14, P0-6).

Run files from before 0-14 carry keyword labels (`by_kind`) and the status
text each call ran under (`by_phase`). Mapping `by_phase` through the
harness's phase_kind() gives the labels a fresh run would get: they agree
with the keyword labels on compose, consolidate and decompose (the kinds
S-002's verdicts rest on) and show where the keywords went wrong (N13).
"""

import json
from collections import Counter

import pytest

from .conftest import RUNS

RUN_FILES = sorted(RUNS.glob('*.json'))
BASELINE = RUNS / '20261015T143545Z_pre-consolidation-baseline_s1_cli_code-s2_report-s3_followup-s4_anchors.json'
SMOKE = RUNS / '20261015T132320Z_smoke_s1_cli_code.json'
POST_MERGE = RUNS / '20261015T182246Z_post-merge-0.04_s1_cli_code-s2_report-s3_followup.json'
AB_CONTROL = RUNS / '20261015T192509Z_0-06-ab-control_s4_anchors.json'
AB_TREATMENT = RUNS / '20261015T194221Z_0-06-ab-treatment_s4_anchors.json'


def _turns(path):
    run = json.loads(path.read_text())
    for rec in run['results']:
        for turn in rec['turns']:
            yield rec, turn


def _phase_counts(harness, llm: dict) -> Counter:
    counts: Counter = Counter()
    for phase, agg in llm['by_phase'].items():
        counts[harness.phase_kind(phase) or 'unmapped'] += agg['count']
    return counts


def test_tracked_run_files_are_present():
    assert len(RUN_FILES) >= 10
    assert all(p.exists() for p in (BASELINE, SMOKE, POST_MERGE, AB_CONTROL, AB_TREATMENT))


@pytest.mark.parametrize('path', RUN_FILES, ids=lambda p: p.name[:16])
def test_phase_labels_agree_with_keyword_labels(harness, path):
    for _, turn in _turns(path):
        llm = turn['llm']
        assert 'label_sources' not in llm  # legacy file: keyword fallback
        kw = Counter({k: v['count'] for k, v in llm['by_kind'].items()})
        ph = _phase_counts(harness, llm)
        assert 'unmapped' not in ph
        assert sum(ph.values()) == sum(kw.values()) == llm['calls']
        # The verdict kinds agree exactly ...
        assert ph['compose'] == kw['compose']
        assert ph['consolidate'] == kw['consolidate']
        # ... the decompose phase also holds the one critique per turn ...
        assert ph['decompose'] == kw['decompose'] + 1
        # ... and N13 as found: executor rounds were labelled `summary`,
        # summary updates plus the critique `system_other`.
        assert kw['summary'] == ph['executor_turn']
        assert kw['system_other'] == ph['summary'] + 1


def test_s002_compose_and_decompose_verdicts_reproduce():
    # S-002: "Compose call p50 ≈ 13–18 s (smoke: 13.3 s p50)"; "decompose +
    # critique pair ... 40–97 s per call".
    turns = [turn for _, turn in _turns(BASELINE)]
    assert len(turns) == 6  # s1, s2, s4 x 2 (s3 ran in its own file)
    for turn in turns:
        by_kind = turn['llm']['by_kind']
        assert 13.0 <= by_kind['compose']['p50_s'] <= 18.0
        assert 40.0 <= by_kind['decompose']['p50_s'] <= 97.0
    [(_, smoke)] = list(_turns(SMOKE))
    assert smoke['llm']['by_kind']['compose']['p50_s'] == pytest.approx(13.3, abs=0.05)


def test_s003_consolidate_verdict_reproduces_and_is_contaminated(compare, capsys):
    code = compare.main([str(AB_CONTROL), str(AB_TREATMENT), '--scenario', 's4_anchors'])
    out = capsys.readouterr().out
    # S-003: "G1: consolidate p50 79.99 s ÷ compose p50 39.83 s = 2.01×" and
    # "both arms contaminated".
    assert 'G1 FAIL: consolidate p50 79.99 s / compose p50 39.83 s = 2.01x' in out
    assert '+41.5%' in out
    assert 'G2 UNMEASURABLE' in out  # no per-kind tokens before 0-14
    assert 'CONTAMINATED A: compose p50 30.55 s' in out
    assert 'CONTAMINATED B: compose p50 39.83 s' in out
    assert code == compare.EXIT_CONTAMINATED


def test_check_scores_every_tracked_file(check):
    scenarios = check.load_scenarios()
    for path in RUN_FILES:
        for rec, turn in _turns(path):
            scenario = scenarios[rec['scenario']]
            checks = check.score_scenario(rec['scenario'], scenario['expect'], turn)
            checks.append(check.label_check(turn))
            assert checks
            name, ok, detail = checks[-1]
            assert ok is None and 'predates 0-14' in detail


def _score(check, path, scenario_id, index):
    scenarios = check.load_scenarios()
    run = json.loads(path.read_text())
    rec = next(r for r in run['results'] if r['scenario'] == scenario_id)
    turn = rec['turns'][index]
    prior = rec['turns'][index - 1] if index else None
    exp = scenarios[scenario_id]['expect']
    return {name: (ok, detail)
            for name, ok, detail in check.score_scenario(
                scenario_id, exp, turn, prior, is_followup=bool(index))}


def test_new_p0_checks_on_tracked_runs(check):
    # P0-1: the pre-0-05 baseline s1 carries prose sections next to the code
    # (S-002: "the zero prose-about-the-tool half of P0-1 is not met").
    s1 = _score(check, BASELINE, 's1_cli_code', 0)
    assert s1['prose (section) parts <= 0 (P0-1)'][0] is False
    # P0-2: the post-merge report has no file parts.
    s2 = _score(check, POST_MERGE, 's2_report', 0)
    assert s2['file parts <= 0 (P0-2)'][0] is True
    # P0-3: the post-merge follow-up rebuilt the document (S-002: "add ×3 →
    # delete ×3 → add ×1, rebuild churn"); no merge, no patch.
    s3 = _score(check, POST_MERGE, 's3_followup', 1)
    ok, detail = s3['follow-up op log has merge_parts or a patch (P0-3)']
    assert ok is False and "'delete_part': 3" in detail
    # N17: a one-part document has no pair to compare.
    assert s3['max dup Jaccard < 0.5'] == (None, 'n/a: 1 part(s)')


def test_check_main_reports_timing_verdicts(check, monkeypatch, capsys):
    # S-002's baseline ran serial and uncontested; the 0-06 arms did not.
    monkeypatch.setattr('sys.argv', ['check.py', str(BASELINE)])
    check.main()
    assert capsys.readouterr().out.count('timing: clean') == 6
    monkeypatch.setattr('sys.argv', ['check.py', str(AB_TREATMENT)])
    assert check.main() == 0  # shape checks pass; timing is reported, not scored
    assert 'timing: CONTAMINATED: compose p50 39.83 s' in capsys.readouterr().out
