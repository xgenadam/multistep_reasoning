#!/usr/bin/env python3
"""Build Q-E1 judge pairs from arms.py run files (Q-02; pre-registration in Q-02 Notes).

For one generator and one pairing of arms (e.g. b against a2), every prompt
both arms ran gets one of three fates, per the pre-registered outcome rule:
  - code, the hidden-test pass-rates differ: decided by the tests (no judge);
  - code, equal pass-rates: a judge pair, each side carrying `tests: k/n`;
  - report: a judge pair;
  - either side errored, or (code) produced no extractable deliverable:
    a loss for that side (both: a tie), never a judge pair.

Output is a `quality.py judge --pairs` manifest plus `decided.json` (the
outcomes no judge sees), under runs/qe1-pairs/<label>/ by default (ignored;
the build is deterministic from tracked run files and records their
hashes). Candidates are the arms' output text: the harness's rendered
Document, a single-model arm's final answer. The judge never sees which arm
wrote which side: the arm names live only in the manifest's `source`, which
quality.py does not send. A follow-up's task shows both requests, never
either arm's earlier deliverable.

Usage (from the repo root):
  .venv/bin/python journal/baseline/qe1_pairs.py RUN_FILE [RUN_FILE ...] \\
      --pair b:a2 --bench journal/baseline/bench/v1 --label flash-next-b-vs-a2
Code results need each run file's `<stem>.tests.json` (hidden_tests.py
score) beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

DEFAULT_OUT = REPO_ROOT / 'runs' / 'qe1-pairs'


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_results(run_files: list[Path]) -> tuple[dict, dict, str]:
    """(prompt_id, arm, run) -> result; (prompt_id, arm, run) -> test row;
    the generator. Refuses run files from different generators or benches."""
    results, tests, gens, benches = {}, {}, set(), set()
    for path in run_files:
        data = json.loads(Path(path).read_text())
        gens.add(data['generator'])
        benches.add(data['manifest_sha256'])
        for r in data['results']:
            key = (r['prompt_id'], r['arm'], r['run'])
            if key in results:
                raise SystemExit(f'{key} appears in two run files')
            results[key] = r
        sidecar = Path(path).with_suffix('.tests.json')
        if sidecar.exists():
            for row in json.loads(sidecar.read_text())['results']:
                tests[(row['prompt_id'], row['arm'], row['run'])] = row
    if len(gens) != 1:
        raise SystemExit(f'run files from more than one generator: {sorted(gens)}')
    if len(benches) != 1:
        raise SystemExit('run files from more than one bench manifest')
    return results, tests, gens.pop()


def task_text(prompts: dict, pid: str) -> str:
    """The task as the judge sees it: for a follow-up, every request in the
    chain, never an arm's earlier deliverable (it differs by arm)."""
    chain = [pid]
    while prompts[chain[0]].get('follows'):
        chain.insert(0, prompts[chain[0]]['follows'])
    if len(chain) == 1:
        return prompts[pid]['text']
    parts = [f'The user first asked:\n\n{prompts[chain[0]]["text"]}']
    parts += [f'After receiving that deliverable, the user asked:\n\n{prompts[c]["text"]}'
              for c in chain[1:]]
    parts.append('Judge the final, complete deliverable after the last request.')
    return '\n\n'.join(parts)


def _side(result: dict | None, test: dict | None, domain: str) -> dict:
    """What a side brought: ok, its text, its pass-rate (code)."""
    if result is None:
        return {'ok': False, 'why': 'not run'}
    if result.get('error'):
        return {'ok': False, 'why': f'error: {result["error"][:120]}'}
    text = (result.get('output') or {}).get('text') or ''
    if domain == 'report':
        return {'ok': bool(text.strip()), 'why': None if text.strip() else 'empty output',
                'text': text}
    if test is None:
        raise SystemExit(f'{result["prompt_id"]} {result["arm"]}: no hidden-test result; '
                         'run hidden_tests.py score first')
    n = test.get('n_tests') or 0
    passed = (test.get('tests') or {}).get('passed') or 0
    if not test.get('extraction_ok', True) and passed == 0:
        return {'ok': False, 'why': 'no extractable deliverable', 'passed': 0, 'n': n}
    return {'ok': True, 'text': text, 'passed': passed, 'n': n,
            'rate': passed / n if n else 0.0}


