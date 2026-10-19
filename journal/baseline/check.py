"""Score a harness run file against the Phase 0 pass criteria.

Usage (from the repo root):
  .venv/bin/python journal/baseline/check.py journal/baseline/runs/<file>.json

Prints a per-scenario pass/fail table against the criteria encoded in
scenarios.py (P0-1..P0-4), plus the call labels each turn was scored with
(P0-6), and whether each turn's timings are clean by compare.py's
contamination rule (reported, not scored). A check that cannot apply (a
Jaccard on a one-part document, label coverage on a run file older than
0-14) reports `n/a` and fails nothing. Exit code 0 only if every scored
scenario passes on every run.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Kinds only the keyword fallback produces; a fresh run has none (P0-6).
FALLBACK_KINDS = ('system_other', 'no_system', 'unknown')

Check = tuple[str, bool | None, str]  # (name, passed or None for n/a, detail)


def load_scenarios() -> dict[str, dict]:
    sys.path.insert(0, str(Path(__file__).parent))
    from scenarios import SCENARIOS  # noqa: E402
    return {s['id']: s for s in SCENARIOS}


def load_expectations() -> dict[str, dict]:
    return {sid: s.get('expect', {}) for sid, s in load_scenarios().items()}


def turn_ops(turn: dict, prior_turn: dict | None) -> Counter:
    """This turn's ops. The op log is cumulative across turns; run files from
    before 0-14 have no `turn_op_counts`, so subtract the prior turn's."""
    doc = turn.get('document') or {}
    if 'turn_op_counts' in doc:
        return Counter(doc['turn_op_counts'])
    ops = Counter(doc.get('op_counts') or {})
    if prior_turn is not None:
        ops -= Counter((prior_turn.get('document') or {}).get('op_counts') or {})
    return ops


def lost_prior_parts(turn: dict, prior_turn: dict | None) -> list[str] | None:
    """Prior-turn part ids this turn dropped (P0-3, D-014), or None if unknown.

    A prior part survives when it is still in the final document, or when a
    merge_parts folded it (possibly via later merges) into a part that is.
    Updates, patches, moves and new parts never lose anything; deleting the
    turn's own scratch parts is not counted. Needs both snapshots: run files
    without them cannot say which ids were dropped.
    """
    prior_snap = (prior_turn or {}).get('snapshot') or {}
    snap = turn.get('snapshot') or {}
    if not prior_snap.get('parts') or 'parts' not in snap:
        return None
    prior_ids = [p.get('id') for p in prior_snap['parts']]
    final_ids = {p.get('id') for p in snap['parts']}
    folded: dict[str, str] = {}  # merged-away id -> the primary it went into
    for entry in (snap.get('op_log') or [])[len(prior_snap.get('op_log') or []):]:
        op = entry.get('op') if isinstance(entry, dict) else None
        if isinstance(op, dict) and op.get('type') == 'merge_parts':
            primary, *rest = op.get('ids') or [None]
            for pid in rest:
                folded[pid] = primary

    def survives(pid: str) -> bool:
        seen = set()
        while pid not in final_ids and pid in folded and pid not in seen:
            seen.add(pid)
            pid = folded[pid]
        return pid in final_ids

    return [pid for pid in prior_ids if not survives(pid)]


def score_scenario(
    sid: str,
    expect: dict,
    turn: dict,
    prior_turn: dict | None = None,
    is_followup: bool = False,
) -> list[Check]:
    """Return [(check, passed, detail)] for one turn of one scenario."""
    out: list[Check] = []
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
    if 'section_parts_max' in expect:
        # P0-1: a code request gives code, with no prose-report parts about it.
        n = kind_count('section')
        out.append((f"prose (section) parts <= {expect['section_parts_max']} (P0-1)",
                    n <= expect['section_parts_max'], f"count={n}, kinds={kinds}"))
    if 'file_parts_max' in expect:
        # P0-2: a report gives sectioned markdown, with no file parts.
        n = kind_count('file')
        out.append((f"file parts <= {expect['file_parts_max']} (P0-2)",
                    n <= expect['file_parts_max'], f"count={n}"))
    if 'section_parts_min' in expect:
        # P0-2 is about the rendered output being sectioned, not about part
        # granularity — a single part may hold multiple ## sections.
        h2 = doc.get('body_h2_headings', 0)
        n = kind_count('section')
        ok = n >= expect['section_parts_min'] or h2 >= expect['section_parts_min']
        out.append((f"sectioned output >= {expect['section_parts_min']}", ok,
                    f"section_parts={n}, body_h2={h2}"))
    if 'non_empty' in expect:
        ok = bool(doc.get('non_empty'))
        out.append(('document non-empty', ok, f"chars={doc.get('content_chars')}"))
    if 'max_dup_jaccard_below' in expect:
        limit = expect['max_dup_jaccard_below']
        name = f"max dup Jaccard < {limit}"
        parts = doc.get('part_count', 0)
        if parts < 2:
            # N17: no pair to compare; 0.0 here would be a vacuous pass.
            out.append((name, None, f"n/a: {parts} part(s)"))
        else:
            j = doc.get('max_dup_jaccard') or 0.0
            out.append((name, j < limit, f"j={j}, top={doc.get('top_dup_pairs', [])[:1]}"))
    if expect.get('followup_keeps_parts') and is_followup:
        # P0-3 (D-014): a follow-up that edits an artifact keeps its parts;
        # it does not delete one and re-add the text under a new id.
        name = "follow-up keeps the prior turn's parts (P0-3)"
        lost = lost_prior_parts(turn, prior_turn)
        ops = dict(turn_ops(turn, prior_turn))
        if lost is None:
            out.append((name, None, f'n/a: no snapshots to compare, turn ops={ops}'))
        else:
            out.append((name, not lost, f'dropped={lost}, turn ops={ops}'))
    if 'min_sub_tasks' in expect:
        st = (turn.get('sub_tasks') or {}).get('final_sub_task_count')
        ok = st is not None and st >= expect['min_sub_tasks']
        out.append((f"sub-tasks >= {expect['min_sub_tasks']}", ok, f"count={st}"))
    if 'file' in expect.get('part_kinds_include', []):
        # 0-09: file part bodies must be RAW file content. The renderer
        # (Document.render, markdown_with_files) adds the ``` fence and
        # infers the language from the title, so a model-authored fence at
        # the start of the body double-fences the output.
        snap = turn.get('snapshot') or {}
        bad = []
        for p in snap.get('parts') or []:
            body = (p.get('body') or '').lstrip()
            if 'file' in str(p.get('kind')).lower() and body.startswith('```'):
                bad.append(p.get('id'))
        out.append(('file part bodies not pre-fenced (0-09)', not bad,
                    f"fenced={bad} (renderer adds the fence; body must be raw)"))
    return out


