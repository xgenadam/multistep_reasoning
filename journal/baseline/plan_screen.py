"""Round 0 of the meta-prompt tournament: plans only (journal/design/meta-prompts.md).

Each variant's decomposer plans each prompt and nothing runs after it, a few
seconds per plan, so a variant whose plans are malformed or still cut one file
into many fragments can be dropped before any full run.

    LLM_MODEL=gemma-4-e4b .venv/bin/python journal/baseline/plan_screen.py --base-url http://localhost:8100/v1 \
        --variant H=self_critique --variant S=simple --variant FS=meta:frozen:journal/design/meta-prompts/decompose.gemma-4-e4b.txt \
        --variant DS=meta:dynamic --prompt c01 --prompt c03 ... --reps 2

A variant is NAME=<decomposer>[:<meta_prompt>[:<meta_prompt_file>]]. Writes
journal/baseline/runs/<stamp>_plan-screen_<label>.json: every plan, and per
variant the sub-task count, sub-tasks per expected file (from the manifest's
`files`), sub-tasks that name no expected file, single-task fallbacks and errors.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import harness  # noqa: E402
import yaml  # noqa: E402
from harness import REPO_ROOT  # noqa: E402

from reasoning_sub_agents.config.registry import REGISTRY, BuildContext  # noqa: E402
from reasoning_sub_agents.config.schema import OptionsConfig  # noqa: E402
from reasoning_sub_agents.llama_utils import create_llama_client  # noqa: E402

BENCH = REPO_ROOT / 'journal/baseline/bench/v1'


def parse_variant(spec: str) -> tuple[str, str, dict]:
    name, _, rest = spec.partition('=')
    parts = rest.split(':', 2)
    options = {}
    if parts[0] == 'meta':
        options['meta_prompt'] = parts[1] if len(parts) > 1 else 'frozen'
        if len(parts) > 2:
            options['meta_prompt_file'] = str((REPO_ROOT / parts[2]) if not Path(parts[2]).is_absolute() else parts[2])
    return name, parts[0], options


def plan_metrics(sub_tasks: list[dict], files: list[str]) -> dict:
    """How the plan splits the expected files."""
    def text(t):
        return ' '.join(str(t.get(k) or '') for k in ('name', 'objective', 'context', 'description'))
    mentions = {f: sum(1 for t in sub_tasks if re.search(re.escape(f), text(t))) for f in files}
    no_file = sum(1 for t in sub_tasks if not any(re.search(re.escape(f), text(t)) for f in files))
    return {'sub_tasks': len(sub_tasks), 'files': len(files),
            'sub_tasks_per_file': round(len(sub_tasks) / max(1, len(files)), 2),
            'mentions_per_file': mentions, 'naming_no_file': no_file,
            'fallback': any('Fallback single task' in (t.get('description') or '') for t in sub_tasks)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base-url', required=True)
    ap.add_argument('--variant', action='append', required=True)
    ap.add_argument('--prompt', action='append', required=True)
    ap.add_argument('--reps', type=int, default=2)
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--label', default='round0')
    ap.add_argument('--max-tokens', type=int, default=32768)
    ap.add_argument('--prompt-token-budget', type=int, default=65536)
    args = ap.parse_args(argv)

    manifest = {p['id']: p for p in yaml.safe_load((BENCH / 'manifest.yaml').read_text())['prompts']}
    harness.MAX_TOKENS = args.max_tokens
    client = create_llama_client(base_url=args.base_url)
    measured = harness.install_instrumentation(client)
    variants = [parse_variant(v) for v in args.variant]
    jobs = [(v, pid, rep) for v in variants for pid in args.prompt for rep in range(args.reps)]
    rows: list[dict] = []
    lock = threading.Lock()

    def one(job):
        (name, decomposer, opts), pid, rep = job
        turn = f'{name}:{pid}#r{rep}'
        token = harness._current_turn.set(turn)
        try:
            options = OptionsConfig(prompt_token_budget=args.prompt_token_budget, **opts)
            d = REGISTRY['decomposer'][decomposer].factory(BuildContext(llm_client=client, options=options))
            prompt = (BENCH / 'prompts' / f'{pid}.md').read_text()
            try:
                tasks = d.generate_sub_tasks(prompt)
                sub_tasks = [t.decomposed_sub_task.model_dump(mode='json') for t in tasks]
                error = None
            except Exception as exc:  # noqa: BLE001 - a failed plan is a row
                sub_tasks, error = [], repr(exc)
            calls = measured.records_for_turn(turn)
            row = {'variant': name, 'prompt_id': pid, 'rep': rep, 'error': error, 'sub_tasks_plan': sub_tasks,
                   'metrics': plan_metrics(sub_tasks, manifest[pid].get('files') or []),
                   'calls': len(calls), 'completion_tokens': sum(c.completion_tokens or 0 for c in calls),
                   'meta_prompt': d.history.get('meta_prompt'),
                   'regenerated': d.history.get('regeneration_needed')}
        finally:
            harness._current_turn.reset(token)
        with lock:
            rows.append(row)
            print(f"{name} {pid} r{rep}: {row['metrics']['sub_tasks']} sub-tasks for {row['metrics']['files']} files"
                  f"{' ERROR ' + error[:80] if error else ''}", flush=True)

    with ThreadPoolExecutor(args.jobs) as ex:
        list(ex.map(one, jobs))
    summary = {}
    for name, _, _ in variants:
        vr = [r for r in rows if r['variant'] == name and not r['error']]
        summary[name] = {
            'plans': len(vr), 'errors': sum(1 for r in rows if r['variant'] == name and r['error']),
            'median_sub_tasks': statistics.median(r['metrics']['sub_tasks'] for r in vr) if vr else None,
            'median_sub_tasks_per_file': statistics.median(r['metrics']['sub_tasks_per_file'] for r in vr) if vr else None,
            'plans_one_task_per_file': sum(1 for r in vr if r['metrics']['sub_tasks'] <= r['metrics']['files']),
            'fallbacks': sum(1 for r in vr if r['metrics']['fallback']),
            'median_completion_tokens': statistics.median(r['completion_tokens'] for r in vr) if vr else None}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = REPO_ROOT / 'journal/baseline/runs' / f'{stamp}_plan-screen_{args.label}.json'
    out.write_text(json.dumps({
        'kind': 'plan-screen', 'base_url': args.base_url, 'model': harness.os.environ.get('LLM_MODEL', 'llama'),
        **harness.git_commit(), 'variants': args.variant, 'reps': args.reps, 'max_tokens': args.max_tokens,
        'summary': summary, 'rows': sorted(rows, key=lambda r: (r['variant'], r['prompt_id'], r['rep']))}, indent=1))
    print(json.dumps(summary, indent=1))
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
