#!/usr/bin/env python3
"""Q-E1 arm drivers (Q-02 stage 0; D-019, D-020; journal/tickets/Q-02.md).

Runs bench prompts through the experiment's arms on one generator and
writes one run file per invocation, with wall time per call, per prompt and
per arm, tokens per prompt, and the commit it ran at.

Arms (paper name -> id here). Every arm gets the same prompt text, the same
model and the same per-call `max_tokens` (harness.MAX_TOKENS), and none
sends a temperature, so all of them sample at the server's defaults, as the
pipeline does:
  (a)  `a`   one call, thinking off
  (a′) `a1`  one call, thinking on
  (a″) `a2`  self-refine: draft, then rounds of critique -> revision,
             thinking off; every round's draft and critique is saved in
             the result's `rounds` (logging only, D-023). Rounds are set by
             one of three rules:
               --refine-budget-from B_RUN_FILE (the campaign's rule, Q-02
                 Notes 2026-10-24, delegated review): each prompt's budget is
                 the harness's (arm b's) completion tokens on that prompt in
                 the same generator's run file (the median over its runs);
                 a prompt b errored on gets b's median for its stratum.
               --refine-budget [FILE]: a budget per generator × stratum
                 (refine_budget.yaml, the pilots' harness medians; pilots
                 only).
               --refine-rounds: a fixed N per domain (the first pilots).
             Under a budget, after the draft, a round starts only while the
             prompt's completion tokens so far plus the last round's are at
             or below the budget; at least REFINE_MIN_ROUNDS, at most
             REFINE_CAP. A hard ceiling of REFINE_CEILING_FACTOR x the
             larger of the budget and its stratum's median caps every
             call's max_tokens: a round the ceiling cuts off is discarded
             (logged, `discarded: true`) and the output is the most recent
             complete draft. Each result logs `refine_budget` (stratum,
             budget, its source, ceiling, spent, rounds, stop reason:
             budget, cap or ceiling) and each round's completion tokens.
             Q-7 wants a2's median completion tokens per prompt at least
             0.75x the harness's (`match` reports the ratio)
  (b)  `b`   the harness (TaskOrchestrator, the harness's default config
             plus any --set overrides)
  (c)  `c`   the harness with consolidation on; meant for the overlap subset

Every call of a single-model arm continues until done: when it ends on
`length`, the driver sends CONTINUE_PROMPT with the partial output, at most
CONTINUE_CAP times, and joins the parts (design § 1, P6).

Follow-up prompts (`follows:` in the manifest) run in a chain after their
parent, in the same job and the same arm. The harness continues the
parent's Document; a single-model arm gets the parent exchange as chat
history (user prompt, its own final answer, the follow-up). Self-refine's
critique and revision prompts get the history spelled out (task_block).

Usage (from the repo root; the endpoint is required, D-008):
  export LLM_BASE_URL=http://localhost:8090/v1
  .venv/bin/python journal/baseline/arms.py run --generator flash-next \\
      --arm a --arm b --subset g3 --label q02-g3-smoke
  .venv/bin/python journal/baseline/arms.py run --generator qwen3.8-27b \\
      --arm a2 --refine-rounds code=1,report=2 --prompt c01 --prompt r03
  .venv/bin/python journal/baseline/arms.py run --generator qwen3.6-35b-a3b \\
      --arm a2 --refine-budget --subset g3
  .venv/bin/python journal/baseline/arms.py run --generator qwen3.6-35b-a3b \\
      --arm a2 --refine-budget-from journal/baseline/runs/<the b run file>.json
  .venv/bin/python journal/baseline/arms.py budget RUN_FILE [RUN_FILE ...]  # derive budgets
  .venv/bin/python journal/baseline/arms.py run ... --resume RUN_FILE
  .venv/bin/python journal/baseline/arms.py plan --subset overlap --arm c   # no calls
  .venv/bin/python journal/baseline/arms.py match RUN_FILE [RUN_FILE ...]

Output: journal/baseline/runs/<timestamp>_<label>_<generator>.json,
rewritten after every finished chain, so --resume continues an interrupted
campaign (finished results are kept, errored ones re-run). Stored harness
snapshots drop the op log (its counts stay in `document`), which keeps a
full arm near the run-file size rule (tickets/README rule 8).

Intermediates (the user, 2026-10-24): every harness turn's plan (the
decomposer's sub-tasks and its history: initial plan, critique,
regenerations) and its Document after every sub-task go to
intermediates/<run file stem>/<turn id>/NN_<kind>.json at the repo root
(git-ignored: large, on the big HDD), one file per TaskOrchestrator.on_step
event. A finished run writes manifest.json there (every file's sha256), and
the run file records the directory and the manifest's hash. Self-refine's
rounds stay in the run file (`rounds`). `intermediates.py score` scores them
all: hidden tests or checklists per intermediate, the final output against
the best one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import harness  # noqa: E402
from harness import REPO_ROOT  # noqa: E402

from reasoning_sub_agents.config import ConfigError  # noqa: E402
from reasoning_sub_agents.document import Document  # noqa: E402
from reasoning_sub_agents.llama_utils import (  # noqa: E402
    create_llama_client,
    message_reasoning,
    split_reasoning,
)
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator  # noqa: E402

DEFAULT_BENCH = Path(__file__).parent / 'bench' / 'v1'
DEFAULT_OUT = Path(__file__).parent / 'runs'

# Served model names (scripts/server/generator-server.sh). The endpoint is
# never defaulted: --base-url or LLM_BASE_URL (D-008).
GENERATORS = {
    'flash-next': 'qwen3.8-flash-next',
    'qwen3.8-27b': 'qwen3.8-27b',
    'qwen3.6-35b-a3b': 'qwen3.6-35b-a3b',
}
# Default --jobs per generator (Q-02 speed check, 2026-10-23, Notes): on the
# llama.cpp generators' 5 slots, 5 concurrent chains give ~1.5x (27B) and
# ~1.8x (35B-A3B) the throughput of 3 on a harness-shaped load, and 8 slots add
# only 7-8 %. flash-next (vLLM) was not measured, so it keeps 3.
DEFAULT_JOBS = {'flash-next': 3, 'qwen3.8-27b': 5, 'qwen3.6-35b-a3b': 5}
ARMS = ('a', 'a1', 'a2', 'b', 'c')
ARM_NAMES = {'a': '(a) single call, thinking off', 'a1': "(a') single call, thinking on",
             'a2': "(a'') self-refine", 'b': '(b) harness', 'c': '(c) harness + consolidation'}
SINGLE_ARMS = ('a', 'a1', 'a2')
DOMAINS = ('code', 'report')

CONTINUE_CAP = 3
# Self-refine under --refine-budget (the provisional amendment, Q-02 Notes).
REFINE_CAP = 8
REFINE_MIN_ROUNDS = 1
REFINE_CEILING_FACTOR = 3  # the hard ceiling, x the budget (the user, 2026-10-24)
INTERMEDIATES_ROOT = REPO_ROOT / 'intermediates'
DEFAULT_BUDGET = Path(__file__).parent / 'refine_budget.yaml'
STRATA = ('code-short', 'code-long', 'report-short', 'report-long')
# The prompts below are part of the pre-registration (Q-02 Notes); a change
# is a new version and voids comparisons with run files made before it.
PROMPTS_VERSION = 'arms-v1'
CONTINUE_PROMPT = ('Continue exactly where you stopped. Do not repeat anything you have '
                   'already written and do not comment on the interruption.')
CRITIQUE_PROMPT = """You are reviewing a response to a task. Find what keeps it from fully meeting the task: requirements it misses or gets wrong, errors (factual or logical mistakes, bugs in code), parts that are incomplete or cut off, and needless repetition. Be specific and say where in the response each problem is. Do not rewrite the response.

