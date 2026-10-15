"""Replay a stored op log onto a fresh Document to find content loss.

Usage:
  dsh-podman-venv/bin/python journal/baseline/replay.py <run.json> --turn r1:t1

Replays the op log exactly as the pipeline applied it (via Document.apply,
which routes through apply_operations with its integrity checks disabled by
passing no current_result) and reports each op's effect on total content.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reasoning_sub_agents.document import AppliedOp, Document  # noqa: E402
from reasoning_sub_agents.document.models import Part  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('run_json')
    ap.add_argument('--turn', required=True, help='e.g. r1:t1 (run index:turn index)')
    args = ap.parse_args()

    d = json.loads(Path(args.run_json).read_text())
    r_idx, t_idx = (int(x.lstrip('rt')) for x in args.turn.split(':'))
    rec = d['results'][r_idx]
    turn = rec['turns'][t_idx]
    snap = turn['snapshot']

    doc = Document(
        title=snap.get('title'),
        parts=[Part.model_validate(p) for p in snap.get('parts') or []],
        summary=snap.get('summary') or '',
        op_log=[],
        render_mode=snap.get('render_mode') or 'markdown_with_files',
    )
    ops = [AppliedOp.model_validate(e) for e in snap.get('op_log') or []]

    def total_chars() -> int:
        return sum(len(p.body) for p in doc.parts)

    before = total_chars()
    print(f'start: {len(doc.parts)} parts, {before} chars')
    for i, applied in enumerate(ops):
        op = applied.op
        try:
            doc.apply([op.model_dump()], origin_task=applied.origin_task)
        except Exception as exc:  # noqa: BLE001 - the point is to observe
            print(f'  [{i:2d}] {op.__class__.__name__:18s} RAISED {exc!r}')
            continue
        after = total_chars()
        delta = after - before
        before = after
        extra = ''
        payload = getattr(op, 'body', None) or getattr(op, 'content', None)
        if payload:
            extra = f' payload_chars={len(payload)}'
        print(f'  [{i:2d}] {op.__class__.__name__:18s} id={getattr(op, "id", "-"):<6} '
              f'after={after:6d} ({delta:+d}){extra}')
    print(f'final: {len(doc.parts)} parts, {total_chars()} chars')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())