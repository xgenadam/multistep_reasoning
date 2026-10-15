"""Phase 0+ baseline & performance harness.

Drives the real TaskOrchestrator end-to-end against the live model server and
records, per turn, BOTH time metrics (wall-clock, per-call latency, tokens,
calls by kind/phase) AND output metrics (part shape, duplication, op usage,
sub-task health) in one JSON file. That pairing is the point: if a
background run catches contention from other traffic (e.g. the agent's own
calls on the same server), the time numbers inflate while the output
numbers stay clean — which tells you to re-run, not to conclude.

Usage (from the repo root):
  dsh-podman-venv/bin/python journal/baseline/harness.py --smoke
  dsh-podman-venv/bin/python journal/baseline/harness.py                 # all scenarios, 2 runs each
  dsh-podman-venv/bin/python journal/baseline/harness.py --scenario s2_report --runs 3
  dsh-podman-venv/bin/python journal/baseline/harness.py --jobs 2        # concurrent scenarios (server has 5 slots)

Output: journal/baseline/runs/<timestamp>_<label>_<scenarios>.json plus a
console summary.

NOTE: the current pipeline records no token counts on streamed calls (the
llama.cpp stream exposes no usage). Completion tokens for prose turns will
be 0 until Phase A adds usage capture; prompt tokens on non-streamed JSON
calls are recorded when the server reports them.
"""

from __future__ import annotations

import argparse
import contextvars
import json
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from reasoning_sub_agents.document import Document  # noqa: E402
from reasoning_sub_agents.llama_utils import create_llama_client  # noqa: E402
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator  # noqa: E402

DEFAULT_HOST = 'host.containers.internal'
DEFAULT_PORT = 5000

# The server's default per-generation cap is ~2804 tokens (measured via
# /v1 probe: finish_reason=length at 2804 completion tokens). That truncates
# the long JSON completions (decompose/compose) and would truncate long prose
# turns. The server honors a per-request max_tokens, so the instrumentation
# raises the cap for every call it times. This is part of the baseline: a
# pipeline running under the 2.8K cap is not what it will run under after
# the fix lands (or via the oobabooga UI, which sets its own limit).
MAX_TOKENS = 8192

_current_phase: contextvars.ContextVar[str] = contextvars.ContextVar(
    'baseline_phase', default='unknown'
)


def classify_call(messages: list[dict]) -> str:
    """Best-effort label for an LLM call from its system message(s)."""
    for msg in messages:
        if msg.get('role') != 'system':
            continue
        content = msg.get('content') or ''
        low = content.lower()
        if 'sub_task_detail' in low or 'broken into sub-tasks' in low:
            return 'decompose'
        if 'self-critique' in low or 'critic' in low:
            return 'decompose_critique'
        if 'add_part' in low or 'document operations' in low:
            return 'compose'
        if 'rolling summary' in low:
            return 'summary'
        if 'oracle' in low:
            return 'oracle'
        if 'tool call' in low or 'assistant response' in low:
            return 'executor_turn'
        return 'system_other'
    return 'no_system'


@dataclass
class CallRecord:
    index: int
    kind: str
    stream: bool
    phase: str
    seconds: float
    first_token_s: float | None
    chunks: int
    prompt_tokens: int | None
    completion_tokens: int | None
    finish_reason: str | None = None


class MeasuredCompletions:
    """Wraps the OpenAI client's chat.completions to time and count calls.

    Records are append-only in a shared list with monotonic indices; callers
    slice the range they care about. Safe under concurrent turns.
    """

    def __init__(self, real) -> None:
        self._real = real
        self._records: list[CallRecord] = []
        self._next_index = 0
        self._lock = threading.Lock()

    def start_index(self) -> int:
        with self._lock:
            return self._next_index

    def records_between(self, start: int, end: int) -> list[CallRecord]:
        with self._lock:
            return [r for r in self._records if start <= r.index < end]

    @property
    def total_calls(self) -> int:
        with self._lock:
            return self._next_index

    def create(self, **kwargs):
        kwargs.setdefault('max_tokens', MAX_TOKENS)
        messages = kwargs.get('messages') or []
        stream = bool(kwargs.get('stream', False))
        kind = classify_call(messages)
        with self._lock:
            index = self._next_index
            self._next_index += 1
        t0 = time.perf_counter()
        phase = _current_phase.get()
        if not stream:
            resp = self._real.create(**kwargs)
            dt = time.perf_counter() - t0
            usage = getattr(resp, 'usage', None)
            choices = getattr(resp, 'choices', None)
            self._append(CallRecord(
                index=index, kind=kind, stream=False, phase=phase, seconds=dt,
                first_token_s=dt, chunks=1,
                prompt_tokens=getattr(usage, 'prompt_tokens', None),
                completion_tokens=getattr(usage, 'completion_tokens', None),
                finish_reason=getattr(choices[0], 'finish_reason', None) if choices else None,
            ))
            return resp
        gen = self._real.create(**kwargs)
        return self._streaming(gen, index, kind, phase, t0)

    def _streaming(self, gen, index, kind, phase, t0):
        first_token_s = None
        chunks = 0
        finish_reason = None
        try:
            for chunk in gen:
                chunks += 1
                choice = (chunk.choices or [None])[0]
                if choice is None:
                    continue
                delta = getattr(choice, 'delta', None)
                if first_token_s is None and getattr(delta, 'content', None):
                    first_token_s = time.perf_counter() - t0
                fr = getattr(choice, 'finish_reason', None)
                if fr:
                    finish_reason = fr
                yield chunk
        finally:
            self._append(CallRecord(
                index=index, kind=kind, stream=True, phase=phase,
                seconds=time.perf_counter() - t0, first_token_s=first_token_s,
                chunks=chunks, prompt_tokens=None, completion_tokens=None,
                finish_reason=finish_reason,
            ))

    def _append(self, rec: CallRecord) -> None:
        with self._lock:
            self._records.append(rec)


