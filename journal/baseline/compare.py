#!/usr/bin/env python3
"""A/B comparison of two harness run files (0-06 consolidation gate).

Usage:
    compare.py RUN_A.json RUN_B.json [--scenario s4_anchors] [--turn 0]

RUN_A: control (default pipeline, no consolidation).
RUN_B: treatment (run with --consolidation).

Gates (P0-4, D-007; both measured in RUN_B):
  G1  consolidate call p50  <= 1.5x compose p50
  G2  marginal tokens (the consolidate call + the summary call it triggers)
      / the turn total  <= 25%   (prompt + completion)

The B-vs-A turn-total growth is REPORTED, not gated: turn totals vary
36K-305K across identical scenarios (D-007). So are per-turn wall_seconds.

Contamination (D-007): a run is contaminated when it ran with jobs != 1, or
when its compose p50 exceeds 1.3x the recorded clean compose p50
(CLEAN_COMPOSE_P50_S). Its wall times then say nothing about the pipeline.

Exit codes: 0 every gate passes; 1 a gate fails or cannot be measured;
2 either run is contaminated (the gates are printed but do not count).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MARGINAL_TOKENS_MAX = 0.25
CONS_VS_COMPOSE_MAX = 1.5
# Clean compose p50 on the generator, the contamination yardstick. S-002's
# uncontested baseline (Qwen3.8-27B, :5000) put it at 13-18 s; the upper end
# stands until 0-16 re-baselines and replaces it.
CLEAN_COMPOSE_P50_S = 18.0
CONTAMINATION_FACTOR = 1.3
# The orchestrator status for the summary call consolidation triggers
# (harness.CONSOLIDATION_SUMMARY_PHASE).
CONSOLIDATION_SUMMARY_PHASE = 'Updating summary after consolidation'

EXIT_PASS, EXIT_FAIL, EXIT_CONTAMINATED = 0, 1, 2


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def find_result(d: dict, scenario_id: str) -> dict:
    for r in d['results']:
        if r['scenario'] == scenario_id:
            return r
    raise SystemExit(f'scenario {scenario_id!r} not in run '
                     f'({[r["scenario"] for r in d["results"]]})')


def contamination(run: dict, turn: dict) -> list[str]:
    """Reasons this run's timings are void; empty when it is clean."""
    reasons = []
    jobs = run.get('jobs')
    if jobs != 1:
        reasons.append(f'jobs={jobs} (timing gates need --jobs 1)')
    p50 = ((turn['llm'].get('by_kind') or {}).get('compose') or {}).get('p50_s')
    limit = CONTAMINATION_FACTOR * CLEAN_COMPOSE_P50_S
    if p50 is not None and p50 > limit:
        reasons.append(f'compose p50 {p50:.2f} s > {CONTAMINATION_FACTOR}x clean '
                       f'{CLEAN_COMPOSE_P50_S:.1f} s = {limit:.1f} s')
    return reasons


def _tokens(agg: dict) -> int:
    return agg.get('prompt_tokens', 0) + agg.get('completion_tokens', 0)


