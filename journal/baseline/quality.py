#!/usr/bin/env python3
"""Phase Q judge tool (Q-01 stage 2; design: journal/design/Q-01-judge.md).

Judges a manifest of candidate pairs pairwise, both orders, and writes a
verdict file. Judging is its own pass over committed outputs (D-019): it
never runs the generator, and it never runs inside a timing-gate window
(Q-4), so claim the server in journal/INDEX.md first.

Usage (from the repo root; the judge endpoint and model are required, via
flags or JUDGE_BASE_URL / JUDGE_MODEL - there is no default, D-008):
  .venv/bin/python journal/baseline/quality.py judge \\
      --pairs journal/baseline/bench/validation/pairs.yaml \\
      --judge-base-url http://host.containers.internal:8091/v1 \\
      --judge-model qwen3.8-flash-next --repeat 2 --label q01-self
  .venv/bin/python journal/baseline/quality.py report VERDICTS.json

Step one is a reachability check (GET /models). The client is a stock
`OpenAI` instance (AGENTS.md). Every call sends the explicit thinking switch
(D-013, default off) at temperature 0 with a fixed seed.

Protocol (design § 3): each pair is judged with candidate a shown first
(order `ab`) and second (order `ba`). A pair's outcome is the candidate that
wins both orders; anything else is a tie. A verdict that fails to parse is
retried once, then recorded as no verdict, which is excluded from the
decisive count (it is not a tie).

Output: journal/baseline/verdicts/<timestamp>_<label>.json, rewritten after
every call so `--resume` can continue an interrupted batch. It records the
judge endpoint and model, the rubric id and hash, the manifest hash, the
commit, and per call the tokens and wall seconds. Per-call wall seconds
inflate above --jobs 1, as in the harness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from reasoning_sub_agents.document import Document  # noqa: E402
from reasoning_sub_agents.llama_utils import (  # noqa: E402
    message_reasoning,
    reasoning_tokens,
    split_reasoning,
)

DEFAULT_RUBRIC = Path(__file__).parent / 'rubrics' / 'pairwise_v1.md'
DEFAULT_OUT = Path(__file__).parent / 'verdicts'
VERDICT_MAX_TOKENS = 2048
ORDERS = ('ab', 'ba')
WINNERS = ('A', 'B', 'tie')
# Q-1 and Q-5 bars (PLAN § Phase Q; design § 4).
REAL_MIN, DAMAGED_MIN, PADDED_MIN = 4, 4, 2
REPEAT_AGREEMENT_MIN = 0.90


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials (95 % by default)."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def render_snapshot(snapshot: dict) -> str:
    """A harness snapshot normalised for judging: render() only, so part
    ids, op log, summary and reasoning never reach the judge (design § 3)."""
    return Document.from_dict(snapshot).render()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def rubric_id(text: str) -> str:
    match = re.search(r'Version:\s*`([^`]+)`', text)
    if match is None:
        raise ValueError('rubric has no "Version: `id`" line')
    return match.group(1)


def load_pairs(path: Path) -> list[dict]:
    """The manifest's pairs with candidate text loaded (paths are relative
    to the manifest)."""
    data = yaml.safe_load(path.read_text())
    pairs = []
    for raw in data['pairs']:
        pair = dict(raw)
        for side in ('a', 'b'):
            pair[f'{side}_text'] = (path.parent / pair[side]).read_text()
        if pair.get('expected') not in (None, 'a', 'b', 'tie'):
            raise ValueError(f'{pair["pair_id"]}: expected must be a, b, tie or empty')
        pairs.append(pair)
    ids = [p['pair_id'] for p in pairs]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate pair_id in manifest')
    return pairs


def build_messages(rubric: str, task: str, first: str, second: str,
                   tests_first: str | None = None,
                   tests_second: str | None = None) -> list[dict]:
    def block(label: str, text: str, tests: str | None) -> str:
        tail = f'\n\ntests: {tests}' if tests else ''
        return f'<<<RESPONSE {label}>>>\n{text}\n<<<END RESPONSE {label}>>>{tail}'

    user = '\n\n'.join([
        f'<<<TASK>>>\n{task}\n<<<END TASK>>>',
        block('A', first, tests_first),
        block('B', second, tests_second),
        'Return only the JSON object.',
    ])
    return [{'role': 'system', 'content': rubric}, {'role': 'user', 'content': user}]


def parse_verdict(text: str | None) -> dict | None:
    """The judge's JSON object if it has a valid `winner`, else None."""
    _, answer = split_reasoning(text)
    fenced = re.search(r'```(?:json)?\s*(\{.*\})\s*```', answer, re.DOTALL)
    body = fenced.group(1) if fenced else answer[answer.find('{'):answer.rfind('}') + 1]
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    winner = str(data.get('winner', '')).strip()
    winner = 'tie' if winner.lower() == 'tie' else winner.upper()
    if winner not in WINNERS:
        return None
    data['winner'] = winner
    return data


