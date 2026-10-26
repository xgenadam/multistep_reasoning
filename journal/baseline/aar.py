"""After-action review of harness turns (the user, 2026-10-25; journal/design/meta-prompts.md).

Not part of the harness: it reads a finished run and asks a reviewer model where
each turn first went wrong, with verbatim evidence from the trace.

    # 1. condensed traces, one Markdown file per turn (also what Sonnet sub-agents read)
    .venv/bin/python journal/baseline/aar.py build RUN.json [--compare A.json] [--prompts c01 c05 ...] [--lost-only]
    # 2. a reviewer over them (any OpenAI-compatible server)
    .venv/bin/python journal/baseline/aar.py review RUN.json --base-url http://localhost:8100/v1 --model gemma-4-e4b --label gemma
    # 3. categories per reviewer, agreement between reviewers
    .venv/bin/python journal/baseline/aar.py summary RUN.json

Files go to runs/aar/<run stem>/ (git-ignored): <turn>.md, then <label>.jsonl
with one diagnosis per turn. A diagnosis counts only if its evidence checks out:
every quote must appear in that turn's trace (whitespace-insensitive), and at
least one quote must be given. The reviewer is offered the categories below,
with "other" always allowed, and not told which cause anyone suspects.

The trace is fullest for runs made with `arms.py run --trace-calls`. Older
runs lack the sub-task inputs, results and composer attempts; their traces say so.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import trace_view as tv  # noqa: E402

REPO_ROOT = tv.REPO_ROOT
OUT_ROOT = REPO_ROOT / 'runs' / 'aar'
TRACE_CHAR_BUDGET = 140_000  # about 35-45K tokens
CAP_MESSAGE = 10_000
CAP_REPLY = 10_000
CAP_PART = 8_000

CATEGORIES = {
    'plan': 'the decomposition: the sub-tasks themselves were the wrong split, scope or order',
    'sub_task_information': 'a sub-task was not given information it needed (from the request, the plan or earlier work)',
    'sub_task_work': 'a sub-task had what it needed but its own output was wrong or incomplete',
    'composer': 'combining the results into the document lost, broke, duplicated or misplaced work',
    'validity_check': "the harness's checks rejected acceptable work, or let broken work through",
    'scorer_extraction': 'the answer may be fine but the files could not be extracted from it as written',
    'other': 'none of these; say what',
}

REVIEW_PROMPT = """You are reviewing one run of a multi-step code-writing pipeline after the fact, to find where it went wrong.

How the pipeline works: a planner splits the user's request into sub-tasks; each sub-task is executed by a model that sees the request, its own sub-task and an outline of the document so far; after each sub-task a composer edits a shared document (adding, replacing or merging parts) to take in that sub-task's result, and the harness checks each edit, rejecting some and asking again; the final document is the answer. Hidden tests then run on the files extracted from the answer.

Below is the full record of one run, in order. For comparison it also shows a single direct answer to the same request, and how both scored.

Answer with JSON only:
{{
  "first_failure": {{"where": "<the section heading where it first went wrong, e.g. 'Step 2 / composer attempt 1'>", "call_index": <the call number if the record shows one, else null>}},
  "category": "<one of: {categories}>",
  "secondary": ["<other categories that also contributed, possibly empty>"],
  "explanation": "<what went wrong and why, in 2-5 sentences>",
  "evidence": [{{"quote": "<an exact quote from the record, 20-300 characters, copied character for character>", "why": "<what it shows>"}}],
  "smallest_fix": "<the smallest change to the pipeline (its instructions, checks or flow) that would most likely have avoided this failure>",
  "confidence": "<low | medium | high>"
}}

Categories:
{category_lines}

Give 1-4 evidence quotes. Copy them exactly from the record: they are checked.

