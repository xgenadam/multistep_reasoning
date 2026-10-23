"""Phase 0+ baseline & performance harness.

Drives the real TaskOrchestrator end-to-end against the live model server and
records, per turn, BOTH time metrics (wall-clock, per-call latency, tokens,
calls by kind/phase) AND output metrics (part shape, duplication, op usage,
sub-task health) in one JSON file. That pairing is the point: if a
background run catches contention from other traffic (e.g. the agent's own
calls on the same server), the time numbers inflate while the output
numbers stay clean — which tells you to re-run, not to conclude.

Usage (from the repo root; the endpoint is required, via --base-url or
LLM_BASE_URL - there is no default):
  export LLM_BASE_URL=http://host.containers.internal:5000/v1
  .venv/bin/python journal/baseline/harness.py --smoke
  .venv/bin/python journal/baseline/harness.py                 # all scenarios, 2 runs each
  .venv/bin/python journal/baseline/harness.py --scenario s2_report --runs 3
  .venv/bin/python journal/baseline/harness.py --jobs 2        # concurrent scenarios (server has 5 slots)
  .venv/bin/python journal/baseline/harness.py --set components.executor=simple \
      --set components.oracle=null                             # any OrchestratorConfig field

Output: journal/baseline/runs/<timestamp>_<label>_<scenarios>.json plus a
console summary.

Every call is labelled from the orchestrator's own state (0-14, N13): the
last status event names the phase, and the `progress.llm_step` label splits
the two phases that make two kinds of call (critique inside decompose, oracle
asks inside execute). The system-prompt keyword classifier is only the
fallback; each call records which path labelled it (`label_source`).

Each call is attributed to its turn through a ContextVar (N14), so per-turn
counts and tokens are exact at any --jobs. Streamed calls ask for a final
usage chunk (N15); a server that omits it leaves `usage_reported: false` and
the turn says its token totals are partial.

Every call carries the thinking switch from `--thinking` (D-013, default
off); each record keeps the switch it was sent with, its `reasoning_tokens`
and a capped excerpt of its reasoning. The full text goes to the side log
under `/runs/thinking/`, never into the run file or a prompt.

`--set section.key=value` overrides any OrchestratorConfig field on top of
the defaults and the --consolidation/--thinking flags (Q-02 arms, Q-05
ablations); an unknown key is an error. The run file records the resolved
config, the overrides and the commit it ran at (Q-9).
"""

from __future__ import annotations

import argparse
import contextvars
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from reasoning_sub_agents.config import (  # noqa: E402
    ConfigError,
    OrchestratorConfig,
    apply_overrides,
    parse_orchestrator_config,
)
from reasoning_sub_agents.document import Document  # noqa: E402
from reasoning_sub_agents.llama_utils import (  # noqa: E402
    create_llama_client,
    message_reasoning,
    reasoning_tokens,
    split_reasoning,
)
from reasoning_sub_agents.progress import live, live_session  # noqa: E402
from reasoning_sub_agents.schemas import TaskStatus  # noqa: E402
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator  # noqa: E402

# D-P: no silent endpoint default. The endpoint comes from --base-url or
# LLM_BASE_URL; from the agent container it is
# http://host.containers.internal:5000/v1 (127.0.0.1 is refused there).
# Phase Q's judge endpoint is recorded the same way (JUDGE_BASE_URL).

# The server's default per-generation cap is ~2804 tokens (measured via
# /v1 probe: finish_reason=length at 2804 completion tokens). That truncates
# the long JSON completions (decompose/compose) and would truncate long prose
# turns. The server honors a per-request max_tokens, so the instrumentation
# raises the cap for every call it times. This is part of the baseline: a
# pipeline running under the 2.8K cap is not what it will run under after
# the fix lands (or via the oobabooga UI, which sets its own limit).
MAX_TOKENS = 8192
# Reasoning excerpt kept per call in the run file (tickets/README rule 8);
# the full text is in the side log.
REASONING_EXCERPT_CHARS = 500

_current_phase: contextvars.ContextVar[str] = contextvars.ContextVar(
    'baseline_phase', default='unknown'
)
# N14: the turn every call made in this context belongs to. Each job runs in
# its own copy_context(), so concurrent scenarios never share it.
_current_turn: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'baseline_turn', default=None
)

