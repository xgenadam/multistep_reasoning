#!/usr/bin/env python3
"""Score every intermediate output of an arms.py run file (Q-02; the user, 2026-10-24).

For each result, the candidates are every output the arm produced on the way
to its final one:
  - a2 (self-refine): each round's draft from the run file's `rounds`
    (round 0 is the first draft; discarded rounds, cut by the ceiling, are
    scored too and marked);
  - b, c (the harness): the Document after each sub-task (and after
    consolidation), from intermediates/<run stem>/<turn id>/*_document_*.json
    (arms.py writes them; git-ignored).

Each candidate is scored the way its domain's final output is: hidden tests
(code; hidden_tests.run_tests) or the checklist (report; checklists.score_text).
Per result, the report gives every step's score beside the completion tokens
spent to reach it, the final output's score, and the best one.

"Best" uses the hidden tests or the checklist, which the arm never sees, so
it is an oracle: an upper bound on what a perfect stop-or-pick rule could
have returned, never an arm's output. "Final" (the most recent complete
output) is what the arm delivers and what the pre-registered comparison
scores. The gap between them is the headroom for a stopping rule (Q-07) and
data for harness tuning.

Usage (from the repo root):
  .venv/bin/python journal/baseline/intermediates.py score RUN_FILE [--bench DIR] [--jobs N]
Writes <run file stem>.intermediates.json beside the run file.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

import checklists  # noqa: E402
import hidden_tests  # noqa: E402

from reasoning_sub_agents.document import Document  # noqa: E402

DEFAULT_BENCH = Path(__file__).parent / 'bench' / 'v1'


def candidates(r: dict, run_dir: Path) -> list[dict]:
    """[{step, tokens, output, discarded}] in order; output is a run-file
    style {'text', 'snapshot'} dict so both scorers read it as they read a
    final output."""
    if r['arm'] == 'a2':
        out, spent = [], 0
        for entry in r.get('rounds') or []:
            spent += entry.get('completion_tokens') or 0
            out.append({'step': entry['round'], 'tokens': spent,
                        'output': {'text': entry.get('draft') or '', 'snapshot': None},
                        'discarded': bool(entry.get('discarded'))})
        return out
    inter = r.get('intermediates') or {}
    d = Path(inter['dir']) if inter.get('dir') else None
    if d is not None and not d.is_absolute():
        d = REPO_ROOT / d
    if d is None or not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob('*_document_*.json')):
        payload = json.loads(f.read_text())
        snap = payload['snapshot']
        out.append({'step': payload['step'], 'tokens': payload.get('completion_tokens'),
                    'output': {'text': Document.from_dict(snap).render(), 'snapshot': snap},
                    'discarded': False})
    return out


def _score_code(output: dict, entry: dict, bench: Path, n_ref: int | None) -> dict:
    files, notes = hidden_tests.extract_output(output, entry.get('files'))
    res = hidden_tests.run_tests(files, bench / 'tests' / entry['id'])
    n = n_ref or res['total']
    return {'score': round(res['passed'] / n, 4) if n else 0.0, 'passed': res['passed'], 'n': n,
            'extraction_ok': bool(files) and not notes['missing']}


def _score_report(output: dict, entry: dict, bench: Path) -> dict:
    text = output.get('text') or ''
    if not text and output.get('snapshot'):
        text = Document.from_dict(output['snapshot']).render()
    s = checklists.score_text(text, checklists.load_checklist(bench, entry['id']))
    return {'score': s['score'], 'passed': s['passed'], 'n': s['total']}


def score_run(run_file: Path, bench: Path, jobs: int = 3) -> dict:
    run_file, bench = Path(run_file), Path(bench)
    data = json.loads(run_file.read_text())
    manifest = {e['id']: e for e in yaml.safe_load((bench / 'manifest.yaml').read_text())['prompts']}
    todo = [r for r in data['results'] if r['prompt_id'] in manifest and not r.get('error')]

    refs: dict[str, int | None] = {}
    for pid in sorted({r['prompt_id'] for r in todo if manifest[r['prompt_id']]['domain'] == 'code'}):
        ref = bench / 'reference' / pid
        refs[pid] = hidden_tests.run_tests(
            hidden_tests.read_tree(ref, skip=(hidden_tests.BROKEN_DIR,)),
            bench / 'tests' / pid)['total'] if ref.is_dir() else None

    def score(output: dict, entry: dict) -> dict:
        if entry['domain'] == 'code':
            return _score_code(output, entry, bench, refs.get(entry['id']))
        return _score_report(output, entry, bench)

    def one(r: dict) -> dict:
        entry = manifest[r['prompt_id']]
        steps = [{**{k: c[k] for k in ('step', 'tokens', 'discarded')}, **score(c['output'], entry)}
                 for c in candidates(r, run_file.parent)]
        final = score(r.get('output') or {}, entry)
        kept = [s for s in steps if not s['discarded']]
        best = max(kept, key=lambda s: s['score'] or 0.0) if kept else None
        return {'prompt_id': r['prompt_id'], 'arm': r['arm'], 'run': r['run'],
                'domain': entry['domain'], 'stratum': r.get('stratum'),
                'final': final, 'steps': steps,
                'best': {'step': best['step'], 'score': best['score'], 'tokens': best['tokens']}
                if best else None,
                'final_is_best': best is None or (final['score'] or 0.0) >= (best['score'] or 0.0)}

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        rows = list(pool.map(one, todo))
    return {'run_file': str(run_file), 'bench': str(bench),
            'scored_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'note': 'best is an oracle (scored with the hidden tests or checklist); final is '
                    'what the arm delivers',
            'results': rows, 'summary': summarise(rows)}


def summarise(rows: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for key in sorted({(r['arm'], r['domain']) for r in rows}):
        group = [r for r in rows if (r['arm'], r['domain']) == key and r['best'] is not None]
        if not group:
            continue
        out['/'.join(key)] = {
            'prompts': len(group),
            'final_mean': round(statistics.mean(r['final']['score'] or 0.0 for r in group), 4),
            'best_mean': round(statistics.mean(r['best']['score'] or 0.0 for r in group), 4),
            'final_is_best_share': round(sum(r['final_is_best'] for r in group) / len(group), 4),
            'steps_median': statistics.median(len(r['steps']) for r in group),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Score every intermediate output of a run file')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sc = sub.add_parser('score')
    sc.add_argument('run_file')
    sc.add_argument('--bench', default=str(DEFAULT_BENCH))
    sc.add_argument('--jobs', type=int, default=3)
    args = ap.parse_args(argv)
    report = score_run(Path(args.run_file), Path(args.bench), args.jobs)
    out = Path(args.run_file).with_suffix('.intermediates.json')
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report['summary'], indent=2))
    print(f'Wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