def marginal_tokens(llm: dict) -> tuple[int | None, str]:
    """D-007 marginal cost of consolidation in one turn, or None + why not.

    Needs per-kind and per-phase token sums (harness 0-14) with usage on
    every marginal call; older run files cannot be attributed.
    """
    cons = (llm.get('by_kind') or {}).get('consolidate')
    summ = (llm.get('by_phase') or {}).get(CONSOLIDATION_SUMMARY_PHASE)
    marginal = [a for a in (cons, summ) if a]
    if not marginal:
        return None, 'no consolidate call'
    if any('prompt_tokens' not in a for a in marginal):
        return None, 'run file predates per-kind token sums (0-14)'
    missing = sum(a.get('calls_without_usage', 0) for a in marginal)
    if missing:
        return None, f'{missing} marginal call(s) carry no usage'
    return sum(_tokens(a) for a in marginal), (
        f'consolidate {_tokens(cons) if cons else 0} + summary '
        f'{_tokens(summ) if summ else 0}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('run_a', help='control run file (no consolidation)')
    ap.add_argument('run_b', help='treatment run file (--consolidation)')
    ap.add_argument('--scenario', default='s4_anchors',
                    help='scenario id to compare (default: s4_anchors)')
    ap.add_argument('--turn', type=int, default=0,
                    help='turn index to compare (default: 0)')
    args = ap.parse_args(argv)

    run_a, run_b = load(args.run_a), load(args.run_b)
    a = find_result(run_a, args.scenario)['turns'][args.turn]
    b = find_result(run_b, args.scenario)['turns'][args.turn]

    la, lb = a['llm'], b['llm']
    tok_a = la['prompt_tokens'] + la['completion_tokens']
    tok_b = lb['prompt_tokens'] + lb['completion_tokens']
    growth = (tok_b - tok_a) / tok_a if tok_a else float('inf')

    cons = lb['by_kind'].get('consolidate')
    comp = lb['by_kind'].get('compose') or {}
    comp_p50 = comp.get('p50_s')

    print(f'compare  A={Path(args.run_a).name}')
    print(f'           base_url={run_a.get("backend")} jobs={run_a.get("jobs")}')
    print(f'         B={Path(args.run_b).name}')
    print(f'           base_url={run_b.get("backend")} jobs={run_b.get("jobs")}')
    if run_a.get('backend') != run_b.get('backend'):
        print('WARNING: A and B ran against different endpoints')
    print(f'scenario {args.scenario} turn {args.turn}')
    print()
    print(f'{"":24s}{"A (control)":>16s}{"B (consol.)":>16s}')
    print(f'{"wall_seconds":24s}{a["wall_seconds"]:16.1f}{b["wall_seconds"]:16.1f}   (reported, not gated)')
    print(f'{"prompt tokens":24s}{la["prompt_tokens"]:16d}{lb["prompt_tokens"]:16d}')
    print(f'{"completion tokens":24s}{la["completion_tokens"]:16d}{lb["completion_tokens"]:16d}')
    print(f'{"total tokens":24s}{tok_a:16d}{tok_b:16d}')
    print(f'{"turn growth B vs A":24s}{growth * 100:+31.1f}%   (reported, not gated; D-007)')
    for name, ll in (('A', la), ('B', lb)):
        if ll.get('tokens_partial'):
            print(f'WARNING: {name} token totals are partial '
                  f'({ll["calls_without_usage"]} call(s) without usage)')
    print()
    print(f'consolidate calls in B: {cons}')
    print(f'compose p50 in B: {comp_p50} s')

    ok = True
    # G1: consolidation call wall vs compose p50
    if cons is None or cons.get('count', 0) < 1:
        print('\nG1 FAIL: no consolidate call in RUN_B '
              '(consolidation did not fire — check the flag and that the '
              'document has >= 2 parts at the end of the turn)')
        ok = False
    elif comp_p50 is None:
        print('\nG1 SKIP: no compose calls in RUN_B to compare against')
    else:
        ratio = cons['p50_s'] / comp_p50
        verdict = 'PASS' if ratio <= CONS_VS_COMPOSE_MAX else 'FAIL'
        ok &= ratio <= CONS_VS_COMPOSE_MAX
        print(f'\nG1 {verdict}: consolidate p50 {cons["p50_s"]:.2f} s / '
              f'compose p50 {comp_p50:.2f} s = {ratio:.2f}x '
              f'(limit {CONS_VS_COMPOSE_MAX}x)')
    # G2: marginal tokens of the consolidation pass (D-007)
    marginal, detail = marginal_tokens(lb)
    if marginal is None:
        ok = False
        print(f'G2 UNMEASURABLE: {detail}')
    else:
        share = marginal / tok_b if tok_b else float('inf')
        verdict = 'PASS' if share <= MARGINAL_TOKENS_MAX else 'FAIL'
        ok &= share <= MARGINAL_TOKENS_MAX
        print(f'G2 {verdict}: marginal tokens {marginal} ({detail}) / turn total '
              f'{tok_b} = {share * 100:.1f}% (limit {MARGINAL_TOKENS_MAX * 100:.0f}%)')

    dirty = {name: contamination(run, turn)
             for name, run, turn in (('A', run_a, a), ('B', run_b, b))}
    print()
    if any(dirty.values()):
        for name, reasons in dirty.items():
            for reason in reasons:
                print(f'CONTAMINATED {name}: {reason}')
        print('CONTAMINATED: gates above are void; re-run on an idle box with --jobs 1')
        return EXIT_CONTAMINATED
    print('ALL GATES PASS' if ok else 'GATES FAILED')
    return EXIT_PASS if ok else EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