def side_of(winner: str | None, order: str) -> str | None:
    """Map the judge's A/B to the pair's candidate a/b for this order."""
    if winner is None:
        return None
    if winner == 'tie':
        return 'tie'
    first, second = order
    return first if winner == 'A' else second


def pair_outcome(ab: str | None, ba: str | None) -> str:
    """Both orders on one repeat -> 'a', 'b', 'tie' or 'no_verdict'."""
    if ab is None or ba is None:
        return 'no_verdict'
    return ab if ab == ba and ab != 'tie' else 'tie'


class Judge:
    """One judge endpoint and model, with the sampling settings recorded."""

    def __init__(self, client: OpenAI, model: str, *, thinking: bool = False,
                 seed: int = 0, max_tokens: int = VERDICT_MAX_TOKENS) -> None:
        self.client = client
        self.model = model
        self.thinking = thinking
        self.seed = seed
        self.max_tokens = max_tokens

    def settings(self) -> dict:
        return {'temperature': 0, 'seed': self.seed, 'max_tokens': self.max_tokens,
                'thinking': 'on' if self.thinking else 'off'}

    def attempt(self, messages: list[dict]) -> dict:
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=0, seed=self.seed,
            max_tokens=self.max_tokens,
            extra_body={'chat_template_kwargs': {'enable_thinking': self.thinking}},
        )
        seconds = time.perf_counter() - t0
        choice = resp.choices[0]
        content = choice.message.content or ''
        reasoning = message_reasoning(choice.message) or split_reasoning(content)[0]
        usage = resp.usage
        verdict = parse_verdict(content)
        return {
            'seconds': round(seconds, 3),
            'finish_reason': choice.finish_reason,
            'prompt_tokens': getattr(usage, 'prompt_tokens', None),
            'completion_tokens': getattr(usage, 'completion_tokens', None),
            'reasoning_tokens': reasoning_tokens(usage),
            'reasoning_chars': len(reasoning),
            'verdict': verdict,
            # Kept only when unparseable, to debug the rubric's output format.
            'raw': None if verdict else content[:2000],
        }

    def judge(self, messages: list[dict]) -> dict:
        """One pair-order: retried once on an unparseable verdict."""
        attempts = [self.attempt(messages)]
        if attempts[0]['verdict'] is None:
            attempts.append(self.attempt(messages))
        final = attempts[-1]
        return {
            'winner': final['verdict']['winner'] if final['verdict'] else None,
            'verdict': final['verdict'],
            'attempts': attempts,
            'seconds': round(sum(a['seconds'] for a in attempts), 3),
            'prompt_tokens': _sum(a['prompt_tokens'] for a in attempts),
            'completion_tokens': _sum(a['completion_tokens'] for a in attempts),
        }


def _sum(values) -> int | None:
    values = list(values)
    return None if any(v is None for v in values) else sum(values)


def check_reachable(client: OpenAI, model: str) -> list[str]:
    """Step one: the endpoint answers /models. Returns the served ids."""
    try:
        served = [m.id for m in client.models.list().data]
    except Exception as exc:  # noqa: BLE001 - one clear message, then stop
        raise SystemExit(f'judge endpoint {client.base_url} is unreachable: {exc!r}')
    if served and model not in served:
        print(f'WARNING: judge model {model!r} is not in /models {served}; '
              'llama-server ignores the name, vLLM will 404', file=sys.stderr)
    return served


