"""How many concurrent requests a server should get, from real recorded requests
(the user, 2026-10-26: "do the speed test, prioritise speed").

Replays N chat requests recorded by llm_proxy.py (the longest prompts by default),
non-streamed, each capped at --max-tokens, at each concurrency in turn, after one
warm-up round, alternating the levels so cache warmth favours none. Reports per
level the makespan, completion tokens per second across the server, and the median
per-request seconds.

    .venv/bin/python journal/baseline/concurrency_bench.py --url http://localhost:8090/v1 \
        --model qwen3.8-flash-next --logs 'runs/ext/proxy-logs/fn-oc-like_*.jsonl' --levels 3 6 --n 24
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def load(pattern: str, n: int) -> list[dict]:
    reqs = []
    for f in glob.glob(pattern):
        for line in open(f):
            r = json.loads(line)
            q = r.get('request')
            if q and q.get('messages') and len(q['messages']) > 4:
                reqs.append((r.get('response') or {}).get('usage', {}).get('prompt_tokens') or 0, q)
    reqs.sort(key=lambda x: -x[0])
    return [q for _, q in reqs[:n]]


def call(url: str, body: dict) -> tuple[float, int]:
    t0 = time.time()
    req = urllib.request.Request(url + '/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    resp = json.loads(urllib.request.urlopen(req, timeout=3600).read())
    return time.time() - t0, (resp.get('usage') or {}).get('completion_tokens') or 0


def round_at(url: str, bodies: list[dict], level: int) -> dict:
    t0 = time.time()
    with ThreadPoolExecutor(level) as ex:
        out = list(ex.map(lambda b: call(url, b), bodies))
    span = time.time() - t0
    toks = sum(c for _, c in out)
    return {'level': level, 'makespan_s': round(span, 1), 'completion_tokens': toks,
            'tok_per_s': round(toks / span, 1), 'median_request_s': round(statistics.median(s for s, _ in out), 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--logs', required=True)
    ap.add_argument('--levels', type=int, nargs='+', default=[3, 6])
    ap.add_argument('--n', type=int, default=24)
    ap.add_argument('--max-tokens', type=int, default=512)
    ap.add_argument('--repeats', type=int, default=2)
    args = ap.parse_args(argv)
    bodies = []
    for q in load(args.logs, args.n):
        b = {k: v for k, v in q.items() if k not in ('stream', 'stream_options')}
        b.update(model=args.model, max_tokens=args.max_tokens, stream=False)
        b.pop('max_completion_tokens', None)
        bodies.append(b)
    print(f'{len(bodies)} requests; warm-up at {max(args.levels)}', flush=True)
    round_at(args.url, bodies, max(args.levels))
    rows = []
    for rep in range(args.repeats):
        for level in (args.levels if rep % 2 == 0 else list(reversed(args.levels))):
            r = round_at(args.url, bodies, level)
            rows.append(r)
            print(json.dumps(r), flush=True)
    summary = {lv: round(statistics.mean(r['tok_per_s'] for r in rows if r['level'] == lv), 1) for lv in args.levels}
    best = max(summary, key=summary.get)
    print(json.dumps({'tok_per_s_by_level': summary, 'best': best}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
