#!/usr/bin/env python3
"""Score arms.py run files on bench v1-std's IFEval entries (Q-02 bias guard 4.1).

Uses Google's official IFEval checker, vendored at
bench/v1-std/ifeval_checker/ (SOURCE.md: the pinned commit and the one local
change). It runs only in its own interpreter, .venv-ifeval (`make
venv-ifeval`), never the project's .venv:

  .venv-ifeval/bin/python journal/baseline/ifeval_score.py RUN_FILE [RUN_FILE ...]

For every result whose prompt has bench/v1-std/ifeval/<id>.json, the
output text is checked against the row's instructions, strict and loose
(IFEval's two modes). An errored or empty output follows no instruction.
Writes <run file stem>.ifeval.json beside each run file, with per-result
verdicts and, per arm, IFEval's four headline numbers: prompt-level and
instruction-level accuracy, strict and loose.

langdetect is seeded (DetectorFactory.seed = 0), so the two language checks
give the same answer on every run; upstream leaves it unseeded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH = Path(__file__).parent / 'bench' / 'v1-std'
CHECKER = DEFAULT_BENCH / 'ifeval_checker'
os.environ.setdefault('NLTK_DATA', str(REPO_ROOT / '.venv-ifeval' / 'nltk_data'))
sys.path.insert(0, str(CHECKER))

try:
    import langdetect
    from instruction_following_eval import evaluation_lib
except ImportError as exc:  # the project's .venv has none of the checker's packages
    raise SystemExit(f'{exc}: run this with .venv-ifeval/bin/python (make venv-ifeval)')

langdetect.DetectorFactory.seed = 0


def load_rows(bench: Path) -> dict[str, evaluation_lib.InputExample]:
    rows = {}
    for meta in sorted((bench / 'ifeval').glob('*.json')):
        pid = meta.stem
        data = json.loads(meta.read_text())
        rows[pid] = evaluation_lib.InputExample(
            key=data['key'], instruction_id_list=data['instruction_id_list'],
            prompt=(bench / 'prompts' / f'{pid}.md').read_text(), kwargs=data['kwargs'])
    return rows


def score_result(inp, text: str) -> dict:
    out = {}
    for mode, fn in (('strict', evaluation_lib.test_instruction_following_strict),
                     ('loose', evaluation_lib.test_instruction_following_loose)):
        verdict = fn(inp, {inp.prompt: text})
        out[mode] = {'all': verdict.follow_all_instructions,
                     'per_instruction': dict(zip(inp.instruction_id_list,
                                                 verdict.follow_instruction_list))}
    return out


def summarise(scored: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for arm in sorted({s['arm'] for s in scored}):
        rows = [s for s in scored if s['arm'] == arm]
        entry = {'prompts': len(rows)}
        for mode in ('strict', 'loose'):
            flags = [f for s in rows for f in s[mode]['per_instruction'].values()]
            entry[f'prompt_level_{mode}'] = round(sum(s[mode]['all'] for s in rows) / len(rows), 4)
            entry[f'instruction_level_{mode}'] = round(sum(flags) / len(flags), 4) if flags else None
        out[arm] = entry
    return out


def score_file(path: Path, rows: dict) -> dict:
    data = json.loads(Path(path).read_text())
    scored = []
    for r in data['results']:
        inp = rows.get(r['prompt_id'])
        if inp is None:
            continue
        text = '' if r.get('error') else ((r.get('output') or {}).get('text') or '')
        scored.append({'prompt_id': r['prompt_id'], 'arm': r['arm'], 'run': r['run'],
                       'key': inp.key, 'error': r.get('error'), **score_result(inp, text)})
    return {'run_file': str(path), 'generator': data.get('generator'),
            'checker': 'google-research instruction_following_eval (bench/v1-std/ifeval_checker/SOURCE.md)',
            'results': scored, 'summary': summarise(scored) if scored else {}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='IFEval scoring for arms run files on bench v1-std')
    ap.add_argument('run_files', nargs='+')
    ap.add_argument('--bench', default=str(DEFAULT_BENCH))
    args = ap.parse_args(argv)
    rows = load_rows(Path(args.bench))
    for f in args.run_files:
        report = score_file(Path(f), rows)
        out = Path(f).with_suffix('.ifeval.json')
        out.write_text(json.dumps(report, indent=2))
        print(f'{f}: {len(report["results"])} IFEval results; {json.dumps(report["summary"])}')
        print(f'Wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