def git_commit() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(['git', *args], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=False).stdout.strip()
    return {'commit': git('rev-parse', 'HEAD'),
            'dirty': bool(git('status', '--porcelain', '--untracked-files=no'))}


def call_key(call: dict) -> tuple[str, str, int]:
    return call['pair_id'], call['order'], call['repeat']


def summarise(pairs: list[dict], calls: list[dict]) -> dict:
    """Per-pair outcomes, Q-1 and Q-5 scoring, rates and cost (design § 3-5)."""
    by_key = {call_key(c): c for c in calls}
    repeats = sorted({c['repeat'] for c in calls})
    per_pair = []
    for pair in pairs:
        pid, expected = pair['pair_id'], pair.get('expected')
        rows = []
        for r in repeats:
            sides = {o: by_key.get((pid, o, r), {}).get('side') for o in ORDERS}
            if all((pid, o, r) not in by_key for o in ORDERS):
                continue
            outcome = pair_outcome(sides['ab'], sides['ba'])
            rows.append({'repeat': r, 'ab': sides['ab'], 'ba': sides['ba'],
                         'outcome': outcome,
                         'position_consistent': None if outcome == 'no_verdict'
                         else sides['ab'] == sides['ba']})
        per_pair.append({'pair_id': pid, 'kind': pair['kind'], 'expected': expected,
                         'repeats': rows, 'pass': [_passes(pair, row) for row in rows]})

    def score(kind: str, bar: int) -> dict:
        rows = [p for p in per_pair if p['kind'] == kind]
        first = [p['pass'][0] if p['pass'] else None for p in rows]
        if not rows:
            return {'n': 0}
        if any(v is None for v in first):
            return {'n': len(rows), 'status': 'pending',
                    'note': 'needs expected labels (the labelling app)'
                    if kind == 'real' else 'missing verdicts'}
        k = sum(first)
        return {'n': len(rows), 'passed': k, 'bar': bar,
                'status': 'pass' if k >= bar else 'fail',
                'all_repeats': [sum(p['pass'][i] for p in rows if len(p['pass']) > i)
                                for i in range(len(repeats))]}

    # Q-5: the same pair in the same order, judged twice, agrees.
    agree = total = 0
    if len(repeats) >= 2:
        r0, r1 = repeats[:2]
        for pair in pairs:
            for o in ORDERS:
                c0, c1 = by_key.get((pair['pair_id'], o, r0)), by_key.get((pair['pair_id'], o, r1))
                if c0 is None or c1 is None:
                    continue
                total += 1
                agree += c0['side'] is not None and c0['side'] == c1['side']
    q5 = {'pair_orders': total, 'agree': agree,
          'rate': round(agree / total, 3) if total else None,
          'bar': REPEAT_AGREEMENT_MIN,
          'status': None if not total else
          ('pass' if agree / total >= REPEAT_AGREEMENT_MIN else 'fail')}

    consistent = [row['position_consistent'] for p in per_pair for row in p['repeats']
                  if row['position_consistent'] is not None]
    # Win-rate of the expected side over the pairs that have one (design § 3).
    expected_outcomes = [
        'win' if row['outcome'] == p['expected'] else row['outcome']
        for p in per_pair if p['expected'] in ('a', 'b')
        for row in p['repeats'][:1]
    ]
    return {
        'pairs': per_pair,
        'q1': {'real': score('real', REAL_MIN), 'damaged': score('damaged', DAMAGED_MIN),
               'padded': score('padded', PADDED_MIN)},
        'q5': q5,
        'position_consistency': {'n': len(consistent), 'consistent': sum(consistent),
                                 'rate': round(sum(consistent) / len(consistent), 3)
                                 if consistent else None},
        'expected_side_rates': rates(expected_outcomes),
        'no_verdict_calls': sum(c['side'] is None for c in calls),
        'cost': cost(calls),
    }


def _passes(pair: dict, row: dict) -> bool | None:
    expected, outcome = pair.get('expected'), row['outcome']
    if outcome == 'no_verdict':
        return False
    if pair['kind'] == 'padded':
        # The padded side is not preferred in either order (design § 4).
        padded = 'b' if expected == 'a' else 'a'
        return padded not in (row['ab'], row['ba'])
    if expected is None:
        return None
    return outcome == expected