## Task

{task}

## Response

{response}

List the problems, most important first. If there are none, say so."""
REVISE_PROMPT = """## Task

{task}

## Current response

{response}

## Review of the current response

{critique}

Write an improved response to the task: fix the problems the review raises that are real, and keep what is already right. Reply with the complete response only, not a list of changes."""

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# The bench
# ---------------------------------------------------------------------------


def load_bench(bench_dir: Path) -> dict:
    """The manifest with each prompt's text, checked for dangling links."""
    manifest_path = bench_dir / 'manifest.yaml'
    manifest = yaml.safe_load(manifest_path.read_text())
    prompts: dict[str, dict] = {}
    drafts = []
    for raw in manifest['prompts']:
        entry = dict(raw)
        pid = entry['id']
        if pid in prompts or pid in drafts:
            raise ValueError(f'duplicate prompt id {pid}')
        if entry.get('status') == 'draft':
            # Brief only (bench README); a frozen bench has none.
            drafts.append(pid)
            continue
        if entry.get('domain') not in DOMAINS:
            raise ValueError(f'{pid}: domain must be one of {DOMAINS}')
        entry['text'] = (bench_dir / 'prompts' / f'{pid}.md').read_text().strip()
        entry.setdefault('follows', None)
        entry.setdefault('subsets', [])
        prompts[pid] = entry
    children: dict[str, str] = {}
    for pid, entry in prompts.items():
        parent = entry['follows']
        if parent is not None:
            if parent not in prompts:
                raise ValueError(f'{pid} follows unknown prompt {parent}')
            if prompts[parent]['domain'] != entry['domain']:
                raise ValueError(f'{pid} and its parent {parent} are in different domains')
            if parent in children:
                # Linear chains: no two chains share a prompt, so every
                # prompt's output is recorded once per arm and run.
                raise ValueError(f'{parent} has two follow-ups ({children[parent]}, {pid})')
            children[parent] = pid
    for pid in prompts:
        chain_of(prompts, pid)  # raises on a cycle
    if manifest.get('frozen') and drafts:
        raise ValueError(f'a frozen bench has draft prompts: {", ".join(drafts)}')
    return {'version': manifest.get('version'), 'frozen': bool(manifest.get('frozen')),
            'drafts': drafts,
            'path': manifest_path, 'sha256': sha256(manifest_path.read_text()),
            'prompts': prompts}


def stratum(entry: dict) -> str:
    return f'{entry["domain"]}-{"long" if entry.get("long") else "short"}'


def chain_of(prompts: dict[str, dict], pid: str) -> list[str]:
    """pid's ancestors, root first, ending with pid."""
    out = [pid]
    while prompts[out[0]]['follows'] is not None:
        out.insert(0, prompts[out[0]]['follows'])
        if len(out) > len(prompts):
            raise ValueError(f'follows cycle through {pid}')
    return out


def select(prompts: dict[str, dict], subset: str | None, ids: list[str] | None,
           domain: str | None) -> list[str]:
    """Selected prompt ids in manifest order. `subset` is a name from the
    manifest's `subsets` lists, or one of the flags long/followup/overlap."""
    chosen = []
    for pid, entry in prompts.items():
        if ids and pid not in ids:
            continue
        if domain and entry['domain'] != domain:
            continue
        if subset and subset != 'all':
            flags = {'long': entry.get('long'), 'followup': entry['follows'] is not None,
                     'overlap': entry.get('overlap') or entry['follows'] is not None}
            if subset in flags:
                if not flags[subset]:
                    continue
            elif subset not in entry['subsets']:
                continue
        chosen.append(pid)
    if ids:
        missing = set(ids) - set(prompts)
        if missing:
            raise ValueError(f'unknown prompt id(s): {", ".join(sorted(missing))}')
    return chosen


def plan_chains(prompts: dict[str, dict], selected: list[str]) -> list[list[str]]:
    """Chains that cover the selection. A follow-up pulls in its ancestors,
    which run (and are recorded) in the same job; a chain that is a prefix
    of another is dropped. Chains are linear (load_bench), so none overlap."""
    chains = [chain_of(prompts, pid) for pid in selected]
    return [c for c in chains if not any(o is not c and o[:len(c)] == c for o in chains)]


# ---------------------------------------------------------------------------
# Single-model arms
# ---------------------------------------------------------------------------


