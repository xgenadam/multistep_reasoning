#!/usr/bin/env python3
"""A/B comparison of two harness run files (0-06 consolidation gate).

Usage:
    compare.py RUN_A.json RUN_B.json [--scenario s4_anchors] [--turn 0]

RUN_A: control (default pipeline, no consolidation).
RUN_B: treatment (run with --consolidation).

Gates (P0-4 / ticket 0-06):
  G1  consolidate call p50  <= 1.5x compose p50 (measured in RUN_B)
  G2  per-turn token growth (B vs A)  <= 25%   (prompt + completion)

Per-turn wall_seconds are REPORTED but not gated on: they are only valid in a
clean idle window, and contention on the shared 5-slot server inflates them.
Exit 0 iff every gate passes (and a consolidate call exists in RUN_B).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOKEN_GROWTH_MAX = 0.25
CONS_VS_COMPOSE_MAX = 1.5


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def find_result(d: dict, scenario_id: str) -> dict:
    for r in d['results']:
        if r['scenario'] == scenario_id:
            return r
    raise SystemExit(f'scenario {scenario_id!r} not in run '
                     f'({[r["scenario"] for r in d["results"]]})')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('run_a', help='control run file (no consolidation)')
    ap.add_argument('run_b', help='treatment run file (--consolidation)')
    ap.add_argument('--scenario', default='s4_anchors',
                    help='scenario id to compare (default: s4_anchors)')
    ap.add_argument('--turn', type=int, default=0,
                    help='turn index to compare (default: 0)')
    args = ap.parse_args()

    a = find_result(load(args.run_a), args.scenario)['turns'][args.turn]
    b = find_result(load(args.run_b), args.scenario)['turns'][args.turn]

    la, lb = a['llm'], b['llm']
    tok_a = la['prompt_tokens'] + la['completion_tokens']
    tok_b = lb['prompt_tokens'] + lb['completion_tokens']
    growth = (tok_b - tok_a) / tok_a if tok_a else float('inf')

    cons = lb['by_kind'].get('consolidate')
    comp = lb['by_kind'].get('compose') or {}
    comp_p50 = comp.get('p50_s')

    print(f'compare  A={Path(args.run_a).name}')
    print(f'         B={Path(args.run_b).name}')
    print(f'scenario {args.scenario} turn {args.turn}')
    print()
    print(f'{"":24s}{"A (control)":>16s}{"B (consol.)":>16s}')
    print(f'{"wall_seconds":24s}{a["wall_seconds"]:16.1f}{b["wall_seconds"]:16.1f}   (reported, not gated)')
    print(f'{"prompt tokens":24s}{la["prompt_tokens"]:16d}{lb["prompt_tokens"]:16d}')
    print(f'{"completion tokens":24s}{la["completion_tokens"]:16d}{lb["completion_tokens"]:16d}')
    print(f'{"total tokens":24s}{tok_a:16d}{tok_b:16d}')
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
    # G2: token growth
    verdict = 'PASS' if growth <= TOKEN_GROWTH_MAX else 'FAIL'
    ok &= growth <= TOKEN_GROWTH_MAX
    print(f'G2 {verdict}: token growth {growth * 100:+.1f}% '
          f'({tok_a} -> {tok_b}, limit +{TOKEN_GROWTH_MAX * 100:.0f}%)')

    print()
    print('ALL GATES PASS' if ok else 'GATES FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())