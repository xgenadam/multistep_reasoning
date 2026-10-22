"""Cut the Q-04 standard judge slice into quality.py's manifest format.

Sources (downloaded by the agent, Q-04 Notes 2026-10-22, raw copies under
--raw): LLMBar's four adversarial subsets (princeton-nlp/LLMBar, GitHub
Dataset/LLMBar/Adversarial/*/dataset.json) and JudgeBench's livecodebench
(coding) and livebench-reasoning (reasoning) pairs for both response models
(ScalerLab/JudgeBench data/*.jsonl). Every pair carries a human label, so
`expected` is filled and quality.py's expected-side rates are the label
agreement; kind `std` keeps them out of the Q-1 scoring.

The slice is a seeded sample so the cut is reproducible from the raw files:
    .venv/bin/python journal/baseline/bench/std/build.py --raw ~/models/bench-std-raw
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
LLMBAR_SUBSETS = {'Neighbor': 'LN', 'GPTInst': 'LI', 'GPTOut': 'LO', 'Manual': 'LM'}
JUDGEBENCH_SOURCES = {'livecodebench': 'JC', 'livebench-reasoning': 'JR'}
JUDGEBENCH_FILES = {'gpt': 'gpt-00000-of-00001.jsonl', 'claude': 'claude-00000-of-00001.jsonl'}


def llmbar_pairs(raw: Path, per_subset: int, rng: random.Random) -> list[dict]:
    pairs = []
    for subset, prefix in LLMBAR_SUBSETS.items():
        items = json.loads((raw / 'LLMBar' / 'Adversarial' / f'{subset}.json').read_text())
        idx = sorted(rng.sample(range(len(items)), min(per_subset, len(items))))
        for n, i in enumerate(idx, 1):
            it = items[i]
            pairs.append({'pair_id': f'{prefix}{n:03d}', 'kind': 'std', 'task': it['input'],
                          'a_text': it['output_1'], 'b_text': it['output_2'],
                          'expected': 'a' if str(it['label']) == '1' else 'b',
                          'source': f'LLMBar/Adversarial/{subset}#{i} (label {it["label"]})'})
    return pairs


def judgebench_pairs(raw: Path, per_source_model: int, rng: random.Random) -> list[dict]:
    pairs = []
    counters = {prefix: 0 for prefix in JUDGEBENCH_SOURCES.values()}
    for model, fname in JUDGEBENCH_FILES.items():
        rows = [json.loads(line) for line in (raw / 'JudgeBench' / 'data' / fname).read_text().splitlines() if line.strip()]
        for source, prefix in JUDGEBENCH_SOURCES.items():
            cand = [r for r in rows if r['source'] == source]
            idx = sorted(rng.sample(range(len(cand)), min(per_source_model, len(cand))))
            for i in idx:
                r = cand[i]
                counters[prefix] += 1
                pairs.append({'pair_id': f'{prefix}{counters[prefix]:03d}', 'kind': 'std', 'task': r['question'],
                              'a_text': r['response_A'], 'b_text': r['response_B'],
                              'expected': 'a' if r['label'] == 'A>B' else 'b',
                              'source': f'JudgeBench/{model}/{source}/{r["pair_id"]} ({r["label"]})'})
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--raw', type=Path, default=Path.home() / 'models' / 'bench-std-raw')
    ap.add_argument('--out', type=Path, default=HERE)
    ap.add_argument('--llmbar-per-subset', type=int, default=25)
    ap.add_argument('--judgebench-per-source-model', type=int, default=15)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    pairs = llmbar_pairs(args.raw, args.llmbar_per_subset, rng) + judgebench_pairs(args.raw, args.judgebench_per_source_model, rng)
    cand = args.out / 'candidates'
    cand.mkdir(parents=True, exist_ok=True)
    for stale in cand.glob('*.md'):
        stale.unlink()
    manifest = []
    for p in pairs:
        for side in ('a', 'b'):
            (cand / f'{p["pair_id"]}_{side}.md').write_text(p[f'{side}_text'])
        manifest.append({'pair_id': p['pair_id'], 'kind': p['kind'], 'task': p['task'],
                         'a': f'candidates/{p["pair_id"]}_a.md', 'b': f'candidates/{p["pair_id"]}_b.md',
                         'expected': p['expected'], 'source': p['source']})
    note = (f'Q-04 standard judge slice, written by build.py (seed {args.seed}): LLMBar adversarial '
            f'{args.llmbar_per_subset} per subset x {len(LLMBAR_SUBSETS)}, JudgeBench livecodebench and '
            f'livebench-reasoning {args.judgebench_per_source_model} per response model each. Human labels in '
            f'expected; kind std stays outside Q-1 scoring and is reported as the expected-side rate.')
    (args.out / 'pairs.yaml').write_text(yaml.safe_dump({'version': 'std_v1', 'note': note, 'pairs': manifest},
                                                         sort_keys=False, allow_unicode=True, width=100))
    by_prefix: dict[str, int] = {}
    for p in pairs:
        by_prefix[p['pair_id'][:2]] = by_prefix.get(p['pair_id'][:2], 0) + 1
    print(f'{len(pairs)} pairs -> {args.out / "pairs.yaml"}; by prefix {by_prefix}')


if __name__ == '__main__':
    main()