def install_instrumentation(client) -> MeasuredCompletions | None:
    if type(client).__name__ != 'OpenAI':
        return None
    measured = MeasuredCompletions(client.chat.completions)
    client.chat.completions = measured
    return measured


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _agg(vals: list[float]) -> dict:
    return {
        'count': len(vals),
        'p50_s': round(statistics.median(vals), 2) if vals else None,
        'max_s': round(max(vals), 2) if vals else None,
    }


def llm_stats(records: list[CallRecord]) -> dict:
    by_kind: dict[str, list[float]] = {}
    by_phase: dict[str, list[float]] = {}
    for r in records:
        by_kind.setdefault(r.kind, []).append(r.seconds)
        by_phase.setdefault(r.phase, []).append(r.seconds)
    return {
        'calls': len(records),
        'prompt_tokens': sum(r.prompt_tokens or 0 for r in records),
        'completion_tokens': sum(r.completion_tokens or 0 for r in records),
        'wall_seconds_sum_calls': round(sum(r.seconds for r in records), 2),
        'by_kind': {k: _agg(v) for k, v in sorted(by_kind.items())},
        'by_phase': {k: _agg(v) for k, v in sorted(by_phase.items())},
    }


def doc_metrics(snapshot: dict) -> dict:
    parts = snapshot.get('parts') or []
    words: dict[str, set[str]] = {}
    for p in parts:
        pid = p.get('id', '?')
        words[pid] = set(w for w in (p.get('body') or '').lower().split() if len(w) > 3)
    dups = []
    ids = list(words)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            union = words[a] | words[b]
            if union:
                dups.append({'a': a, 'b': b, 'jaccard': round(len(words[a] & words[b]) / len(union), 3)})
    dups.sort(key=lambda d: -d['jaccard'])
    ops: Counter = Counter()
    for entry in snapshot.get('op_log') or []:
        if isinstance(entry, dict):
            op = entry.get('op')
            if isinstance(op, dict) and 'type' in op:
                ops[op['type']] += 1
    return {
        'part_count': len(parts),
        'part_kinds': dict(Counter(p.get('kind', '?') for p in parts)),
        'part_titles': [p.get('title') or '' for p in parts],
        'summary_chars': len(snapshot.get('summary') or ''),
        'content_chars': sum(len(p.get('body') or '') for p in parts),
        'top_dup_pairs': dups[:3],
        'max_dup_jaccard': dups[0]['jaccard'] if dups else 0.0,
        'op_counts': dict(ops),
        'non_empty': any((p.get('body') or '').strip() for p in parts)
                     or bool((snapshot.get('summary') or '').strip()),
    }


def turn_health(entry: dict) -> dict:
    """Defensive summary of an orchestrator history entry."""
    exec_results = entry.get('execution_results') or []
    statuses: Counter = Counter()
    for r in exec_results:
        if isinstance(r, dict):
            st = r.get('status') or r.get('sub_task_status')
            statuses[str(st)] += 1
    decomp = entry.get('decomposition_history') or {}
    count = None
    for key in ('regenerated_sub_tasks', 'initial_tasks', 'decompose_response'):
        val = decomp.get(key)
        if isinstance(val, list):
            count = len(val)
            break
    return {'exec_entries': len(exec_results),
            'exec_status_counts': dict(statuses),
            'final_sub_task_count': count}


# ---------------------------------------------------------------------------
# Driving
# ---------------------------------------------------------------------------