def label_check(turn: dict) -> Check:
    """P0-6: every call carries a phase label and the labels sum to the total."""
    llm = turn.get('llm') or {}
    by_kind = llm.get('by_kind') or {}
    total = llm.get('calls', 0)
    summed = sum(v.get('count', 0) for v in by_kind.values())
    name = 'phase labels cover every call (P0-6)'
    if 'label_sources' not in llm:
        return (name, None, f'n/a: run file predates 0-14, labels are the keyword '
                            f'fallback ({summed}/{total} calls)')
    sources = llm['label_sources']
    stray = {k: by_kind[k]['count'] for k in FALLBACK_KINDS if k in by_kind}
    ok = summed == total and sources.get('phase', 0) == total and not stray
    return (name, ok, f'{summed}/{total} calls, sources={sources}'
                      + (f', fallback kinds={stray}' if stray else ''))


def kind_line(turn: dict) -> str:
    """The per-kind numbers the S-002 compose/decompose/consolidate verdicts
    rest on, with the label path that produced them."""
    llm = turn.get('llm') or {}
    by_kind = llm.get('by_kind') or {}
    source = 'phase' if 'label_sources' in llm else 'keyword fallback'
    cells = []
    for kind in ('decompose', 'decompose_critique', 'executor_turn', 'oracle',
                 'compose', 'summary', 'consolidate', *FALLBACK_KINDS):
        agg = by_kind.get(kind)
        if agg:
            cells.append(f"{kind} n={agg['count']} p50={agg['p50_s']}s")
    partial = ' (tokens partial)' if llm.get('tokens_partial') else ''
    return f"labels: {source}{partial}; " + ', '.join(cells)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    run = json.loads(Path(sys.argv[1]).read_text())
    scenarios = load_scenarios()
    from compare import contamination  # noqa: E402 - sibling script, one rule
    all_ok = True
    print(f"Run: {run.get('label')} @ {run.get('generated_at')} "
          f"({run.get('runs_per_scenario')} run(s)/scenario, jobs={run.get('jobs')}, "
          f"backend={run.get('backend')})")
    if run.get('errors'):
        print('RUN-LEVEL ERRORS:', *run['errors'], sep='\n  ')
    attribution = run.get('attribution')
    if attribution:
        exact = (attribution['calls'] == attribution['calls_in_turns']
                 and attribution['prompt_tokens'] == attribution['prompt_tokens_in_turns'])
        print(f"attribution: {'exact' if exact else 'MISMATCH'} {attribution}")
        all_ok = all_ok and exact
    for rec in run.get('results', []):
        sid = rec['scenario']
        scenario = scenarios.get(sid, {})
        exp = scenario.get('expect', {})
        turn_defs = scenario.get('turns', [])
        crit = exp.get('criterion', '?')
        print(f"\n{sid}  [{crit}]")
        turns = rec.get('turns', [])
        for pos, turn in enumerate(turns):
            ti = turn.get('index')
            prefix = f"  r{rec['run']} t{ti} wall={turn.get('wall_seconds')}s"
            if 'error' in turn:
                print(f"{prefix}: ERROR {turn['error']}")
                all_ok = False
                continue
            tdef = turn_defs[ti] if isinstance(ti, int) and ti < len(turn_defs) else {}
            is_followup = bool(tdef.get('prior'))
            prior_turn = turns[pos - 1] if is_followup and pos > 0 else None
            checks = score_scenario(sid, exp, turn, prior_turn, is_followup)
            checks.append(label_check(turn))
            ok = all(p is not False for _, p, _ in checks)
            all_ok = all_ok and ok
            print(f"{prefix}: {'PASS' if ok else 'FAIL'}")
            print(f"      {kind_line(turn)}")
            dirty = contamination(run, turn)
            print(f"      timing: {'CONTAMINATED: ' + '; '.join(dirty) if dirty else 'clean'}")
            for name, passed, detail in checks:
                mark = 'n/a' if passed is None else ('ok ' if passed else 'BAD')
                print(f"      [{mark}] {name} — {detail}")
    print('\n' + ('ALL PASS' if all_ok else 'FAILURES PRESENT'))
    return 0 if all_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