# N13: orchestrator status prefix -> call kind. Order matters: the legacy
# synthesiser status also starts with 'Executing', and its calls stay on the
# keyword fallback.
PHASE_KINDS: tuple[tuple[str, str | None], ...] = (
    ('Decomposing the request', 'decompose'),
    ('Executing sub-tasks (legacy', None),
    ('Executing ', 'executor_turn'),
    ('Composing after ', 'compose'),
    ('Updating summary after ', 'summary'),
    ('Consolidating document', 'consolidate'),
    # arms.py's single-model calls (Q-02): one call, and self-refine's three.
    ('Single call', 'single'),
    ('Self-refine draft', 'refine_draft'),
    ('Self-refine critique', 'refine_critique'),
    ('Self-refine revision', 'refine_revise'),
)
# llm_step labels that split a phase into two kinds of call.
STEP_KINDS: dict[str, dict[str, str]] = {
    'decompose': {'Critique decomposition': 'decompose_critique'},
    'executor_turn': {'Oracle ask': 'oracle'},
}
# The summary call that consolidation triggers (part of D-007's marginal cost).
CONSOLIDATION_SUMMARY_PHASE = 'Updating summary after consolidation'


def phase_kind(phase: str, step: str = '') -> str | None:
    """Call kind from the orchestrator phase and llm_step label, or None."""
    for prefix, kind in PHASE_KINDS:
        if phase.startswith(prefix):
            if kind is None:
                return None
            return STEP_KINDS.get(kind, {}).get(step, kind)
    return None


def classify_call(messages: list[dict]) -> str:
    """Fallback label for an LLM call from its system message(s).

    Only used when phase_kind() has no answer (calls outside a known phase,
    legacy synthesiser). It mislabels the current pipeline (N13): executor
    rounds land in `summary`, summary updates and the critique in
    `system_other`.

    instructor's JSON mode embeds the response schema in the system message,
    which is what makes the other labels work. The consolidation call is the
    one exception: its restricted schema contains no add_part, so the system
    scan would miss it; check its unique user-prompt signature first, before
    the scan short-circuits on system_other.
    """
    for msg in messages:
        if msg.get('role') == 'user' and 'document consolidator' in (
            msg.get('content') or ''
        ).lower():
            return 'consolidate'
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
    for msg in messages:
        if msg.get('role') == 'user':
            low = (msg.get('content') or '').lower()
            if 'document consolidator' in low:
                return 'consolidate'
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
    turn: str | None = None
    step: str = ''
    label_source: str = 'keyword'  # 'phase' | 'keyword'
    usage_reported: bool = False
    error: str | None = None  # exception type when the call raised
    thinking: bool | None = None  # enable_thinking the request carried (D-013)
    reasoning_tokens: int | None = None
    reasoning_chars: int = 0
    reasoning_excerpt: str = ''


def _switch(kwargs: dict) -> bool | None:
    template = (kwargs.get('extra_body') or {}).get('chat_template_kwargs') or {}
    return template.get('enable_thinking')


def _reasoning_fields(text: str, usage) -> dict:
    return dict(reasoning_tokens=reasoning_tokens(usage), reasoning_chars=len(text),
                reasoning_excerpt=text[:REASONING_EXCERPT_CHARS])


