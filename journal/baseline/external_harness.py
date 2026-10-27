"""Run an external coding harness (OpenCode) on v1 prompts and write a run file the
hidden-test scorer reads (journal/design/lead-worker.md, the established-harness comparison).

    .venv/bin/python journal/baseline/external_harness.py --generator flash-next --model qwen3.8-flash-next \
        --tier like --label oc-like --prompt c13 --prompt c01 --prompt c01f --runs 2 --jobs 6

Each chain (a prompt and its follow-ups) runs in its own empty working directory, in a
container on the internal network `oc-internal`, whose only peer is the logging proxy
`oc-proxy` (llm_proxy.py) in front of the model server. A follow-up continues the same
OpenCode session in the same directory (`--continue`). After each prompt the files in the
directory are the answer: each becomes a path line and a fenced block, as the bench asks.

Tiers:
  like   OpenCode's own `build` agent and system prompt, file tools only (read, edit/write,
         glob, grep, list, todowrite); bash, web, sub-agents, LSP, skills, questions denied.
  real   the same with bash allowed, in an image with Python and pytest added.

Writes journal/baseline/runs/<stamp>_ext-<label>_<generator>.json and keeps each chain's
work directory, per-turn file snapshots, OpenCode's event stream and the proxy's call log
under runs/ext/<stamp>_<label>/ (ignored).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH = REPO_ROOT / 'journal/baseline/bench/v1'
EXT_ROOT = REPO_ROOT / 'runs/ext'
PROXY_LOGS = EXT_ROOT / 'proxy-logs'
IMAGES = {
    'like': 'ghcr.io/anomalyco/opencode@sha256:6ebc13097f2381301220abe9d1b2a54f50cd1603a910dc1c66e93d8f2c4e8ebb',
    'real': 'opencode-python:1.19.3',
}
OPENCODE_VERSION = '1.19.3'
DENY_ALWAYS = ['webfetch', 'websearch', 'task', 'external_directory', 'lsp', 'skill', 'question']
SKIP_DIRS = {'.opencode', '__pycache__', '.pytest_cache', '.git', 'node_modules'}


def permissions(tier: str) -> dict:
    allow = ['read', 'edit', 'glob', 'grep', 'list', 'todowrite'] + (['bash'] if tier == 'real' else [])
    deny = DENY_ALWAYS + ([] if tier == 'real' else ['bash'])
    return {**{k: 'allow' for k in allow}, **{k: 'deny' for k in deny}}


def config(label: str, model: str, tier: str, steps: int, context: int, output: int, proxy: str = 'oc-proxy') -> dict:
    return {
        '$schema': 'https://opencode.ai/config.json', 'autoupdate': False, 'share': 'disabled',
        'provider': {'local': {
            'npm': '@ai-sdk/openai-compatible', 'name': 'local model via logging proxy',
            'options': {'baseURL': f'http://{proxy}:9000/{label}/v1', 'apiKey': 'sk-local'},
            'models': {model: {'name': model, 'limit': {'context': context, 'output': output}}}}},
        'agent': {'build': {'steps': steps, 'permission': permissions(tier)}},
    }


def answer_text(work: Path) -> tuple[str, list[str]]:
    """The files in the working directory as path lines and fenced blocks."""
    files = sorted(p for p in work.rglob('*') if p.is_file()
                   and not any(part in SKIP_DIRS for part in p.relative_to(work).parts))
    chunks, names = [], []
    for p in files:
        rel = p.relative_to(work).as_posix()
        try:
            body = p.read_text()
        except UnicodeDecodeError:
            continue
        lang = 'python' if rel.endswith('.py') else ''
        chunks.append(f'{rel}\n```{lang}\n{body.rstrip()}\n```')
        names.append(rel)
    return '\n\n'.join(chunks) + ('\n' if chunks else ''), names


def proxy_stats(label: str) -> dict:
    path = PROXY_LOGS / f'{label}.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    usage = [((r.get('response') or {}).get('usage') or {}) for r in rows]
    return {'calls': len(rows), 'prompt_tokens': sum(u.get('prompt_tokens') or 0 for u in usage),
            'completion_tokens': sum(u.get('completion_tokens') or 0 for u in usage),
            'calls_without_usage': sum(1 for u in usage if not u),
            # cached prompt tokens, when the server reports them (vLLM --enable-prompt-tokens-details)
            'cached_prompt_tokens': sum(((u.get('prompt_tokens_details') or {}).get('cached_tokens') or 0) for u in usage),
            'calls_reporting_cache': sum(1 for u in usage if (u.get('prompt_tokens_details') or {}).get('cached_tokens') is not None),
            'tool_calls': sum(len((r.get('response') or {}).get('tool_calls') or []) for r in rows),
            'finish_length': sum(1 for r in rows if (r.get('response') or {}).get('finish_reason') == 'length'),
            'proxy_log': str(path.relative_to(REPO_ROOT)),
            # the last reply's text: a model that answers in prose instead of calling the file tools
            # leaves no files, but its answer is here (scored separately, see --text-fallback)
            'final_reply': next((((r.get('response') or {}).get('content') or '') for r in reversed(rows)
                                 if ((r.get('response') or {}).get('content') or '').strip()), '')}


def run_prompt(chain_dir: Path, label: str, prompt: str, args, first: bool, proxy: str = 'oc-proxy') -> dict:
    cfg = chain_dir / 'cfg'
    cfg.mkdir(exist_ok=True)
    (cfg / 'opencode.json').write_text(json.dumps(
        config(label, args.model, args.tier, args.steps, args.context, args.output, proxy), indent=1))
    name = f'oc_{label}'
    cmd = ['docker', 'run', '--rm', '--name', name, '--network', 'oc-internal',
           '-v', f'{chain_dir / "work"}:/work', '-v', f'{cfg}:/cfg:ro', '-v', f'{chain_dir / "data"}:/data',
           '-e', 'OPENCODE_CONFIG=/cfg/opencode.json', '-e', 'HOME=/data', '-w', '/work', IMAGES[args.tier],
           'run', '--model', f'local/{args.model}', '--agent', 'build', '--format', 'json']
    if not first:
        cmd.append('--continue')
    cmd.append(prompt)
    t0 = time.time()
    with open(chain_dir / f'{label}.events.jsonl', 'w') as out, open(chain_dir / f'{label}.stderr.txt', 'w') as err:
        try:
            proc = subprocess.run(cmd, stdout=out, stderr=err, timeout=args.timeout)
            code, error = proc.returncode, None if proc.returncode == 0 else f'exit {proc.returncode}'
        except subprocess.TimeoutExpired:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            code, error = None, f'timed out after {args.timeout}s'
    return {'exit': code, 'error': error, 'wall_seconds': round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--generator', required=True)
    ap.add_argument('--model', required=True, help='the served model name')
    ap.add_argument('--tier', choices=sorted(IMAGES), required=True)
    ap.add_argument('--label', required=True)
    ap.add_argument('--prompt', action='append', required=True)
    ap.add_argument('--runs', type=int, default=2)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--steps', type=int, default=60)
    ap.add_argument('--timeout', type=int, default=3600)
    ap.add_argument('--context', type=int, default=131072)
    ap.add_argument('--output', type=int, default=32768)
    ap.add_argument('--text-fallback', action='store_true',
                    help='also write a run file scoring the final reply where no files were left')
    ap.add_argument('--proxy', action='append', default=None,
                    help='logging proxy container(s), one per model server; chains are spread over them (default oc-proxy)')
    args = ap.parse_args(argv)

    manifest = {p['id']: p for p in yaml.safe_load((BENCH / 'manifest.yaml').read_text())['prompts']}
    roots = []
    for pid in args.prompt:
        root = pid
        while manifest[root].get('follows'):
            root = manifest[root]['follows']
        if root not in roots:
            roots.append(root)
    children = {}
    for pid, p in manifest.items():
        if p.get('follows'):
            children.setdefault(p['follows'], []).append(pid)

    def chain(root):
        out, stack = [], [root]
        while stack:
            pid = stack.pop(0)
            if pid in args.prompt or pid == root:
                out.append(pid)
            stack += sorted(children.get(pid, []))
        return out

    started = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = EXT_ROOT / f'{started}_{args.label}'
    PROXY_LOGS.mkdir(parents=True, exist_ok=True)
    jobs = [(root, run) for root in roots for run in range(args.runs)]
    results, lock = [], threading.Lock()

    proxies = args.proxy or ['oc-proxy']

    def work(job):
        root, run = job
        proxy = proxies[jobs.index(job) % len(proxies)]
        chain_dir = base / f'{root}_r{run}'
        for sub in ('work', 'data', 'turns'):
            (chain_dir / sub).mkdir(parents=True, exist_ok=True)
        ids = chain(root)
        for i, pid in enumerate(ids):
            label = f'{args.label}_{started}_{pid}_r{run}'
            outcome = run_prompt(chain_dir, label, (BENCH / 'prompts' / f'{pid}.md').read_text(), args, first=(i == 0),
                                 proxy=proxy)
            snap = chain_dir / 'turns' / pid
            shutil.copytree(chain_dir / 'work', snap, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(*SKIP_DIRS))
            text, names = answer_text(chain_dir / 'work')
            row = {'prompt_id': pid, 'arm': f'oc-{args.tier}', 'run': run, 'chain': ids,
                   'follows': manifest[pid].get('follows'), 'domain': manifest[pid]['domain'],
                   'error': outcome['error'], 'wall_seconds': outcome['wall_seconds'], 'exit': outcome['exit'],
                   'files': names, 'output': {'text': text, 'chars': len(text)}, 'llm': proxy_stats(label),
                   'chain_dir': str(chain_dir.relative_to(REPO_ROOT)), 'proxy': proxy}
            with lock:
                results.append(row)
                print(f"{pid} r{run}: {len(names)} files, {row['llm']['calls']} calls, {outcome['wall_seconds']}s"
                      f"{' ERROR ' + outcome['error'] if outcome['error'] else ''}", flush=True)

    with __import__('concurrent.futures').futures.ThreadPoolExecutor(args.jobs) as ex:
        list(ex.map(work, jobs))
    manifest_text = (BENCH / 'manifest.yaml').read_text()
    import hashlib
    out = REPO_ROOT / 'journal/baseline/runs' / f'{started}_ext-{args.label}_{args.generator}.json'
    out.write_text(json.dumps({
        'kind': 'external-harness', 'harness': 'opencode', 'harness_version': OPENCODE_VERSION,
        'image': IMAGES[args.tier], 'tier': args.tier, 'permissions': permissions(args.tier),
        'agent': 'build (OpenCode default system prompt)', 'steps': args.steps, 'timeout_s': args.timeout,
        'bench': 'v1', 'bench_frozen': True, 'manifest_path': str(BENCH.relative_to(REPO_ROOT) / 'manifest.yaml'),
        'manifest_sha256': hashlib.sha256(manifest_text.encode()).hexdigest(),
        'generator': args.generator, 'model': args.model, 'started_at': started, 'runs_per_prompt': args.runs,
        'jobs': args.jobs, 'network': 'oc-internal (no route out) via ' + ', '.join(proxies),
        'results': sorted(results, key=lambda r: (r['prompt_id'], r['run']))}, indent=1))
    print(f'wrote {out}')
    if args.text_fallback:
        # Scored as its own run file: files when the harness left any, else the final reply's text.
        data = json.loads(out.read_text())
        for r in data['results']:
            if not r['files']:
                r['output'] = {'text': r['llm']['final_reply'], 'chars': len(r['llm']['final_reply'])}
                r['answer_from'] = 'final_reply'
            else:
                r['answer_from'] = 'files'
        data['scoring'] = 'files, else the final reply (not the harness contract; for comparison)'
        alt = out.with_name(out.stem.replace(f'_ext-{args.label}_', f'_ext-{args.label}-textfb_') + '.json')
        alt.write_text(json.dumps(data, indent=1))
        print(f'wrote {alt}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