def _message_text(resp) -> tuple[str, str | None]:
    choice = resp.choices[0] if resp.choices else None
    message = getattr(choice, 'message', None)
    content = getattr(message, 'content', None) or ''
    if not message_reasoning(message):
        content = split_reasoning(content)[1]  # inline <think> never reaches the output
    return content, getattr(choice, 'finish_reason', None)


def complete(client, model: str, messages: list[dict], *, thinking: bool, phase: str,
             counters: dict, ceiling: int | None = None) -> str:
    """One logical call, continued until done: on `length` the partial output
    goes back as an assistant turn with CONTINUE_PROMPT, at most CONTINUE_CAP
    times. Returns the joined text.

    `ceiling` caps the prompt's completion tokens (counters['completion_tokens']
    so far included): each attempt's max_tokens is at most the room left, and
    when the room runs out the call stops there with counters['ceiling_hit']."""
    convo = list(messages)
    parts: list[str] = []
    for attempt in range(CONTINUE_CAP + 1):
        max_tokens = harness.MAX_TOKENS
        if ceiling is not None:
            room = ceiling - counters.get('completion_tokens', 0)
            if room <= 0:
                counters['ceiling_hit'] = True
                break
            max_tokens = min(max_tokens, room)
        harness._current_phase.set(phase if attempt == 0 else f'{phase} (continuation {attempt})')
        resp = client.chat.completions.create(
            model=model, messages=convo, max_tokens=max_tokens, stream=False,
            timeout=3600,
            extra_body={'chat_template_kwargs': {'enable_thinking': thinking}},
        )
        text, finish = _message_text(resp)
        parts.append(text)
        usage = getattr(resp, 'usage', None)
        ctok = getattr(usage, 'completion_tokens', None)
        if ctok is None:  # no usage from the server: estimate, and say so
            counters['usage_missing'] = counters.get('usage_missing', 0) + 1
            ctok = len(text) // 4
        counters['completion_tokens'] = counters.get('completion_tokens', 0) + ctok
        counters['finish_reasons'].append(finish)
        if finish != 'length':
            break
        if ceiling is not None and counters['completion_tokens'] >= ceiling:
            counters['ceiling_hit'] = True  # cut off by the ceiling, not by max_tokens
            break
        if attempt == CONTINUE_CAP:
            counters['capped'] += 1
            break
        counters['continuations'] += 1
        convo = convo + [{'role': 'assistant', 'content': text},
                         {'role': 'user', 'content': CONTINUE_PROMPT}]
    return ''.join(parts)


def task_block(history: list[tuple[str, str]], prompt: str) -> str:
    """The task as the critic and the reviser see it: for a follow-up, the
    earlier requests and this arm's earlier deliverables, spelled out."""
    if not history:
        return prompt
    lines = []
    for i, (asked, answered) in enumerate(history):
        lines.append(('The user first asked:' if i == 0 else 'The user then asked:')
                     + f'\n\n{asked}\n\nThe deliverable they received was:\n\n{answered}')
    lines.append(f'The user then asked:\n\n{prompt}')
    return '\n\n'.join(lines)


def run_single(client, model: str, arm: str, prompt: str, history: list[tuple[str, str]],
               rounds: int, budget: dict | None = None) -> tuple[str, dict]:
    """One prompt through arm a, a1 or a2. Returns the output and counters.
    a2 runs `rounds` rounds, or, given `budget` ({stratum, tokens}), the
    budget rule in the module docstring."""
    counters = {'continuations': 0, 'capped': 0, 'finish_reasons': [], 'rounds': 0,
                'completion_tokens': 0}
    messages = []
    for asked, answered in history:
        messages += [{'role': 'user', 'content': asked},
                     {'role': 'assistant', 'content': answered}]
    messages.append({'role': 'user', 'content': prompt})
    if arm in ('a', 'a1'):
        return complete(client, model, messages, thinking=arm == 'a1', phase='Single call',
                        counters=counters), counters
    ceiling = (REFINE_CEILING_FACTOR * max(budget['tokens'], budget['stratum_median'])
               if budget else None)
    draft = complete(client, model, messages, thinking=False, phase='Self-refine draft',
                     counters=counters, ceiling=ceiling)
    # Every round's draft and critique, for the post-hoc confidence study
    # (D-023). Logging only: nothing below reads it back.
    counters['round_log'] = [{'round': 0, 'draft': draft,
                              'completion_tokens': counters['completion_tokens']}]
    task = task_block(history, prompt)
    last_round, stop = 0, 'rounds'
    if counters.get('ceiling_hit'):  # the draft alone reached the ceiling: it is all there is
        stop = 'ceiling'
    for r in range(0 if stop == 'ceiling' else (REFINE_CAP if budget else rounds)):
        spent = counters['completion_tokens']
        # The full last round predicts the next: rounds mostly grow (Q-02
        # Notes 2026-10-24), so half of it would overshoot.
        if budget and r >= REFINE_MIN_ROUNDS and spent + last_round > budget['tokens']:
            stop = 'budget'
            break
        critique = complete(
            client, model,
            [{'role': 'user', 'content': CRITIQUE_PROMPT.format(task=task, response=draft)}],
            thinking=False, phase=f'Self-refine critique round {r + 1}', counters=counters,
            ceiling=ceiling)
        revised = '' if counters.get('ceiling_hit') else complete(
            client, model,
            [{'role': 'user', 'content': REVISE_PROMPT.format(
                task=task, response=draft, critique=critique)}],
            thinking=False, phase=f'Self-refine revision round {r + 1}', counters=counters,
            ceiling=ceiling)
        last_round = counters['completion_tokens'] - spent
        if counters.get('ceiling_hit'):
            # Cut off by the ceiling: the round is discarded and the most
            # recent complete draft stands.
            counters['round_log'].append({'round': r + 1, 'critique': critique,
                                          'draft': revised, 'completion_tokens': last_round,
                                          'discarded': True})
            stop = 'ceiling'
            break
        draft = revised
        counters['rounds'] += 1
        counters['round_log'].append({'round': r + 1, 'critique': critique, 'draft': draft,
                                      'completion_tokens': last_round})
    else:
        if budget and stop != 'ceiling':
            stop = 'cap'
    if budget:
        counters['budget'] = {'stratum': budget['stratum'], 'budget': budget['tokens'],
                              'source': budget['source'], 'ceiling': ceiling, 'spent': counters['completion_tokens'],
                              'rounds': counters['rounds'], 'stop': stop,
                              'cap': REFINE_CAP, 'min_rounds': REFINE_MIN_ROUNDS}
    return draft, counters


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def trim_snapshot(snapshot: dict) -> dict:
    out = {k: v for k, v in snapshot.items() if k != 'op_log'}
    out['op_log_len'] = len(snapshot.get('op_log') or [])
    return out