class MeasuredCompletions:
    """Wraps the OpenAI client's chat.completions to time and count calls.

    Records are append-only in a shared list with monotonic indices. Each
    record carries the turn id from `_current_turn`, so per-turn stats come
    from records_for_turn() and stay exact under concurrent turns.
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

    def records_for_turn(self, turn: str) -> list[CallRecord]:
        with self._lock:
            return sorted(
                (r for r in self._records if r.turn == turn), key=lambda r: r.index
            )

    def all_records(self) -> list[CallRecord]:
        with self._lock:
            return sorted(self._records, key=lambda r: r.index)

    @property
    def total_calls(self) -> int:
        with self._lock:
            return self._next_index

    def create(self, **kwargs):
        kwargs.setdefault('max_tokens', MAX_TOKENS)
        messages = kwargs.get('messages') or []
        stream = bool(kwargs.get('stream', False))
        if stream:
            # N15: ask for the final usage chunk; _streaming() swallows it.
            kwargs.setdefault('stream_options', {'include_usage': True})
        phase = _current_phase.get()
        state = live()
        step = state.llm_label if state is not None else ''
        kind = phase_kind(phase, step)
        label_source = 'phase'
        if kind is None:
            kind, label_source = classify_call(messages), 'keyword'
        with self._lock:
            index = self._next_index
            self._next_index += 1
        base = dict(index=index, kind=kind, phase=phase, turn=_current_turn.get(),
                    step=step, label_source=label_source, thinking=_switch(kwargs))
        t0 = time.perf_counter()
        try:
            resp = self._real.create(**kwargs)
        except BaseException as exc:
            # A call that raised still happened; keep it in its turn.
            self._append(CallRecord(
                **base, stream=stream, seconds=time.perf_counter() - t0,
                first_token_s=None, chunks=0, prompt_tokens=None,
                completion_tokens=None, error=type(exc).__name__,
            ))
            raise
        if not stream:
            dt = time.perf_counter() - t0
            usage = getattr(resp, 'usage', None)
            choices = getattr(resp, 'choices', None)
            message = getattr(choices[0], 'message', None) if choices else None
            text = (message_reasoning(message)
                    or split_reasoning(getattr(message, 'content', None))[0])
            self._append(CallRecord(
                **base, stream=False, seconds=dt, first_token_s=dt, chunks=1,
                prompt_tokens=getattr(usage, 'prompt_tokens', None),
                completion_tokens=getattr(usage, 'completion_tokens', None),
                finish_reason=getattr(choices[0], 'finish_reason', None) if choices else None,
                usage_reported=usage is not None,
                **_reasoning_fields(text, usage),
            ))
            return resp
        return self._streaming(resp, base, t0)

    def _streaming(self, gen, base: dict, t0: float):
        first_token_s = None
        chunks = 0
        finish_reason = None
        usage = None
        error = None
        reasoning: list[str] = []
        content: list[str] = []
        try:
            for chunk in gen:
                chunks += 1
                if getattr(chunk, 'usage', None) is not None:
                    usage = chunk.usage
                choice = (chunk.choices or [None])[0]
                if choice is None:
                    # The include_usage chunk has no choices; the pipeline
                    # indexes choices[0], so it never sees this chunk.
                    continue
                delta = getattr(choice, 'delta', None)
                if first_token_s is None and getattr(delta, 'content', None):
                    first_token_s = time.perf_counter() - t0
                reasoning.append(message_reasoning(delta))
                content.append(getattr(delta, 'content', None) or '')
                fr = getattr(choice, 'finish_reason', None)
                if fr:
                    finish_reason = fr
                yield chunk
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            self._append(CallRecord(
                **base, stream=True, seconds=time.perf_counter() - t0,
                first_token_s=first_token_s, chunks=chunks,
                prompt_tokens=getattr(usage, 'prompt_tokens', None),
                completion_tokens=getattr(usage, 'completion_tokens', None),
                finish_reason=finish_reason, usage_reported=usage is not None,
                error=error,
                **_reasoning_fields(
                    ''.join(reasoning) or split_reasoning(''.join(content))[0], usage),
            ))

    def _append(self, rec: CallRecord) -> None:
        with self._lock:
            self._records.append(rec)


def git_commit() -> dict:
    """The commit a run used, and whether tracked files differed from it.
    Read it when the run starts: HEAD can move while a run is going."""
    def git(*args: str) -> str:
        return subprocess.run(['git', *args], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=False).stdout.strip()
    return {'commit': git('rev-parse', 'HEAD'),
            'dirty': bool(git('status', '--porcelain', '--untracked-files=no'))}


def resolve_config(consolidation: bool, thinking: str,
                   overrides: list[str] | None) -> OrchestratorConfig:
    """Defaults, then the two option flags, then `--set` overrides."""
    raw = {'options': {'consolidation': consolidation, 'thinking': thinking}}
    return parse_orchestrator_config(apply_overrides(raw, overrides or []))


def install_instrumentation(client) -> MeasuredCompletions | None:
    if type(client).__name__ != 'OpenAI':
        return None
    measured = MeasuredCompletions(client.chat.completions)
    client.chat.completions = measured
    return measured


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _missing_usage(r: CallRecord) -> bool:
    """An answered call the server sent no usage for (a raised call has no
    answer; llm_stats counts those as calls_raised)."""
    return r.error is None and not r.usage_reported


def _agg(records: list[CallRecord]) -> dict:
    vals = [r.seconds for r in records]
    return {
        'count': len(vals),
        'p50_s': round(statistics.median(vals), 2) if vals else None,
        'max_s': round(max(vals), 2) if vals else None,
        'prompt_tokens': sum(r.prompt_tokens or 0 for r in records),
        'completion_tokens': sum(r.completion_tokens or 0 for r in records),
        'calls_without_usage': sum(_missing_usage(r) for r in records),
        'reasoning_tokens': sum(r.reasoning_tokens or 0 for r in records),
        'reasoning_chars': sum(r.reasoning_chars for r in records),
    }


def llm_stats(records: list[CallRecord]) -> dict:
    by_kind: dict[str, list[CallRecord]] = {}
    by_phase: dict[str, list[CallRecord]] = {}
    for r in records:
        by_kind.setdefault(r.kind, []).append(r)
        by_phase.setdefault(r.phase, []).append(r)
    without_usage = sum(_missing_usage(r) for r in records)
    return {
        'calls': len(records),
        'prompt_tokens': sum(r.prompt_tokens or 0 for r in records),
        'completion_tokens': sum(r.completion_tokens or 0 for r in records),
        'streamed_calls': sum(r.stream for r in records),
        'calls_without_usage': without_usage,
        # True when a server sent no usage for some call: the token sums
        # above are then a lower bound.
        'tokens_partial': without_usage > 0,
        'label_sources': dict(Counter(r.label_source for r in records)),
        'calls_raised': sum(r.error is not None for r in records),
        # D-013: calls sent with thinking on / with no explicit switch at all.
        'thinking_calls': sum(r.thinking is True for r in records),
        'calls_without_switch': sum(r.thinking is None for r in records),
        'reasoning_tokens': sum(r.reasoning_tokens or 0 for r in records),
        'reasoning_chars': sum(r.reasoning_chars for r in records),
        'wall_seconds_sum_calls': round(sum(r.seconds for r in records), 2),
        'by_kind': {k: _agg(v) for k, v in sorted(by_kind.items())},
        'by_phase': {k: _agg(v) for k, v in sorted(by_phase.items())},
    }


def doc_metrics(snapshot: dict, prior_ops: int = 0) -> dict:
    """Shape metrics for one snapshot.

    The op log is cumulative across turns; `prior_ops` is the length of the
    input document's log, so `turn_op_counts` holds this turn's ops only.
    """
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
    turn_ops: Counter = Counter()
    for i, entry in enumerate(snapshot.get('op_log') or []):
        if isinstance(entry, dict):
            op = entry.get('op')
            if isinstance(op, dict) and 'type' in op:
                ops[op['type']] += 1
                if i >= prior_ops:
                    turn_ops[op['type']] += 1
    headings = sum(
        1
        for p in parts
        for line in (p.get('body') or '').splitlines()
        if line.startswith('## ')
    )
    return {
        'part_count': len(parts),
        'part_kinds': dict(Counter(p.get('kind', '?') for p in parts)),
        'body_h2_headings': headings,
        'part_titles': [p.get('title') or '' for p in parts],
        'summary_chars': len(snapshot.get('summary') or ''),
        'content_chars': sum(len(p.get('body') or '') for p in parts),
        'top_dup_pairs': dups[:3],
        # None, not 0.0, when there is no pair to compare (N17).
        'max_dup_jaccard': dups[0]['jaccard'] if dups else None,
        'op_counts': dict(ops),
        'turn_op_counts': dict(turn_ops),
        'non_empty': any((p.get('body') or '').strip() for p in parts)
                     or bool((snapshot.get('summary') or '').strip()),
    }


BUDGET_EXHAUSTED = 'budget_exhausted'


def track_sub_task_statuses(executor) -> list[str] | None:
    """Record each sub-task's real outcome as the orchestrator runs it (N16).

    Wraps `executor.execute_one` on the instance: a raise is `failed` (the
    orchestrator stubs the sub-task and goes on, and the executor history
    gets no entry); a return is the sub-task's `TaskStatus`, except that an
    oracle loop that ran out of rounds is `budget_exhausted`, which
    `TaskStatus` cannot express yet (it says `completed`; N4, ticket 0-12).
    """
    real = getattr(executor, 'execute_one', None)
    if real is None:
        return None
    statuses: list[str] = []

    def execute_one(sub_task, *args, **kwargs):
        history = getattr(executor, 'history', None)
        seen = len(history) if isinstance(history, list) else 0
        try:
            out = real(sub_task, *args, **kwargs)
        except BaseException:
            statuses.append(TaskStatus.FAILED.value)
            raise
        new = history[seen:] if isinstance(history, list) else []
        if any(isinstance(e, dict) and e.get(BUDGET_EXHAUSTED) for e in new):
            statuses.append(BUDGET_EXHAUSTED)
        else:
            statuses.append(str(getattr(sub_task, 'status', None)))
        return out

    executor.execute_one = execute_one
    return statuses


def _history_statuses(exec_results: list) -> list[str]:
    """Statuses read back from executor history (misses failed sub-tasks)."""
    out = []
    for r in exec_results:
        if not isinstance(r, dict):
            continue
        if r.get(BUDGET_EXHAUSTED):
            out.append(BUDGET_EXHAUSTED)
            continue
        task = r.get('completed_sub_task')
        status = task.get('status') if isinstance(task, dict) else None
        out.append(str(status or r.get('status')))
    return out


def turn_health(entry: dict, statuses: list[str] | None = None) -> dict:
    """Defensive summary of an orchestrator history entry.

    `statuses` comes from track_sub_task_statuses(); without it they are
    read back from the executor history.
    """
    exec_results = entry.get('execution_results') or []
    if statuses is None:
        statuses = _history_statuses(exec_results)
    decomp = entry.get('decomposition_history') or {}
    count = None
    for key in ('regenerated_sub_tasks', 'initial_tasks', 'decompose_response'):
        val = decomp.get(key)
        if isinstance(val, list):
            count = len(val)
            break
    return {'exec_entries': len(exec_results),
            'exec_status_counts': dict(Counter(statuses)),
            'sub_task_statuses': list(statuses),
            'final_sub_task_count': count}


# ---------------------------------------------------------------------------
# Driving
# ---------------------------------------------------------------------------


def run_scenario(
    scenario: dict,
    client,
    measured: MeasuredCompletions,
    run_index: int,
    build_orchestrator=None,
    log_tag: str = '',
) -> dict:
    """Run one scenario's turns. log_tag prefixes each turn's thinking side
    log name, so runs on the same day do not share a file."""
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
            turn_id = f'{scenario["id"]}#r{run_index}:t{ti}'
            _current_turn.set(turn_id)
            _current_phase.set(f'{scenario["id"]}:setup')
            doc = None
            prior_ops = 0
            prior = turn.get('prior')
            if prior and prior in docs:
                snap = docs[prior]
                prior_ops = len(snap.get('op_log') or [])
                # to_dict() stores parts/op_log as plain dicts; from_dict()
                # rehydrates them so attribute access (outline(), render(),
                # ...) works on the reconstructed document (0-08).
                doc = Document.from_dict(snap)
            turn_start = time.perf_counter()
            result = None
            build = build_orchestrator or (lambda: TaskOrchestrator.instantiate(llm_client=client))
            orch = build()
            statuses = track_sub_task_statuses(getattr(orch, 'agent_executor', None))
            error = None
            try:
                # live_session() gives llm_step labels somewhere to land; the
                # harness reads them per call (phase_kind).
                with live_session() as state:
                    for kind, payload in orch.iter_query(
                            turn['text'], document=doc, turn_id=f'{log_tag}{turn_id}'):
                        if kind == 'status':
                            _current_phase.set(str(payload))
                            state.llm_label = ''  # a step label never spans phases
                            record['events'].append(
                                {'t': round(time.perf_counter() - t0, 1), 'phase': str(payload)}
                            )
                        else:
                            result = payload
            except Exception as exc:
                error = repr(exc)
                raise
            finally:
                # A turn that raised or returned nothing still made calls;
                # record them so every call lands in a turn.
                if error is not None or result is None:
                    record['turns'].append(
                        {'index': ti, 'turn_id': turn_id, 'text': turn['text'],
                         'wall_seconds': round(time.perf_counter() - turn_start, 1),
                         'error': error or 'no result',
                         'llm': llm_stats(measured.records_for_turn(turn_id))}
                    )
            if result is None:
                continue
            turn_wall = time.perf_counter() - turn_start
            calls = measured.records_for_turn(turn_id)
            snapshot = result.document_snapshot or {}
            docs[turn.get('name', f'{scenario["id"]}:t{ti}')] = snapshot
            entry = orch.history[-1] if orch.history else {}
            record['turns'].append({
                'index': ti,
                'turn_id': turn_id,
                'text': turn['text'],
                'wall_seconds': round(turn_wall, 1),
                'llm': llm_stats(calls),
                'calls': [asdict(c) for c in calls],  # re-scorable per call
                'document': doc_metrics(snapshot, prior_ops),
                'sub_tasks': turn_health(entry, statuses),
                'snapshot': snapshot,  # full parts/op_log for post-hoc inspection
            })
    except Exception as exc:  # noqa: BLE001 - keep the turns and calls made so far
        record['error'] = repr(exc)
    finally:
        record['total_wall_seconds'] = round(time.perf_counter() - t0, 1)
    return record


def run_jobs(items: list, work, n_jobs: int) -> None:
    """Run work(i, item) for every item, n_jobs at a time.

    Each job runs in a fresh copy of the caller's context, so the phase and
    turn ContextVars a job sets never leak into another job, whichever pool
    thread it lands on (N14).
    """
    if n_jobs > 1:
        with ThreadPoolExecutor(max_workers=n_jobs) as pool:
            futures = [
                pool.submit(contextvars.copy_context().run, work, i, item)
                for i, item in enumerate(items)
            ]
            for f in futures:
                f.result()
    else:
        for i, item in enumerate(items):
            contextvars.copy_context().run(work, i, item)


def attribution_summary(measured: MeasuredCompletions, results: list[dict]) -> dict:
    """Global vs per-turn call/token totals; equal when attribution is exact."""
    records = measured.all_records()
    turn_calls = turn_ptok = turn_ctok = 0
    for rec in results:
        for turn in rec.get('turns', []):
            ll = turn.get('llm')
            if ll:
                turn_calls += ll['calls']
                turn_ptok += ll['prompt_tokens']
                turn_ctok += ll['completion_tokens']
    return {
        'calls': len(records),
        'calls_in_turns': turn_calls,
        'calls_unattributed': sum(r.turn is None for r in records),
        'prompt_tokens': sum(r.prompt_tokens or 0 for r in records),
        'prompt_tokens_in_turns': turn_ptok,
        'completion_tokens': sum(r.completion_tokens or 0 for r in records),
        'completion_tokens_in_turns': turn_ctok,
    }


def main() -> int:
    sys.path.insert(0, str(Path(__file__).parent))
    from scenarios import SCENARIOS  # noqa: E402

    ap = argparse.ArgumentParser(description='Baseline & performance harness')
    ap.add_argument('--scenario', action='append', default=None,
                    help='scenario id (repeatable); default: all')
    ap.add_argument('--runs', type=int, default=2, help='runs per scenario (default 2)')
    ap.add_argument('--jobs', type=int, default=3,
                    help='scenarios to run concurrently (server has 5 slots; '
                         'default 3, try up to 4). Per-turn calls and tokens '
                         'are exact at any value; per-call wall times inflate '
                         'above 1, so timing gates (P0-4, compare.py) need 1')
    ap.add_argument('--smoke', action='store_true',
                    help='cheap integration check: 1 run of the first scenario')
    ap.add_argument('--consolidation', action='store_true',
                    help='enable the 0-06 consolidation pass after the final sub-task')
    ap.add_argument('--thinking', choices=('off', 'on'), default='off',
                    help="model thinking switch for every call (D-013; default off, "
                         "the baseline setting)")
    ap.add_argument('--set', action='append', default=[], metavar='SECTION.KEY=VALUE',
                    help='override an OrchestratorConfig field, e.g. components.executor=simple '
                         'or options.max_oracle_rounds=4 (repeatable; values parse as YAML)')
    ap.add_argument('--label', default=None)
    ap.add_argument('--base-url', default=os.environ.get('LLM_BASE_URL'),
                    help='generator endpoint, e.g. http://host.containers.internal:5000/v1 '
                         '(default: $LLM_BASE_URL; required)')
    ap.add_argument('--judge-base-url', default=os.environ.get('JUDGE_BASE_URL'),
                    help='judge endpoint for Phase Q (default: $JUDGE_BASE_URL); '
                         'recorded only, unused until Q-01')
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

    if not args.base_url:
        ap.error('no endpoint: pass --base-url or set LLM_BASE_URL '
                 '(e.g. http://host.containers.internal:5000/v1)')
    env_url = os.environ.get('LLM_BASE_URL')
    if env_url and env_url != args.base_url:
        ap.error(f'LLM_BASE_URL={env_url} would override --base-url={args.base_url}; '
                 'unset one of them')
    try:
        cfg = resolve_config(args.consolidation, args.thinking, args.set)
    except (ConfigError, ValueError) as exc:
        ap.error(str(exc))
    client = create_llama_client(base_url=args.base_url)
    backend = str(client.base_url).rstrip('/')
    print(f'Backend: {backend}')
    print(f'Scenarios: {[s["id"] for s in scenarios]} x {args.runs} run(s), '
          f'jobs={args.jobs}, thinking={args.thinking}')

    measured = install_instrumentation(client)
    if measured is None:
        print('ERROR: client is not a stock OpenAI client; cannot instrument.')
        return 2

    jobs = [(s, r) for s in scenarios for r in range(args.runs)]
    results: list[dict | None] = [None] * len(jobs)
    errors: list[str] = []

    options = cfg.options
    provenance = git_commit()
    started = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    def make_orchestrator(llm_client):
        return TaskOrchestrator.from_orchestrator_config(cfg, llm_client=llm_client)

    def work(idx: int, item: tuple[dict, int]) -> None:
        s, r = item
        try:
            results[idx] = run_scenario(
                s, client, measured, r,
                build_orchestrator=lambda: make_orchestrator(client),
                log_tag=f'{started}_',
            )
        except Exception as exc:  # noqa: BLE001 - report, keep other jobs
            errors.append(f'{s["id"]} run {r}: {exc!r}')
            return
        if 'error' in results[idx]:
            errors.append(f'{s["id"]} run {r}: {results[idx]["error"]}')

    run_jobs(jobs, work, args.jobs)
    done = [r for r in results if r is not None]
    attribution = attribution_summary(measured, done)

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    label = args.label or ('smoke' if args.smoke else 'baseline')
    slug = '-'.join(s['id'] for s in scenarios)
    out_path = Path(args.out) / f'{stamp}_{label}_{slug}.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'backend': backend,
        'judge_backend': args.judge_base_url,
        'generated_at': stamp,
        'label': label,
        'runs_per_scenario': args.runs,
        'jobs': args.jobs,
        **provenance,
        # HEAD when the file was written, if it moved during the run.
        'commit_at_end': (lambda end: end if end != provenance['commit'] else None)(
            git_commit()['commit']),
        # The components and options every turn ran with (the endpoint is
        # `backend`), and the --set overrides that produced them.
        'config': cfg.model_dump(mode='json', exclude={'llm'}),
        'overrides': args.set,
        # D-013: the switch every call was sent with, and where the full
        # reasoning text went (one JSONL per turn, named <started>_<turn id>).
        'thinking': {'setting': options.thinking, 'by_step': options.thinking_by_step,
                     'log_dir': options.thinking_log_dir, 'started_at': started},
        'caveat': ('per-call wall_seconds are inflated by concurrent server load; '
                   'use --jobs 1 for timing gates (per-turn calls and tokens are '
                   'exact, 0-14)')
                   if args.jobs > 1 else None,
        'total_calls_observed': measured.total_calls,
        'attribution': attribution,
        'results': done,
        'errors': errors,
    }
    out_path.write_text(json.dumps(payload, indent=2))

    print('\n' + '=' * 100)
    for rec in done:
        for turn in rec['turns']:
            if 'error' in turn:
                print(f"{rec['scenario']} r{rec['run']} t{turn['index']}: ERROR {turn['error']}")
                continue
            d = turn['document']
            ll = turn['llm']
            dup = d['max_dup_jaccard']
            print(f"{rec['scenario']:<16} r{rec['run']} t{turn['index']}: "
                  f"wall={turn['wall_seconds']:>6}s calls={ll['calls']:>2} "
                  f"ptok={ll['prompt_tokens']:>6} ctok={ll['completion_tokens']:>6}"
                  f"{'+' if ll['tokens_partial'] else ''} rtok={ll['reasoning_tokens']} "
                  f"parts={d['part_count']} {d['part_kinds']} "
                  f"dup={'n/a' if dup is None else f'{dup:.2f}'} ops={d['turn_op_counts']}")
    if attribution['calls'] != attribution['calls_in_turns']:
        print(f"\nWARNING: {attribution['calls'] - attribution['calls_in_turns']} "
              f"call(s) outside any recorded turn: {attribution}")
    if errors:
        print('\nERRORS:')
        for e in errors:
            print('  ' + e)
    print(f'\nWrote {out_path}')
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())