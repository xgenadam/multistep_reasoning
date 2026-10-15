"""Score a harness run file against the Phase 0 pass criteria.

Usage (from the repo root):
  dsh-podman-venv/bin/python journal/baseline/check.py journal/baseline/runs/<file>.json

Prints a per-scenario pass/fail table against the criteria encoded in
scenarios.py (P0-1..P0-4) plus a machine summary. Exit code 0 only if every
scored scenario passes on every run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_expectations() -> dict[str, dict]:
    sys.path.insert(0, str(Path(__file__).parent))
    from scenarios import SCENARIOS  # noqa: E402
    return {s['id']: s.get('expect', {}) for s in SCENARIOS}


def score_scenario(sid: str, expect: dict, turn: dict) -> list[tuple[str, bool, str]]:
    """Return [(check, passed, detail)] for one turn of one scenario."""
    out: list[tuple[str, bool, str]] = []
    doc = turn.get('document') or {}
    kinds = doc.get('part_kinds') or {}

    def kind_count(name: str) -> int:
        for k, v in kinds.items():
            if name in k:
                return v
        return 0

    if 'part_kinds_include' in expect:
        for want in expect['part_kinds_include']:
            n = kind_count(want)
            out.append((f"parts include '{want}'", n > 0, f"count={n}, kinds={kinds}"))
    if 'file_parts_min' in expect:
        n = kind_count('file')
        out.append((f"file parts >= {expect['file_parts_min']}", n >= expect['file_parts_min'], f"count={n}"))
    if 'section_parts_min' in expect:
        n = kind_count('section')
        out.append((f"section parts >= {expect['section_parts_min']}", n >= expect['section_parts_min'], f"count={n}"))
    if 'non_empty' in expect:
        ok = bool(doc.get('non_empty'))
        out.append(('document non-empty', ok, f"chars={doc.get('content_chars')}"))
    if 'max_dup_jaccard_below' in expect:
        j = doc.get('max_dup_jaccard', 0.0)
        limit = expect['max_dup_jaccard_below']
        out.append((f"max dup Jaccard < {limit}", j < limit, f"j={j}, top={doc.get('top_dup_pairs', [])[:1]}"))
    if 'min_sub_tasks' in expect:
        st = (turn.get('sub_tasks') or {}).get('final_sub_task_count')
        ok = st is not None and st >= expect['min_sub_tasks']
        out.append((f"sub-tasks >= {expect['min_sub_tasks']}", ok, f"count={st}"))
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    run = json.loads(Path(sys.argv[1]).read_text())
    expects = load_expectations()
    all_ok = True
    print(f"Run: {run.get('label')} @ {run.get('generated_at')} "
          f"({run.get('runs_per_scenario')} run(s)/scenario, jobs={run.get('jobs')})")
    if run.get('errors'):
        print('RUN-LEVEL ERRORS:', *run['errors'], sep='\n  ')
    for rec in run.get('results', []):
        sid = rec['scenario']
        exp = expects.get(sid, {})
        crit = exp.get('criterion', '?')
        print(f"\n{sid}  [{crit}]")
        for turn in rec.get('turns', []):
            prefix = f"  r{rec['run']} t{turn.get('index')} wall={turn.get('wall_seconds')}s"
            if 'error' in turn:
                print(f"{prefix}: ERROR {turn['error']}")
                all_ok = False
                continue
            checks = score_scenario(sid, exp, turn)
            if not checks:
                print(f"{prefix}: no checks (anchor scenario)")
                continue
            ok = all(p for _, p, _ in checks)
            all_ok = all_ok and ok
            print(f"{prefix}: {'PASS' if ok else 'FAIL'}")
            for name, passed, detail in checks:
                mark = 'ok ' if passed else 'BAD'
                print(f"      [{mark}] {name} — {detail}")
    print('\n' + ('ALL PASS' if all_ok else 'FAILURES PRESENT'))
    return 0 if all_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())