def run_scenario(scenario: dict, client, measured: MeasuredCompletions, run_index: int) -> dict:
    record = {
        'scenario': scenario['id'],
        'run': run_index,
        'expectations': scenario.get('expect', {}),
        'turns': [],
        'events': [],
    }
    docs: dict[str, dict] = {}
    t0 = time.perf_counter()
    try:
        for ti, turn in enumerate(scenario['turns']):
            _current_phase.set(f'{scenario["id"]}:setup')
            doc = None
            prior = turn.get('prior')
            if prior and prior in docs:
                doc = Document(**docs[prior])
            idx_start = measured.start_index()
            turn_start = time.perf_counter()
            result = None
            orch = TaskOrchestrator.instantiate(llm_client=client)
            for kind, payload in orch.iter_query(turn['text'], document=doc):
                if kind == 'status':
                    _current_phase.set(str(payload))
                    record['events'].append(
                        {'t': round(time.perf_counter() - t0, 1), 'phase': str(payload)}
                    )
                else:
                    result = payload
            turn_wall = time.perf_counter() - turn_start
            idx_end = measured.start_index()
            if result is None:
                record['turns'].append(
                    {'index': ti, 'text': turn['text'], 'wall_seconds': round(turn_wall, 1),
                     'error': 'no result'}
                )
                continue
            snapshot = result.document_snapshot or {}
            docs[turn.get('name', f'{scenario["id"]}:t{ti}')] = snapshot
            entry = orch.history[-1] if orch.history else {}
            record['turns'].append({
                'index': ti,
                'text': turn['text'],
                'wall_seconds': round(turn_wall, 1),
                'llm': llm_stats(measured.records_between(idx_start, idx_end)),
                'document': doc_metrics(snapshot),
                'sub_tasks': turn_health(entry),
            })
    finally:
        record['total_wall_seconds'] = round(time.perf_counter() - t0, 1)
    return record


def main() -> int:
    sys.path.insert(0, str(Path(__file__).parent))
    from scenarios import SCENARIOS  # noqa: E402

    ap = argparse.ArgumentParser(description='Baseline & performance harness')
    ap.add_argument('--scenario', action='append', default=None,
                    help='scenario id (repeatable); default: all')
    ap.add_argument('--runs', type=int, default=2, help='runs per scenario (default 2)')
    ap.add_argument('--jobs', type=int, default=1,
                    help='scenarios to run concurrently (server has 5 slots)')
    ap.add_argument('--smoke', action='store_true',
                    help='cheap integration check: 1 run of the first scenario')
    ap.add_argument('--label', default=None)
    ap.add_argument('--out', default=str(Path(__file__).parent / 'runs'))
    args = ap.parse_args()

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in SCENARIOS if s['id'] in args.scenario]
        missing = set(args.scenario) - {s['id'] for s in scenarios}
        if missing:
            ap.error(f'unknown scenario(s): {", ".join(sorted(missing))}')
    if args.smoke:
        scenarios = scenarios[:1]
        args.runs = 1

    print(f'Backend: http://{DEFAULT_HOST}:{DEFAULT_PORT}/v1')
    print(f'Scenarios: {[s["id"] for s in scenarios]} x {args.runs} run(s), jobs={args.jobs}')

    client = create_llama_client()
    measured = install_instrumentation(client)
    if measured is None:
        print('ERROR: client is not a stock OpenAI client; cannot instrument.')
        return 2

    jobs = [(s, r) for s in scenarios for r in range(args.runs)]
    results: list[dict | None] = [None] * len(jobs)
    errors: list[str] = []

    def work(idx: int, item: tuple[dict, int]) -> None:
        s, r = item
        try:
            results[idx] = run_scenario(s, client, measured, r)
        except Exception as exc:  # noqa: BLE001 - report, keep other jobs
            errors.append(f'{s["id"]} run {r}: {exc!r}')

    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for i, item in enumerate(jobs):
                pool.submit(work, i, item)
    else:
        for i, item in enumerate(jobs):
            work(i, item)

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    label = args.label or ('smoke' if args.smoke else 'baseline')
    slug = '-'.join(s['id'] for s in scenarios)
    out_path = Path(args.out) / f'{stamp}_{label}_{slug}.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'backend': f'http://{DEFAULT_HOST}:{DEFAULT_PORT}/v1',
        'generated_at': stamp,
        'label': label,
        'runs_per_scenario': args.runs,
        'jobs': args.jobs,
        'caveat': ('per-turn LLM stats may include calls from concurrent turns '
                   'when jobs>1') if args.jobs > 1 else None,
        'total_calls_observed': measured.total_calls,
        'results': [r for r in results if r is not None],
        'errors': errors,
    }
    out_path.write_text(json.dumps(payload, indent=2))

    print('\n' + '=' * 100)
    for rec in [r for r in results if r is not None]:
        for turn in rec['turns']:
            if 'error' in turn:
                print(f"{rec['scenario']} r{rec['run']} t{turn['index']}: ERROR {turn['error']}")
                continue
            d = turn['document']
            ll = turn['llm']
            print(f"{rec['scenario']:<16} r{rec['run']} t{turn['index']}: "
                  f"wall={turn['wall_seconds']:>6}s calls={ll['calls']:>2} "
                  f"ptok={ll['prompt_tokens']:>6} ctok={ll['completion_tokens']:>6} "
                  f"parts={d['part_count']} {d['part_kinds']} "
                  f"dup={d['max_dup_jaccard']:.2f} ops={d['op_counts']}")
    if errors:
        print('\nERRORS:')
        for e in errors:
            print('  ' + e)
    print(f'\nWrote {out_path}')
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())