def result_key(r: dict) -> tuple[str, str, int]:
    return r['prompt_id'], r['arm'], r['run']


def run_chain_single(client, model, measured, arm, chain, prompts, run_index,
                     rounds_by_domain, budgets=None) -> list[dict]:
    results = []
    history: list[tuple[str, str]] = []
    for pid in chain:
        entry = prompts[pid]
        turn_id = f'{arm}:{pid}#r{run_index}'
        harness._current_turn.set(turn_id)
        rounds = rounds_by_domain.get(entry['domain'], 0) if arm == 'a2' else 0
        budget = prompt_budget(budgets, pid, stratum(entry)) if arm == 'a2' and budgets else None
        t0 = time.perf_counter()
        error = None
        text, counters = '', {}
        try:
            text, counters = run_single(client, model, arm, entry['text'], history, rounds,
                                        budget)
        except Exception as exc:  # noqa: BLE001 - record it; the chain stops here
            error = repr(exc)
        wall = time.perf_counter() - t0
        calls = measured.records_for_turn(turn_id)
        results.append({
            'prompt_id': pid, 'arm': arm, 'run': run_index, 'chain': chain,
            'follows': entry['follows'], 'domain': entry['domain'], 'stratum': stratum(entry),
            'wall_seconds': round(wall, 1), 'llm': harness.llm_stats(calls),
            'calls': [asdict(c) for c in calls],
            'refine_rounds': counters.get('rounds'),
            # a2 under --refine-budget: stratum, budget, spent, rounds, stop
            'refine_budget': counters.get('budget'),
            # a2 only: [{round 0: draft}, {round k: critique, draft}, ...] (D-023)
            'rounds': counters.get('round_log'),
            'continuations': counters.get('continuations'),
            'capped': counters.get('capped'),
            'output': {'text': text, 'snapshot': None, 'chars': len(text)},
            'error': error,
        })
        if error is not None:
            results += [_skipped(rest, arm, run_index, chain, prompts, pid)
                        for rest in chain[chain.index(pid) + 1:]]
            break
        history.append((entry['text'], text))
    return results


def _skipped(pid, arm, run_index, chain, prompts, failed) -> dict:
    return {'prompt_id': pid, 'arm': arm, 'run': run_index, 'chain': chain,
            'follows': prompts[pid]['follows'], 'domain': prompts[pid]['domain'],
            'wall_seconds': 0.0, 'llm': harness.llm_stats([]), 'calls': [],
            'output': {'text': '', 'snapshot': None, 'chars': 0},
            'error': f'not run: {failed} failed earlier in the chain'}


def _jsonable(obj):
    if hasattr(obj, 'model_dump'):
        return obj.model_dump(mode='json')
    return str(obj)


