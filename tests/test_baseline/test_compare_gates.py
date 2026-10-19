"""compare.py gates and exit codes on 0-14 run files (D-007, P0-6)."""

import json

import pytest

CONS_SUMMARY = 'Updating summary after consolidation'


def _run_file(harness, tmp_path, name, *, jobs=1, compose_s=15.0, consolidate_s=20.0,
              consolidate_tokens=100, consolidate=True):
    """A one-turn s4 run file whose llm block comes from harness.llm_stats."""
    def call(i, kind, phase, seconds, tokens):
        return harness.CallRecord(
            index=i, kind=kind, stream=False, phase=phase, seconds=seconds,
            first_token_s=seconds, chunks=1, prompt_tokens=tokens, completion_tokens=0,
            label_source='phase', usage_reported=True,
        )

    calls = [
        call(0, 'decompose', 'Decomposing the request into sub-tasks…', 40.0, 400),
        call(1, 'executor_turn', 'Executing 1/1: a', 30.0, 300),
        call(2, 'compose', 'Composing after 1/1: a', compose_s, 200),
        call(3, 'summary', 'Updating summary after 1/1: a', 10.0, 100),
    ]
    if consolidate:
        calls += [
            call(4, 'consolidate', 'Consolidating document', consolidate_s, consolidate_tokens),
            call(5, 'summary', CONS_SUMMARY, 10.0, 100),
        ]
    run = {
        'backend': 'http://host.containers.internal:5000/v1', 'jobs': jobs,
        'results': [{'scenario': 's4_anchors', 'run': 0, 'turns': [{
            'index': 0, 'wall_seconds': 100.0, 'llm': harness.llm_stats(calls),
        }]}],
    }
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(run))
    return str(path)


def test_clean_runs_that_meet_both_gates_exit_0(harness, compare, tmp_path, capsys):
    a = _run_file(harness, tmp_path, 'a', consolidate=False)
    b = _run_file(harness, tmp_path, 'b')
    assert compare.main([a, b]) == compare.EXIT_PASS
    out = capsys.readouterr().out
    # Marginal: consolidate 100 + its summary 100 over a 1,200-token turn.
    assert 'G2 PASS: marginal tokens 200 (consolidate 100 + summary 100) / turn total 1200 = 16.7%' in out
    assert 'base_url=http://host.containers.internal:5000/v1 jobs=1' in out


def test_marginal_share_over_25_percent_fails_g2(harness, compare, tmp_path, capsys):
    a = _run_file(harness, tmp_path, 'a', consolidate=False)
    b = _run_file(harness, tmp_path, 'b', consolidate_tokens=1000)
    assert compare.main([a, b]) == compare.EXIT_FAIL
    assert 'G2 FAIL: marginal tokens 1100' in capsys.readouterr().out


def test_slow_consolidate_fails_g1(harness, compare, tmp_path, capsys):
    a = _run_file(harness, tmp_path, 'a', consolidate=False)
    b = _run_file(harness, tmp_path, 'b', consolidate_s=30.0)
    assert compare.main([a, b]) == compare.EXIT_FAIL
    assert 'G1 FAIL' in capsys.readouterr().out


@pytest.mark.parametrize('arm', ['a', 'b'])
def test_jobs_above_1_is_contaminated(harness, compare, tmp_path, capsys, arm):
    a = _run_file(harness, tmp_path, 'a', consolidate=False, jobs=3 if arm == 'a' else 1)
    b = _run_file(harness, tmp_path, 'b', jobs=3 if arm == 'b' else 1)
    assert compare.main([a, b]) == compare.EXIT_CONTAMINATED
    assert f'CONTAMINATED {arm.upper()}: jobs=3' in capsys.readouterr().out


def test_inflated_compose_p50_is_contaminated(harness, compare, tmp_path, capsys):
    limit = compare.CONTAMINATION_FACTOR * compare.CLEAN_COMPOSE_P50_S
    a = _run_file(harness, tmp_path, 'a', consolidate=False, compose_s=limit)  # at the limit: clean
    b = _run_file(harness, tmp_path, 'b', compose_s=limit + 0.5, consolidate_s=limit)
    assert compare.main([a, b]) == compare.EXIT_CONTAMINATED
    out = capsys.readouterr().out
    assert 'CONTAMINATED B: compose p50' in out
    assert 'CONTAMINATED A' not in out


def test_missing_usage_makes_g2_unmeasurable(harness, compare, tmp_path, capsys):
    a = _run_file(harness, tmp_path, 'a', consolidate=False)
    b_path = _run_file(harness, tmp_path, 'b')
    run = json.loads(open(b_path).read())
    run['results'][0]['turns'][0]['llm']['by_phase'][CONS_SUMMARY]['calls_without_usage'] = 1
    open(b_path, 'w').write(json.dumps(run))
    assert compare.main([a, b_path]) == compare.EXIT_FAIL
    assert 'G2 UNMEASURABLE: 1 marginal call(s) carry no usage' in capsys.readouterr().out