=== RECORD ===
{trace}
=== END OF RECORD ===
"""


def clip(text: str | None, n: int) -> str:
    text = text or ''
    return text if len(text) <= n else text[:n] + f'\n[... {len(text) - n} more characters omitted]'


def diff_text(rows: list[list]) -> str:
    out = []
    for tag, _, left, _, right in rows:
        if tag == 'skip':
            out.append(f'  ... {left} unchanged lines')
        elif tag == 'eq':
            out.append(f'  {left}')
        else:
            if left is not None:
                out.append(f'- {left}')
            if right is not None:
                out.append(f'+ {right}')
    return '\n'.join(out)


def condense(turn: dict) -> str:
    """One turn as Markdown: what a reviewer reads. Repeated system prompts are given once."""
    lines: list[str] = []
    seen_system: dict[str, int] = {}

    def call_block(c: dict, full_prompt: bool) -> None:
        lines.append(f"#### Call {c['index']} ({c['kind']}{', ' + c['label'] if c.get('label') else ''}): "
                     f"{c.get('prompt_tokens')} prompt tokens, {c.get('completion_tokens')} completion tokens, "
                     f"finish {c.get('finish_reason')}{', ERROR ' + c['error'] if c.get('error') else ''}")
        if full_prompt:
            for m in c['messages']:
                if m['role'] == 'system':
                    key = m['text']
                    if key in seen_system:
                        lines.append(f"[system prompt: same as call {seen_system[key]}]")
                        continue
                    seen_system[key] = c['index']
                lines.append(f"[{m['role']}]\n{clip(m['text'], CAP_MESSAGE)}")
        else:
            last = next((m for m in reversed(c['messages']) if m['role'] == 'user'), None)
            if last:
                lines.append(f"[last user message]\n{clip(last['text'], CAP_MESSAGE // 2)}")
        if c.get('reasoning'):
            lines.append(f"[model reasoning]\n{clip(c['reasoning'], CAP_REPLY // 2)}")
        lines.append(f"[model reply]\n{clip(c['content'], CAP_REPLY)}")

    lines.append(f"# Run of prompt {turn['prompt_id']} (arm {turn['arm']}, run {turn['run']})")
    lines.append(f"## The user's request\n{clip(turn['prompt'], 20_000)}")
    plan = turn.get('plan')
    lines.append('## Plan')
    if plan:
        for i, st in enumerate(plan['sub_tasks'], 1):
            lines.append(f"{i}. **{st.get('name')}** ({st.get('type')}): {st.get('objective') or st.get('description')}\n"
                         f"   context given: {st.get('context') or '(none)'}")
        if plan.get('critique'):
            lines.append(f"### Critique of the plan\n{clip(plan['critique'], 6000)}")
        for c in tv_calls(turn, 'plan'):
            call_block(c, full_prompt=False)
    else:
        lines.append('(no plan recorded)')
    traced = turn.get('traced')
    if not traced:
        lines.append('(This run did not record call text: the sub-tasks\' inputs and the composer\'s prompts are not shown.)')
    for s in turn['steps']:
        head = 'Consolidation' if s['step'] == 'consolidation' else f"Step {s['step']} of {s['of']}: {s.get('sub_task')}"
        lines.append(f"## {head}" + (' (THE COMPOSER GAVE UP HERE)' if s['kind'] == 'compose_failed' else ''))
        exec_calls = tv_calls(turn, s['step'], ('executor_turn', 'oracle'))
        if exec_calls:
            lines.append(f"### Step {s['step']} / executor")
            for i, c in enumerate(exec_calls):
                call_block(c, full_prompt=(i == 0))
        lines.append(f"### Step {s['step']} / sub-task result")
        lines.append(clip(s['result'], CAP_REPLY) if s.get('result') is not None else '(not recorded)')
        attempts = s.get('compose_attempts')
        if attempts is None:
            lines.append(f"### Step {s['step']} / composer\n(attempts not recorded)")
        else:
            compose_calls = tv_calls(turn, s['step'], ('compose', 'consolidate'))
            for i, a in enumerate(attempts):
                verdict = ('FALLBACK: the result was added verbatim after: ' + str(a.get('fallback_after'))
                           if a.get('attempt') == 'fallback' else
                           'REJECTED: ' + a['error'] if a.get('error') else
                           'asked to see parts ' + ', '.join(a['need_part_ids']) if a.get('need_part_ids') else 'ACCEPTED')
                lines.append(f"### Step {s['step']} / composer attempt {a.get('attempt')}: {verdict}")
                if i == 0 and compose_calls:
                    call_block(compose_calls[0], full_prompt=True)
                for op in a.get('ops') or []:
                    meta = ' '.join(f'{k}={json.dumps(v)}' for k, v in op.items() if k not in ('body', 'type') and v is not None)
                    lines.append(f"- {op.get('type')} {meta}" + (f"\n```\n{clip(op['body'], CAP_PART)}\n```" if op.get('body') else ''))
                if a.get('keep'):
                    lines.append(f"  keep check: {json.dumps(a['keep'])}")
        lines.append(f"### Step {s['step']} / document after this step")
        for p in s['parts']:
            if p['change'] == 'same':
                lines.append(f"- {p['id']} ({p.get('kind')}): unchanged")
            elif p['change'] == 'changed' and p.get('diff'):
                lines.append(f"- {p['id']} ({p.get('kind')}): CHANGED\n```diff\n{clip(diff_text(p['diff']), CAP_PART)}\n```")
            else:
                lines.append(f"- {p['id']} ({p.get('kind')}): {p['change'].upper()}\n```\n{clip(p['body'], CAP_PART)}\n```")
    lines.append('## Final answer')
    if turn.get('error'):
        lines.append(f"The run ended with an error: {turn['error']}")
    lines.append(clip(turn.get('output'), 30_000))
    t = turn.get('test')
    lines.append('## Hidden tests on the final answer')
    if t:
        sc, ex = t['score'], t.get('extraction') or {}
        lines.append(f"{sc['passed']} of {sc['total']} passed. File extraction: {'ok' if sc['extraction_ok'] else 'INCOMPLETE'}"
                     f"{'; missing ' + ', '.join(sc['missing']) if sc['missing'] else ''}"
                     f"{'; unclosed code fence' if sc['unclosed_fence'] else ''}; files found {json.dumps(ex.get('files') or {})}")
        failed = [k for k, o in t['outcomes'].items() if o != 'passed']
        if failed:
            lines.append('Failed: ' + ', '.join(failed[:40]) + (f' (+{len(failed) - 40} more)' if len(failed) > 40 else ''))
        lines.append(f"pytest output (tail):\n```\n{clip(t.get('output_tail'), 6000)}\n```")
    else:
        lines.append('(not scored)')
    for label, c in (turn.get('compare') or {}).items():
        sc = c.get('score')
        lines.append(f"## For comparison: a single direct answer ({label}), "
                     + (f"{sc['passed']} of {sc['total']} hidden tests passed" if sc else 'not scored'))
        lines.append(clip(c.get('output'), 20_000))
    text = '\n\n'.join(lines)
    if len(text) > TRACE_CHAR_BUDGET:
        text = text[:TRACE_CHAR_BUDGET // 2] + (f'\n\n[... {len(text) - TRACE_CHAR_BUDGET} characters of the middle omitted '
                                                 'to fit the review budget ...]\n\n') + text[-TRACE_CHAR_BUDGET // 2:]
    return text


def tv_calls(turn: dict, step, kinds=None) -> list[dict]:
    return [c for c in turn.get('calls') or []
            if str(c.get('step')) == str(step) and (kinds is None or c['kind'] in kinds)]


def norm(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def check_evidence(diagnosis: dict, trace: str) -> dict:
    """Marks each quote found / not found; the diagnosis is valid if it gave one and all were found."""
    hay = norm(trace)
    quotes = diagnosis.get('evidence') or []
    found = [bool(q.get('quote')) and len(norm(q['quote'])) >= 10 and norm(q['quote']) in hay for q in quotes]
    return {'quotes': len(quotes), 'found': sum(found), 'valid': bool(quotes) and all(found),
            'category_known': diagnosis.get('category') in CATEGORIES}


def parse_reply(text: str) -> dict | None:
    text = re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', text or '')
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def review_prompt(trace: str) -> str:
    return REVIEW_PROMPT.format(categories=', '.join(CATEGORIES), trace=trace,
                                category_lines='\n'.join(f'- {k}: {v}' for k, v in CATEGORIES.items()))


def out_dir(run_file: Path) -> Path:
    return OUT_ROOT / run_file.stem


def cmd_build(args) -> int:
    run_file = Path(args.run_file).resolve()
    view_out = out_dir(run_file) / 'view'
    view_args = [str(run_file), '--bench', args.bench, '--out', str(view_out)]
    if args.compare:
        view_args += ['--compare', *args.compare]
    tv.main(view_args)  # the per-turn data the viewer uses is the source here too
    index = json.loads(re.search(r'const INDEX = (\{.*?\});\n', (view_out / 'index.html').read_text(), re.S).group(1))
    picked = []
    for t in index['turns']:
        if args.prompts and t['prompt_id'] not in args.prompts:
            continue
        if args.lost_only:
            first = index['meta']['compare'][0] if index['meta']['compare'] else None
            mine = t['score']['rate'] if t['score'] else 0.0
            if first is None or t['compare'].get(first) is None or mine >= t['compare'][first]:
                continue
        picked.append(t['slug'])
    for slug in picked:
        js = (view_out / 'data' / f'{slug}.js').read_text()
        turn = json.loads(js[js.index(',') + 1:js.rindex(');')].replace('<\\/', '</'))
        (out_dir(run_file) / f'{slug}.md').write_text(condense(turn))
    (out_dir(run_file) / 'turns.json').write_text(json.dumps(picked, indent=1))
    print(f'wrote {len(picked)} condensed traces to {out_dir(run_file)}')
    return 0


def cmd_review(args) -> int:
    from openai import OpenAI
    run_file = Path(args.run_file).resolve()
    d = out_dir(run_file)
    slugs = json.loads((d / 'turns.json').read_text())
    if args.prompts:
        slugs = [s for s in slugs if any(f'_{p}_' in s for p in args.prompts)]
    client = OpenAI(base_url=args.base_url, api_key='sk-no-key-needed', timeout=3600, max_retries=0)
    out = d / f'{args.label}.jsonl'
    done = {json.loads(l)['turn'] for l in out.read_text().splitlines() if l.strip()} if out.exists() else set()
    extra = {'chat_template_kwargs': {'enable_thinking': args.thinking}}
    for slug in slugs:
        if slug in done:
            continue
        trace = (d / f'{slug}.md').read_text()
        row = {'turn': slug, 'reviewer': args.label, 'model': args.model}
        try:
            resp = client.chat.completions.create(
                model=args.model, messages=[{'role': 'user', 'content': review_prompt(trace)}],
                max_tokens=args.max_tokens, response_format={'type': 'json_object'}, extra_body=extra)
            text = resp.choices[0].message.content or ''
            row.update(finish=resp.choices[0].finish_reason,
                       usage=resp.usage.model_dump() if resp.usage else None)
            diagnosis = parse_reply(text)
            row['diagnosis'] = diagnosis
            row['raw'] = None if diagnosis else text
            row['check'] = check_evidence(diagnosis, trace) if diagnosis else {'valid': False}
        except Exception as exc:  # noqa: BLE001 - one failed review is a row
            row.update(error=repr(exc), check={'valid': False})
        with out.open('a') as f:
            f.write(json.dumps(row) + '\n')
        print(f"{slug}: {(row.get('diagnosis') or {}).get('category', row.get('error', 'unparsed'))}"
              f" valid={row['check'].get('valid')}")
    return 0


def cmd_summary(args) -> int:
    d = out_dir(Path(args.run_file).resolve())
    by_reviewer: dict[str, dict[str, dict]] = {}
    for f in sorted(d.glob('*.jsonl')):
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        by_reviewer[f.stem] = {r['turn']: r for r in rows}
    for name, rows in by_reviewer.items():
        valid = [r for r in rows.values() if r['check'].get('valid')]
        cats = Counter(r['diagnosis']['category'] for r in valid)
        print(f"{name}: {len(rows)} reviews, {len(valid)} with checked evidence; "
              + ', '.join(f'{k} {n}' for k, n in cats.most_common()))
    names = list(by_reviewer)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            both = [t for t in by_reviewer[a] if t in by_reviewer[b]
                    and by_reviewer[a][t]['check'].get('valid') and by_reviewer[b][t]['check'].get('valid')]
            agree = sum(1 for t in both if by_reviewer[a][t]['diagnosis']['category']
                        == by_reviewer[b][t]['diagnosis']['category'])
            print(f'{a} vs {b}: same category on {agree} of {len(both)} turns both validly reviewed')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('run_file')
    b.add_argument('--compare', nargs='*', default=[])
    b.add_argument('--prompts', nargs='*', default=[])
    b.add_argument('--lost-only', action='store_true', help='only turns scoring below the first --compare run')
    b.add_argument('--bench', default=str(REPO_ROOT / 'journal/baseline/bench/v1'))
    r = sub.add_parser('review')
    r.add_argument('run_file')
    r.add_argument('--base-url', required=True)
    r.add_argument('--model', required=True)
    r.add_argument('--label', required=True, help='the reviewer name, e.g. gemma or flash-next')
    r.add_argument('--prompts', nargs='*', default=[])
    r.add_argument('--max-tokens', type=int, default=16384)
    r.add_argument('--thinking', action='store_true')
    s = sub.add_parser('summary')
    s.add_argument('run_file')
    args = ap.parse_args(argv)
    return {'build': cmd_build, 'review': cmd_review, 'summary': cmd_summary}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