def turn_dir_name(turn_id: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', turn_id)


class IntermediateWriter:
    """TaskOrchestrator.on_step -> intermediates/<run stem>/<turn id>/NN_<kind>.json.

    The turn comes from harness._current_turn (run_scenario sets it per
    turn). A turn's directory is cleared the first time this writer sees it,
    so a resumed chain's re-run replaces its old files."""

    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()
        self.seen: dict[str, int] = {}

    def __call__(self, kind: str, payload: dict) -> None:
        turn = harness._current_turn.get() or 'no-turn'
        d = self.root / turn_dir_name(turn)
        with self.lock:
            if turn not in self.seen:
                shutil.rmtree(d, ignore_errors=True)
                d.mkdir(parents=True, exist_ok=True)
                self.seen[turn] = 0
            n = self.seen[turn] = self.seen[turn] + 1
        step = payload.get('step')
        name = f'{n:02d}_{kind}' + (f'_{step}' if step is not None else '') + '.json'
        (d / name).write_text(json.dumps({'kind': kind, 'turn_id': turn, **payload},
                                         default=_jsonable))

    def manifest(self) -> dict:
        files = {str(f.relative_to(self.root)): hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in sorted(self.root.rglob('*.json')) if f.name != 'manifest.json'}
        text = json.dumps(files, indent=1)
        (self.root / 'manifest.json').write_text(text)
        return {'files': len(files), 'manifest_sha256': sha256(text)}


def run_chain_harness(client, measured, arm, chain, prompts, run_index, build,
                      log_tag, intermediates_root=None) -> list[dict]:
    scenario = {
        'id': f'{arm}:{chain[0]}',
        'turns': [{'name': pid, 'text': prompts[pid]['text'],
                   'prior': chain[i - 1] if i else None} for i, pid in enumerate(chain)],
    }
    record = harness.run_scenario(scenario, client, measured, run_index,
                                  build_orchestrator=build, log_tag=log_tag)
    by_index = {t['index']: t for t in record['turns']}
    results: list[dict] = []
    failed = None
    for i, pid in enumerate(chain):
        turn = by_index.get(i)
        if failed is not None or turn is None:
            # run_scenario stops at a turn that raised, and goes on without a
            # prior after one that returned nothing; neither is a fair turn.
            row = _skipped(pid, arm, run_index, chain, prompts, failed or pid)
            if failed is None:
                row['error'] = record.get('error') or 'no turn recorded'
        else:
            snapshot = turn.get('snapshot')
            text = Document.from_dict(snapshot).render() if snapshot else ''
            inter = None
            if intermediates_root is not None and turn.get('turn_id'):
                d = intermediates_root / turn_dir_name(turn['turn_id'])
                inter = {'dir': str(d.relative_to(REPO_ROOT)) if d.is_relative_to(REPO_ROOT)
                         else str(d), 'files': len(list(d.glob('*.json'))) if d.exists() else 0}
            row = {
                'prompt_id': pid, 'arm': arm, 'run': run_index, 'chain': chain,
                'follows': prompts[pid]['follows'], 'domain': prompts[pid]['domain'],
                'stratum': stratum(prompts[pid]), 'intermediates': inter,
                'wall_seconds': turn['wall_seconds'], 'llm': turn['llm'],
                'calls': turn.get('calls', []),
                'document': turn.get('document'), 'sub_tasks': turn.get('sub_tasks'),
                'output': {'text': text,
                           'snapshot': trim_snapshot(snapshot) if snapshot else None,
                           'chars': len(text)},
                'error': turn.get('error'),
            }
        if row['error'] is not None and failed is None:
            failed = pid
        results.append(row)
    return results


def parse_rounds(spec: str | None) -> dict[str, int]:
    """'2' -> both domains; 'code=1,report=2' -> per domain."""
    if not spec:
        return {}
    if '=' not in spec:
        return {d: int(spec) for d in DOMAINS}
    out = {}
    for item in spec.split(','):
        domain, _, n = item.partition('=')
        if domain not in DOMAINS:
            raise ValueError(f'--refine-rounds: unknown domain {domain!r}')
        out[domain] = int(n)
    return out


def load_budget(path: Path, generator: str) -> dict:
    """refine_budget.yaml's entry for one generator: {stratum: tokens}, plus the file's hash."""
    raw = yaml.safe_load(Path(path).read_text())
    per = (raw.get('budgets') or {}).get(generator)
    if not per:
        raise SystemExit(f'{path}: no refine budget for generator {generator!r}')
    bad = set(per) - set(STRATA)
    if bad:
        raise SystemExit(f'{path}: unknown strata {sorted(bad)} for {generator}')
    return {'path': str(Path(path).resolve().relative_to(REPO_ROOT))
            if Path(path).resolve().is_relative_to(REPO_ROOT) else str(path),
            'sha256': sha256(Path(path).read_text()), 'tokens': {k: int(v) for k, v in per.items()}}


def load_budget_from_run(path: Path, generator: str, manifest_sha256: str,
                         prompts: dict) -> dict:
    """Per-prompt budgets from a harness run file: arm b's error-free
    completion tokens per prompt (the median over runs), plus b's median per
    stratum for prompts b has no clean result on. Refuses a file from another
    generator or another bench manifest."""
    data = json.loads(Path(path).read_text())
    if data.get('generator') != generator:
        raise SystemExit(f'{path}: generator {data.get("generator")!r}, not {generator!r}')
    if data.get('manifest_sha256') != manifest_sha256:
        raise SystemExit(f'{path}: ran on another bench manifest '
                         f'({data.get("manifest_sha256")}); budgets must come from this one')
    per: dict[str, list[int]] = {}
    for r in data['results']:
        if r['arm'] == 'b' and r['error'] is None and r['prompt_id'] in prompts:
            per.setdefault(r['prompt_id'], []).append(r['llm']['completion_tokens'])
    by_prompt = {pid: int(statistics.median(v)) for pid, v in sorted(per.items())}
    by_stratum: dict[str, list[int]] = {}
    for pid, tokens in by_prompt.items():
        by_stratum.setdefault(stratum(prompts[pid]), []).append(tokens)
    return {'path': str(Path(path).resolve().relative_to(REPO_ROOT))
            if Path(path).resolve().is_relative_to(REPO_ROOT) else str(path),
            'sha256': sha256(Path(path).read_text()), 'source': 'run-file',
            'prompts': by_prompt,
            'tokens': {st: int(statistics.median(v)) for st, v in sorted(by_stratum.items())}}


def prompt_budget(budgets: dict, pid: str, st: str) -> dict:
    """One prompt's budget: its own (a run-file source) or its stratum's."""
    own = (budgets.get('prompts') or {}).get(pid)
    return {'stratum': st, 'tokens': own if own is not None else budgets['tokens'][st],
            'stratum_median': budgets['tokens'][st],
            'source': 'prompt' if own is not None
            else ('stratum-fallback' if budgets.get('source') == 'run-file' else 'stratum')}


def budget_report(files: list[Path], bench_dir: Path) -> dict:
    """Per generator × stratum: the median completion tokens per prompt of
    the harness (arm b, error-free results only) across the run files, which
    is the --refine-budget value; with n and the prompts behind it."""
    prompts = load_bench(bench_dir)['prompts']
    rows: dict[str, dict[str, dict[str, int]]] = {}
    for path in files:
        data = json.loads(Path(path).read_text())
        for r in data['results']:
            if r['arm'] != 'b' or r['error'] is not None or r['prompt_id'] not in prompts:
                continue
            per = rows.setdefault(data['generator'], {}).setdefault(
                stratum(prompts[r['prompt_id']]), {})
            per[r['prompt_id']] = r['llm']['completion_tokens']
    return {gen: {st: {'tokens': int(statistics.median(v.values())), 'n': len(v),
                       'prompts': dict(sorted(v.items()))}
                  for st, v in sorted(per.items())}
            for gen, per in sorted(rows.items())}


def summarise(results: list[dict]) -> dict:
    """Per arm × domain: prompts, errors, wall and tokens per prompt (medians
    and sums). Completion tokens include reasoning tokens (usage counts them)."""
    out: dict[str, dict] = {}
    for arm in ARMS:
        for domain in DOMAINS:
            rows = [r for r in results if r['arm'] == arm and r['domain'] == domain]
            if not rows:
                continue
            ok = [r for r in rows if r['error'] is None]
            ctok = [r['llm']['completion_tokens'] for r in ok]
            ptok = [r['llm']['prompt_tokens'] for r in ok]
            wall = [r['wall_seconds'] for r in ok]
            out[f'{arm}/{domain}'] = {
                'prompts': len(rows), 'errors': len(rows) - len(ok),
                'completion_tokens_p50': statistics.median(ctok) if ctok else None,
                'prompt_tokens_p50': statistics.median(ptok) if ptok else None,
                'reasoning_tokens_sum': sum(r['llm']['reasoning_tokens'] for r in ok),
                'wall_seconds_p50': statistics.median(wall) if wall else None,
                'wall_seconds_sum': round(sum(wall), 1),
                'calls_sum': sum(r['llm']['calls'] for r in ok),
                'output_chars_p50': statistics.median(r['output']['chars'] for r in ok)
                if ok else None,
                'continuations_sum': sum(r.get('continuations') or 0 for r in ok),
                'capped_sum': sum(r.get('capped') or 0 for r in ok),
            }
    return out


def check_served(client, model: str) -> list[str]:
    try:
        served = [m.id for m in client.models.list().data]
    except Exception as exc:  # noqa: BLE001 - one clear message, then stop
        raise SystemExit(f'generator endpoint {client.base_url} is unreachable: {exc!r}')
    if model not in served:
        raise SystemExit(f'generator model {model!r} is not served at {client.base_url} '
                         f'({served}); is the right generator up?')
    return served


def run_arms(args) -> int:
    bench = load_bench(Path(args.bench))
    prompts = bench['prompts']
    selected = select(prompts, args.subset, args.prompt, args.domain)
    chains = plan_chains(prompts, selected)
    arms = args.arm or ['b']
    rounds = parse_rounds(args.refine_rounds)
    budget = (load_budget(args.refine_budget, args.generator) if args.refine_budget
              else load_budget_from_run(args.refine_budget_from, args.generator,
                                        bench['sha256'], prompts)
              if args.refine_budget_from else None)
    if 'a2' in arms:
        if budget:
            needed = {stratum(prompts[p]) for c in chains for p in c}
            missing = needed - set(budget['tokens'])
            if missing:
                raise SystemExit(f'{budget["path"]} has no {args.generator} budget for '
                                 f'{", ".join(sorted(missing))}')
        else:
            needed = {prompts[p]['domain'] for c in chains for p in c}
            missing = needed - set(rounds)
            if missing:
                raise SystemExit('arm a2 needs --refine-budget-from, --refine-budget or '
                                 '--refine-rounds for '
                                 + ', '.join(sorted(missing)))
    try:
        base_cfg = harness.resolve_config(False, 'off', args.set)
        consol_cfg = harness.resolve_config(True, 'off', args.set)
    except (ConfigError, ValueError) as exc:
        raise SystemExit(str(exc))

    if not args.base_url:
        raise SystemExit('no endpoint: pass --base-url or set LLM_BASE_URL')
    env_url = os.environ.get('LLM_BASE_URL')
    if env_url and env_url != args.base_url:
        raise SystemExit(f'LLM_BASE_URL={env_url} would override --base-url={args.base_url}')
    model = GENERATORS[args.generator]
    env_model = os.environ.get('LLM_MODEL')
    if env_model and env_model != model:
        raise SystemExit(f'LLM_MODEL={env_model} contradicts --generator {args.generator} '
                         f'({model}); unset it')
    os.environ['LLM_MODEL'] = model  # the pipeline's calls read it (llama_utils._model_name)
    if args.jobs is None:
        args.jobs = DEFAULT_JOBS[args.generator]

    client = create_llama_client(base_url=args.base_url)
    backend = str(client.base_url).rstrip('/')
    served = check_served(client, model)
    measured = harness.install_instrumentation(client)
    if measured is None:
        raise SystemExit('client is not a stock OpenAI client; cannot instrument')

    results: list[dict] = []
    if args.resume:
        out_path = Path(args.resume)
        old = json.loads(out_path.read_text())
        for field, now in (('generator', args.generator), ('model', model),
                           ('manifest_sha256', bench['sha256']),
                           ('prompts_version', PROMPTS_VERSION),
                           ('overrides', args.set), ('refine_rounds', rounds),
                           ('refine_budget', budget)):
            if old.get(field) != now:
                raise SystemExit(f'--resume: {field} differs ({old.get(field)!r} vs {now!r})')
        head = harness.git_commit()['commit']
        if old.get('commit') != head:
            raise SystemExit(f'--resume: the file ran at commit {old.get("commit")}, HEAD is {head}; '
                             'resume from a worktree pinned at that commit')
        results = [r for r in old['results'] if r['error'] is None]
        label, started = old['label'], old['started_at']
    else:
        started = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        label = args.label or 'arms'
        out_path = Path(args.out) / f'{started}_{label}_{args.generator}.json'
        out_path.parent.mkdir(parents=True, exist_ok=True)
    done = {result_key(r) for r in results}
    writer = IntermediateWriter(Path(args.intermediates) / out_path.stem) \
        if any(a in ('b', 'c') for a in arms) else None

    # A chain re-runs whole unless every prompt in it finished: a follow-up
    # must continue the parent output it is recorded beside.
    jobs = [(arm, chain, run) for arm in arms for chain in chains for run in range(args.runs)
            if any((pid, arm, run) not in done for pid in chain)]
    print(f'Backend: {backend} model={model} bench={bench["version"]} '
          f'(frozen={bench["frozen"]}) arms={arms} prompts={len(selected)} '
          f'chains={len(chains)} jobs to run={len(jobs)} --jobs={args.jobs}')
    if not bench['frozen']:
        print('WARNING: the bench is not frozen; these results are not Q-E1 evidence')
    lock = threading.Lock()
    header = {
        'kind': 'q-e1-arms',
        'bench': bench['version'], 'bench_frozen': bench['frozen'],
        'manifest_path': str(bench['path'].relative_to(REPO_ROOT))
        if bench['path'].is_relative_to(REPO_ROOT) else str(bench['path']),
        'manifest_sha256': bench['sha256'],
        'prompt_sha256': {pid: sha256(prompts[pid]['text']) for c in chains for pid in c},
        'generator': args.generator, 'model': model, 'backend': backend,
        'served_models': served,
        'arms': arms, 'arm_names': {a: ARM_NAMES[a] for a in arms},
        'refine_rounds': rounds, 'refine_budget': budget,
        'refine_cap': REFINE_CAP if budget else None,
        'refine_min_rounds': REFINE_MIN_ROUNDS if budget else None,
        'continue_cap': CONTINUE_CAP,
        'max_tokens': harness.MAX_TOKENS, 'sampling': 'server defaults (no temperature sent)',
        'prompts_version': PROMPTS_VERSION,
        'prompts_sha256': sha256(CONTINUE_PROMPT + CRITIQUE_PROMPT + REVISE_PROMPT),
        'config': base_cfg.model_dump(mode='json', exclude={'llm'}),
        'overrides': args.set,
        'selection': {'subset': args.subset, 'prompt': args.prompt, 'domain': args.domain},
        'runs_per_prompt': args.runs, 'jobs': args.jobs,
        'intermediates_dir': (str(writer.root.relative_to(REPO_ROOT))
                              if writer.root.is_relative_to(REPO_ROOT) else str(writer.root))
        if writer else None,
        'caveat': ('per-call and per-prompt wall seconds are inflated by concurrent jobs; '
                   'use --jobs 1 for wall-time comparisons') if args.jobs > 1 else None,
    }
    arm_elapsed: dict[str, float] = {}
    errors: list[str] = []
    # The commit is read once, at the start; a resumed file keeps its own,
    # which --resume has checked is HEAD.
    provenance = {k: old[k] for k in ('commit', 'dirty')} if args.resume else harness.git_commit()

    def write() -> None:
        head = harness.git_commit()['commit']
        payload = {**header, **provenance,
                   'commit_at_end': head if head != provenance['commit'] else None,
                   'label': label, 'started_at': started,
                   'updated_at': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                   'results': sorted(results, key=lambda r: (r['arm'], r['prompt_id'], r['run'])),
                   'summary': summarise(results),
                   'arm_elapsed_seconds': arm_elapsed, 'errors': errors}
        tmp = out_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(out_path)

    def build_for(arm):
        cfg = consol_cfg if arm == 'c' else base_cfg

        def build():
            orch = TaskOrchestrator.from_orchestrator_config(cfg, llm_client=client)
            orch.on_step = writer
            return orch
        return build

    def work(_idx: int, job: tuple[str, list[str], int]) -> None:
        arm, chain, run = job
        try:
            if arm in SINGLE_ARMS:
                rows = run_chain_single(client, model, measured, arm, chain, prompts, run,
                                        rounds, budget)
            else:
                rows = run_chain_harness(client, measured, arm, chain, prompts, run,
                                         build_for(arm), f'{started}_',
                                         writer.root if writer else None)
        except Exception as exc:  # noqa: BLE001 - report, keep other jobs
            with lock:
                errors.append(f'{arm} {chain} r{run}: {exc!r}')
            return
        with lock:
            replaced = {result_key(r) for r in rows}
            results[:] = [r for r in results if result_key(r) not in replaced] + rows
            for r in rows:
                if r['error']:
                    errors.append(f'{r["arm"]} {r["prompt_id"]} r{r["run"]}: {r["error"]}')
            write()
        for r in rows:
            ll = r['llm']
            print(f'{r["arm"]:<3} {r["prompt_id"]:<6} r{r["run"]}: wall={r["wall_seconds"]:>7}s '
                  f'calls={ll["calls"]:>3} ptok={ll["prompt_tokens"]:>7} '
                  f'ctok={ll["completion_tokens"]:>6} rtok={ll["reasoning_tokens"]} '
                  f'chars={r["output"]["chars"]}'
                  + (f' ERROR {r["error"]}' if r['error'] else ''))

    # Arms run one after another, so each arm's elapsed time is its own.
    for arm in arms:
        arm_jobs = [j for j in jobs if j[0] == arm]
        t0 = time.perf_counter()
        harness.run_jobs(arm_jobs, work, args.jobs)
        arm_elapsed[arm] = round(arm_elapsed.get(arm, 0.0) + time.perf_counter() - t0, 1)
    if writer is not None and writer.root.exists():
        header['intermediates'] = writer.manifest()
    write()
    print(json.dumps(summarise(results), indent=2))
    print(f'\nWrote {out_path}')
    return 0 if not errors else 1


# ---------------------------------------------------------------------------
# Compute matching (Q-7)
# ---------------------------------------------------------------------------


def match_report(files: list[Path], tolerance: float = 0.25,
                 strata: dict[str, str] | None = None) -> dict:
    """Per generator × domain: the harness's median completion tokens per
    prompt against a2's at each N tried (`a2@N`; and a's, a1's), the ±25 %
    check, and the N that the N = 1 pilot's per-call medians predict:
    draft + N × (critique + revision). Rounds grow longer with N on long
    documents, so the prediction is a lower bound; verify it. Results are
    also reported per stratum (gen/code-long, ...), from each result's
    `stratum` or, for older run files, `strata` (prompt id -> stratum)."""
    rows: dict[tuple[str, str], dict[str, list]] = {}
    call_medians: dict[tuple[str, str], dict[str, list[int]]] = {}
    for path in files:
        data = json.loads(Path(path).read_text())
        gen = data['generator']
        for r in data['results']:
            if r['error'] is not None:
                continue
            key = (gen, r['domain'])
            # a2 runs at different N are different arms for matching: a2@N,
            # and a2@budget under --refine-budget.
            if r['arm'] == 'a2':
                arm = 'a2@budget' if r.get('refine_budget') else f'a2@{r.get("refine_rounds")}'
            else:
                arm = r['arm']
            rows.setdefault(key, {}).setdefault(arm, []).append(r['llm']['completion_tokens'])
            st = r.get('stratum') or (strata or {}).get(r.get('prompt_id'))
            if st:
                rows.setdefault((gen, st), {}).setdefault(arm, []).append(
                    r['llm']['completion_tokens'])
            if r['arm'] == 'a2' and r.get('refine_rounds') == 1:
                per = call_medians.setdefault(key, {'draft': [], 'round': []})
                draft = sum(c['completion_tokens'] or 0 for c in r['calls']
                            if c['kind'] == 'refine_draft')
                per['draft'].append(draft)
                if r.get('refine_rounds'):
                    rounds_tok = sum(c['completion_tokens'] or 0 for c in r['calls']
                                     if c['kind'] in ('refine_critique', 'refine_revise'))
                    per['round'].append(rounds_tok / r['refine_rounds'])
    out = {}
    for (gen, domain), arms in sorted(rows.items()):
        med = {arm: statistics.median(v) for arm, v in arms.items()}
        entry = {'prompts': {arm: len(v) for arm, v in arms.items()}, 'completion_p50': med}
        target = med.get('b')
        if target:
            entry['within_25pct'] = {arm: abs(m - target) <= tolerance * target
                                     for arm, m in med.items() if arm != 'b'}
            # Q-7 as amended (2026-10-24): one-sided, a2 at least 0.75x the
            # harness; above 1.25x it is labelled over-resourced.
            entry['ratio_to_b'] = {arm: round(m / target, 3) for arm, m in med.items() if arm != 'b'}
            entry['q7_met'] = {arm: r >= 1 - tolerance for arm, r in entry['ratio_to_b'].items()}
            entry['over_resourced'] = [arm for arm, r in entry['ratio_to_b'].items()
                                       if r > 1 + tolerance]
            per = call_medians.get((gen, domain))
            if per and per['draft'] and per['round']:
                d, rnd = statistics.median(per['draft']), statistics.median(per['round'])
                entry['predicted_rounds'] = max(0, round((target - d) / rnd)) if rnd else None
                entry['draft_p50'], entry['round_p50'] = d, rnd
        out[f'{gen}/{domain}'] = entry
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Q-E1 arm drivers')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def selection(p):
        p.add_argument('--bench', default=str(DEFAULT_BENCH))
        p.add_argument('--subset', default=None,
                       help='a manifest subset (g3, ...), or long / followup / overlap / all')
        p.add_argument('--prompt', action='append', default=None, help='prompt id (repeatable)')
        p.add_argument('--domain', choices=DOMAINS, default=None)
        p.add_argument('--arm', action='append', choices=ARMS, default=None,
                       help='arm id (repeatable; default b): ' + ', '.join(
                           f'{k} = {v}' for k, v in ARM_NAMES.items()))

    run = sub.add_parser('run', help='run arms on a generator and write a run file')
    selection(run)
    run.add_argument('--generator', choices=sorted(GENERATORS), required=True)
    run.add_argument('--base-url', default=os.environ.get('LLM_BASE_URL'),
                     help='generator endpoint (default: $LLM_BASE_URL; required)')
    rule = run.add_mutually_exclusive_group()
    rule.add_argument('--refine-rounds', default=None,
                      help="a2's rounds: N for both domains or code=N,report=M")
    rule.add_argument('--refine-budget', nargs='?', const=str(DEFAULT_BUDGET), default=None,
                      metavar='FILE',
                      help=f"a2's rounds by token budget per stratum (default file: "
                           f"{DEFAULT_BUDGET.name}; pilots only)")
    rule.add_argument('--refine-budget-from', default=None, metavar='B_RUN_FILE',
                      help="a2's rounds by a per-prompt token budget: the harness's (arm b's) "
                           "completion tokens per prompt in this run file, same generator and "
                           "bench (the campaign's rule)")
    run.add_argument('--set', action='append', default=[], metavar='SECTION.KEY=VALUE',
                     help='OrchestratorConfig override for the harness arms (Q-05 ablations)')
    run.add_argument('--runs', type=int, default=1)
    run.add_argument('--jobs', type=int, default=None,
                     help='chains run concurrently (default per generator: '
                          + ', '.join(f'{g} {n}' for g, n in DEFAULT_JOBS.items())
                          + '); wall times need 1')
    run.add_argument('--label', default=None)
    run.add_argument('--resume', default=None, help='continue this run file')
    run.add_argument('--out', default=str(DEFAULT_OUT))
    run.add_argument('--intermediates', default=str(INTERMEDIATES_ROOT),
                     help='where harness plans and Document states go, one directory per run '
                          'file (default: <repo>/intermediates, git-ignored)')

    plan = sub.add_parser('plan', help='print the chains a selection runs; no calls')
    selection(plan)

    match = sub.add_parser('match', help='compute-matching report over run files (Q-7)')
    match.add_argument('files', nargs='+')
    match.add_argument('--bench', default=str(DEFAULT_BENCH),
                       help='for the strata of run files that predate the `stratum` field')

    budget = sub.add_parser('budget', help="a2's token budgets per generator × stratum: the "
                            "harness's median completion tokens in the given run files")
    budget.add_argument('files', nargs='+')
    budget.add_argument('--bench', default=str(DEFAULT_BENCH))

    args = ap.parse_args(argv)
    if args.cmd == 'match':
        prompts = load_bench(Path(args.bench))['prompts']
        strata = {pid: stratum(e) for pid, e in prompts.items()}
        print(json.dumps(match_report([Path(f) for f in args.files], strata=strata), indent=2))
        return 0
    if args.cmd == 'budget':
        print(yaml.safe_dump(budget_report([Path(f) for f in args.files], Path(args.bench)),
                             sort_keys=False))
        return 0
    if args.cmd == 'plan':
        bench = load_bench(Path(args.bench))
        selected = select(bench['prompts'], args.subset, args.prompt, args.domain)
        chains = plan_chains(bench['prompts'], selected)
        for arm in args.arm or ['b']:
            for chain in chains:
                print(f'{arm:<3} ' + ' -> '.join(chain))
        print(f'{len(selected)} prompts selected, {len(chains)} chains, '
              f'bench {bench["version"]} frozen={bench["frozen"]}')
        return 0
    return run_arms(args)


if __name__ == '__main__':
    raise SystemExit(main())