def rates(outcomes: list[str]) -> dict:
    """The three numbers per pairing (design § 3) for one side: 'win' for
    that side, 'tie', anything else ('a'/'b') a loss; 'no_verdict' excluded."""
    wins = outcomes.count('win')
    ties = outcomes.count('tie')
    n = sum(o != 'no_verdict' for o in outcomes)
    decisive = n - ties
    ci = wilson(wins, decisive)
    return {
        'n': n, 'decisive': decisive, 'wins': wins, 'ties': ties,
        'decisive_win_rate': round(wins / decisive, 3) if decisive else None,
        'wilson95': [round(x, 3) for x in ci] if ci else None,
        'tie_rate': round(ties / n, 3) if n else None,
        'all_pairs_rate': round((wins + 0.5 * ties) / n, 3) if n else None,
    }


def cost(calls: list[dict]) -> dict:
    """Tokens and wall-clock per call and in total (Q-4, D-019's addendum)."""
    secs = sorted(c['seconds'] for c in calls)
    attempts = sum(len(c['attempts']) for c in calls)
    return {
        'calls': len(calls), 'attempts': attempts,
        'prompt_tokens': _sum(c['prompt_tokens'] for c in calls),
        'completion_tokens': _sum(c['completion_tokens'] for c in calls),
        'seconds_sum': round(sum(secs), 1),
        'seconds_p50': round(secs[len(secs) // 2], 2) if secs else None,
        'seconds_max': round(secs[-1], 2) if secs else None,
    }


def run_judge(args) -> int:
    if not args.judge_base_url:
        raise SystemExit('no judge endpoint: pass --judge-base-url or set JUDGE_BASE_URL')
    if not args.judge_model:
        raise SystemExit('no judge model: pass --judge-model or set JUDGE_MODEL')
    pairs_path = Path(args.pairs)
    pairs = load_pairs(pairs_path)
    if args.pair:
        pairs = [p for p in pairs if p['pair_id'] in args.pair]
    rubric_path = Path(args.rubric)
    rubric = rubric_path.read_text()

    client = OpenAI(base_url=args.judge_base_url, api_key='sk-no-key-needed')
    served = check_reachable(client, args.judge_model)
    judge = Judge(client, args.judge_model, thinking=args.thinking == 'on', seed=args.seed)

    header = {
        'judge_backend': str(client.base_url).rstrip('/'),
        'judge_model': args.judge_model,
        'served_models': served,
        'rubric': rubric_id(rubric), 'rubric_path': str(rubric_path),
        'rubric_sha256': sha256(rubric),
        'pairs_path': str(pairs_path), 'pairs_sha256': sha256(pairs_path.read_text()),
        'settings': judge.settings(),
    }
    calls: list[dict] = []
    if args.resume:
        out_path = Path(args.resume)
        old = json.loads(out_path.read_text())
        for field in ('judge_backend', 'judge_model', 'rubric_sha256', 'pairs_sha256', 'settings'):
            if old[field] != header[field]:
                raise SystemExit(f'--resume: {field} differs ({old[field]!r} vs {header[field]!r})')
        calls = [c for c in old['calls'] if c['side'] is not None]
        label, started = old['label'], old['started_at']
    else:
        started = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        label = args.label or 'judge'
        out_path = Path(args.out) / f'{started}_{label}.json'
        out_path.parent.mkdir(parents=True, exist_ok=True)

    done = {call_key(c) for c in calls}
    todo = [(p, o, r) for r in range(args.repeat) for p in pairs for o in ORDERS
            if (p['pair_id'], o, r) not in done]
    print(f'Judge: {header["judge_backend"]} model={args.judge_model} '
          f'rubric={header["rubric"]} pairs={len(pairs)} repeat={args.repeat} '
          f'calls to run={len(todo)} jobs={args.jobs}')
    lock = threading.Lock()

    def write() -> None:
        payload = {**header, **git_commit(), 'label': label, 'started_at': started,
                   'updated_at': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                   'jobs': args.jobs,
                   'caveat': 'per-call seconds inflate above --jobs 1' if args.jobs > 1 else None,
                   'calls': sorted(calls, key=lambda c: (c['repeat'], c['pair_id'], c['order'])),
                   'summary': summarise(pairs, calls)}
        tmp = out_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(out_path)

    def work(item: tuple[dict, str, int]) -> None:
        pair, order, repeat = item
        first, second = order
        tests = pair.get('tests') or {}
        messages = build_messages(rubric, pair['task'], pair[f'{first}_text'],
                                  pair[f'{second}_text'], tests.get(first), tests.get(second))
        try:
            result = judge.judge(messages)
        except Exception as exc:  # noqa: BLE001 - record, keep the batch going
            print(f'{pair["pair_id"]} {order} r{repeat}: ERROR {exc!r}', file=sys.stderr)
            return
        call = {'pair_id': pair['pair_id'], 'order': order, 'repeat': repeat,
                'side': side_of(result['winner'], order), **result}
        with lock:
            calls.append(call)
            write()
        print(f'{pair["pair_id"]:<4} {order} r{repeat}: winner={result["winner"]} '
              f'side={call["side"]} {result["seconds"]:.1f}s '
              f'ptok={result["prompt_tokens"]} ctok={result["completion_tokens"]}')

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(work, todo))
    write()
    print_report(json.loads(out_path.read_text()))
    print(f'\nWrote {out_path}')
    return 0


def print_report(data: dict) -> None:
    s = data['summary']
    print(f'\njudge={data["judge_model"]} @ {data["judge_backend"]} rubric={data["rubric"]} '
          f'commit={data["commit"][:7]}{"+dirty" if data["dirty"] else ""}')
    print(f'{"pair":<5} {"kind":<8} {"exp":<4} repeats (ab/ba -> outcome)')
    for p in s['pairs']:
        cells = ' | '.join(f'{r["ab"]}/{r["ba"]} -> {r["outcome"]}' for r in p['repeats'])
        print(f'{p["pair_id"]:<5} {p["kind"]:<8} {str(p["expected"]):<4} {cells}  pass={p["pass"]}')
    for kind, res in s['q1'].items():
        print(f'Q-1 {kind}: {res}')
    print(f'Q-5 repeatability: {s["q5"]}')
    print(f'position consistency: {s["position_consistency"]}')
    print(f'expected-side rates: {s["expected_side_rates"]}')
    print(f'no-verdict calls: {s["no_verdict_calls"]}')
    print(f'cost: {s["cost"]}')


def main() -> int:
    ap = argparse.ArgumentParser(description='Phase Q pairwise judge (Q-01)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    j = sub.add_parser('judge', help='judge a pairs manifest, both orders')
    j.add_argument('--pairs', required=True, help='pairs manifest (YAML)')
    j.add_argument('--pair', action='append', default=None, help='pair_id (repeatable)')
    j.add_argument('--judge-base-url', default=os.environ.get('JUDGE_BASE_URL'),
                   help='judge endpoint (default: $JUDGE_BASE_URL; required)')
    j.add_argument('--judge-model', default=os.environ.get('JUDGE_MODEL'),
                   help='judge model name (default: $JUDGE_MODEL; required)')
    j.add_argument('--rubric', default=str(DEFAULT_RUBRIC))
    j.add_argument('--repeat', type=int, default=1,
                   help='judge every pair-order this many times (Q-5 uses 2)')
    j.add_argument('--thinking', choices=('off', 'on'), default='off')
    j.add_argument('--seed', type=int, default=0)
    j.add_argument('--jobs', type=int, default=1,
                   help='concurrent judge calls; per-call seconds inflate above 1')
    j.add_argument('--label', default=None)
    j.add_argument('--resume', default=None, help='verdict file to continue')
    j.add_argument('--out', default=str(DEFAULT_OUT))
    r = sub.add_parser('report', help='print the summary of a verdict file')
    r.add_argument('verdicts')
    args = ap.parse_args()
    if args.cmd == 'report':
        print_report(json.loads(Path(args.verdicts).read_text()))
        return 0
    return run_judge(args)


if __name__ == '__main__':
    sys.exit(main())
