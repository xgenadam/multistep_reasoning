"""Trace the part-id lifecycle in a stored run's op log (P0-3 churn forensics).

Usage:
  dsh-podman-venv/bin/python journal/baseline/replay.py <run.json> --turn r1:t1
  dsh-podman-venv/bin/python journal/baseline/replay.py <run.json>          # all turns

The point is to see HOW the composer kept (or squandered) the document: does
consolidation fold parts with merge_parts / a targeted patch, or does it
delete the whole document and re-add it as one part (the "churn" signature)?

Notes on what this can and cannot do:
- The stored snapshot's op_log is CUMULATIVE across the scenario's turns. For
  a continuation turn (one with a `prior`), this tool reports only that turn's
  OWN ops — the tail of the log after the prior turn's log length.
- Ops that carried their body via body_source="current_result" do NOT have a
  stored body (we only snapshot the document, not the sub-task results), so we
  report them as "(body not stored)" rather than a char delta. Patch ops that
  carry a literal body DO get a char delta.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _own_ops(snap: dict, prior_snap: dict | None) -> list[dict]:
    """Return this turn's own ops (log minus the prior turn's prefix)."""
    log = snap.get('op_log') or []
    if prior_snap is None:
        return log
    prefix = len(prior_snap.get('op_log') or [])
    return log[prefix:]


def _trace(label: str, ops: list[dict], seed_live: set[str] | None = None) -> dict:
    live: set[str] = set(seed_live or ())
    if seed_live:
        print(f'  (carried over from prior turn: {sorted(seed_live)})')
    counts: dict[str, int] = {}
    churn = 0  # a delete that is part of a delete-then-re-add whole-doc rebuild
    print(f'=== {label} : {len(ops)} ops ===')
    for i, entry in enumerate(ops):
        op = entry['op']
        ty = op['type']
        counts[ty] = counts.get(ty, 0) + 1
        if ty == 'add_part':
            pid = op['id']
            live.add(pid)
            src = op.get('body_source') or ('body' if op.get('body') else '?')
            print(f'  [{i:2d}] + add    {pid:24} kind={op.get("kind","?"):8} src={src}')
        elif ty == 'delete_part':
            pid = op['id']
            live.discard(pid)
            print(f'  [{i:2d}] - delete {pid:24}')
        elif ty == 'merge_parts':
            ids = op['ids']
            primary = ids[0]
            absorbed = ids[1:]
            for x in absorbed:
                live.discard(x)
            live.add(primary)
            print(f'  [{i:2d}] ~ merge  -> {primary} absorbs {absorbed}')
        elif ty == 'update_part':
            body = op.get('body')
            delta = f' body_chars={len(body)}' if body else ' src=current_result (not stored)'
            print(f'  [{i:2d}] ~ update {op["id"]:24}{delta}')
        elif ty == 'append_to_part':
            body = op.get('body')
            delta = f' +{len(body)} chars' if body else ' src=current_result (not stored)'
            print(f'  [{i:2d}] ~ append {op["id"]:24}{delta}')
        elif ty in ('replace_in_part', 'insert_in_part'):
            body = op.get('body')
            delta = f' {len(body) if body else 0} chars' if body else ' (not stored)'
            print(f'  [{i:2d}] ~ {ty:14} {op["id"]:24}{delta}')
        elif ty == 'move_part':
            print(f'  [{i:2d}] ~ move     {op["id"]:24} -> after {op.get("after","?")}')
        else:
            print(f'  [{i:2d}] ? {ty} {op}')
    # churn signature: a delete that drops the live set to fewer parts,
    # immediately followed by an add (classic whole-doc rebuild).
    for i in range(len(ops) - 1):
        a, b = ops[i]['op'], ops[i + 1]['op']
        if a['type'] == 'delete_part' and b['type'] == 'add_part':
            churn += 1
    print(f'  live parts at end: {sorted(live)}  ({len(live)})')
    print(f'  op counts: {counts}')
    print(f'  delete->add adjacency (churn indicator): {churn}')
    return {'ops': len(ops), 'final_parts': len(live), 'counts': counts, 'churn': churn}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('run_json')
    ap.add_argument('--turn', help='e.g. r1:t1 (run index:turn index); default: all turns')
    args = ap.parse_args()

    d = json.loads(Path(args.run_json).read_text())

    targets: list[tuple[int, int]] = []
    if args.turn:
        r_idx, t_idx = (int(x.lstrip('rt')) for x in args.turn.split(':'))
        targets = [(r_idx, t_idx)]
    else:
        targets = [(ri, ti) for ri, r in enumerate(d['results'])
                   for ti in range(len(r['turns']))]

    # Precompute prior snapshots for each (run, turn) so we can slice own ops.
    prior_snap: dict[tuple[int, int], dict | None] = {}
    for ri, r in enumerate(d['results']):
        for ti in range(len(r['turns'])):
            # prior = previous turn of the SAME run
            if ti > 0:
                prior_snap[(ri, ti)] = r['turns'][ti - 1]['snapshot']
            else:
                prior_snap[(ri, ti)] = None

    for (ri, ti) in targets:
        rec = d['results'][ri]
        turn = rec['turns'][ti]
        snap = turn['snapshot']
        psnap = prior_snap[(ri, ti)]
        ops = _own_ops(snap, psnap)
        chars = sum(len(p['body']) for p in snap.get('parts') or [])
        seed = {p['id'] for p in psnap.get('parts') or []} if psnap else None
        print(f'\n# run {ri} turn {ti}: ends {len(snap.get("parts") or [])} part(s), '
              f'{chars} chars total')
        _trace(f'r{ri} t{ti}', ops, seed_live=seed)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())