def build(run_files: list[Path], x: str, y: str, bench: Path, run: int = 0) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from arms import load_bench
    loaded = load_bench(bench)
    prompts = loaded['prompts']
    results, tests, generator = load_results(run_files)
    pairs, decided = [], []
    for pid, entry in prompts.items():
        rx, ry = results.get((pid, x, run)), results.get((pid, y, run))
        if rx is None and ry is None:
            continue
        domain = entry['domain']
        sx = _side(rx, tests.get((pid, x, run)), domain)
        sy = _side(ry, tests.get((pid, y, run)), domain)
        base = {'prompt_id': pid, 'domain': domain, 'long': bool(entry.get('long')),
                'follow_up': entry.get('follows') is not None}
        if not sx['ok'] or not sy['ok']:
            winner = 'tie' if not sx['ok'] and not sy['ok'] else (x if sx['ok'] else y)
            decided.append({**base, 'winner': winner, 'by': 'failure',
                            x: sx.get('why'), y: sy.get('why')})
            continue
        if domain == 'code' and sx['rate'] != sy['rate']:
            decided.append({**base, 'winner': x if sx['rate'] > sy['rate'] else y, 'by': 'tests',
                            x: f'{sx["passed"]}/{sx["n"]}', y: f'{sy["passed"]}/{sy["n"]}'})
            continue
        pair = {'pair_id': pid, 'kind': 'qe1', 'task': task_text(prompts, pid),
                'a': f'candidates/{pid}_a.md', 'b': f'candidates/{pid}_b.md',
                'expected': None,
                'source': f'{generator} {pid} run {run}: a = arm {x}, b = arm {y}',
                '_a_text': sx['text'], '_b_text': sy['text'], **{'_meta': base}}
        if domain == 'code':
            pair['tests'] = {'a': f'{sx["passed"]}/{sx["n"]} passed',
                             'b': f'{sy["passed"]}/{sy["n"]} passed'}
        pairs.append(pair)
    return {'generator': generator, 'arms': {'a': x, 'b': y}, 'run': run,
            'bench_manifest_sha256': loaded['sha256'],
            'run_files': {str(p): _sha(p) for p in run_files},
            'pairs': pairs, 'decided': decided}


def write(built: dict, out_dir: Path) -> Path:
    (out_dir / 'candidates').mkdir(parents=True, exist_ok=True)
    manifest_pairs = []
    for p in built['pairs']:
        (out_dir / p['a']).write_text(p['_a_text'])
        (out_dir / p['b']).write_text(p['_b_text'])
        manifest_pairs.append({k: v for k, v in p.items() if not k.startswith('_')})
    head = {k: built[k] for k in ('generator', 'arms', 'run', 'bench_manifest_sha256', 'run_files')}
    manifest = {'version': 'qe1', 'note': f'Q-E1 judge pairs, {built["generator"]}: '
                f'a = arm {built["arms"]["a"]}, b = arm {built["arms"]["b"]} '
                '(qe1_pairs.py; the judge sees neither)', **head, 'pairs': manifest_pairs}
    path = out_dir / 'pairs.yaml'
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=100))
    (out_dir / 'decided.json').write_text(json.dumps(
        {**head, 'decided': built['decided'],
         'pair_meta': {p['pair_id']: p['_meta'] for p in built['pairs']}}, indent=2))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Build Q-E1 judge pairs from arms run files')
    ap.add_argument('run_files', nargs='+')
    ap.add_argument('--pair', required=True, help='X:Y, e.g. b:a2 (X is side a)')
    ap.add_argument('--bench', default=str(Path(__file__).parent / 'bench' / 'v1'))
    ap.add_argument('--run', type=int, default=0)
    ap.add_argument('--label', required=True)
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    x, _, y = args.pair.partition(':')
    if not x or not y or x == y:
        ap.error('--pair is X:Y with two different arms')
    built = build([Path(f) for f in args.run_files], x, y, Path(args.bench), args.run)
    path = write(built, Path(args.out) / args.label)
    by = {}
    for d in built['decided']:
        by[(d['domain'], d['by'])] = by.get((d['domain'], d['by']), 0) + 1
    print(f'{len(built["pairs"])} judge pairs, {len(built["decided"])} decided without the judge '
          f'{dict(sorted(by.items()))}')
    print(f'Wrote {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
