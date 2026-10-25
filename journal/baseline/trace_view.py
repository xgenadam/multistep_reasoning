"""Trace viewer for harness runs (the user, 2026-10-25: follow a turn through the
harness and see where it broke).

Builds a static page from one arms.py run file, its intermediates and its
hidden-test scores, optionally beside other run files (a, a1, ...) on the same
prompts:

    .venv/bin/python journal/baseline/trace_view.py RUN.json [--compare A.json ...] [--out DIR]

DIR (default runs/trace-view/<run stem>, git-ignored) gets index.html plus one
data/<turn>.js per turn, loaded on demand so a large run opens from file://.

Per turn the page shows, top to bottom: the request; the plan (sub-tasks, the
decomposition prompt, the critique); each step's executor calls and result, its
composer attempts (accepted, rejected and why, fallback) and the Document parts
it added, changed or removed (with a diff); the final extraction and the hidden
tests that failed; and each compared arm's answer and score. Problems are marked
and listed at the top of the turn.

What it can show depends on the run. Runs from before --trace-calls have the
plan and the Document after each step only: no sub-task results, no composer
attempts and no call text. A run made with `arms.py run --trace-calls` has all of it.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEXT_CAP = 400_000  # characters per message or reply kept in the page


def load_json(path: Path):
    return json.loads(path.read_text())


def tests_for(run_file: Path) -> dict:
    """(prompt_id, arm, run) -> the hidden-test result, from RUN.tests.json if it exists."""
    path = run_file.with_name(run_file.stem + '.tests.json')
    if not path.exists():
        return {}
    return {(r['prompt_id'], r['arm'], r['run']): r for r in load_json(path).get('results', [])}


def score(test: dict | None) -> dict | None:
    if not test:
        return None
    t = test.get('tests') or {}
    ex = test.get('extraction') or {}
    total = t.get('total') or 0
    return {'passed': t.get('passed', 0), 'total': total,
            'rate': (t.get('passed', 0) / total) if total else 0.0,
            'extraction_ok': bool(test.get('extraction_ok')),
            'missing': ex.get('missing') or [], 'unclosed_fence': bool(ex.get('unclosed_fence')),
            'timed_out': bool(t.get('timed_out')), 'run_error': test.get('run_error')}


def cap(text) -> str:
    text = text if isinstance(text, str) else json.dumps(text, indent=1, default=str)
    return text if len(text) <= TEXT_CAP else text[:TEXT_CAP] + f'\n… [{len(text) - TEXT_CAP} more characters cut]'


def message_text(message: dict) -> str:
    content = message.get('content')
    if isinstance(content, list):  # content parts
        return '\n'.join(p.get('text', '') if isinstance(p, dict) else str(p) for p in content)
    return content or ''


def parts_diff(before: list[dict], after: list[dict]) -> list[dict]:
    """Each part of `after` (and each removed one) as added / changed / same / removed."""
    old = {p['id']: p for p in before}
    new_ids = {p['id'] for p in after}
    rows = []
    for p in after:
        prev = old.get(p['id'])
        row = {'id': p['id'], 'kind': p.get('kind'), 'title': p.get('title'),
               'origin_task': p.get('origin_task'), 'body': cap(p.get('body') or '')}
        if prev is None:
            row['change'] = 'added'
        elif (prev.get('body'), prev.get('title'), prev.get('kind')) != (p.get('body'), p.get('title'), p.get('kind')):
            row['change'] = 'changed'
            row['diff'] = cap(''.join(difflib.unified_diff(
                (prev.get('body') or '').splitlines(True), (p.get('body') or '').splitlines(True),
                'before', 'after', n=2)))
        else:
            row['change'] = 'same'
        rows.append(row)
    rows += [{'id': pid, 'kind': p.get('kind'), 'title': p.get('title'), 'change': 'removed',
              'body': cap(p.get('body') or '')} for pid, p in old.items() if pid not in new_ids]
    return rows


def step_number(name: str) -> tuple:
    m = re.match(r'(\d+)_([a-z_]+?)(?:_(\d+|consolidation))?\.json$', name)
    return (int(m.group(1)), m.group(2), m.group(3)) if m else (0, name, None)


def phase_step(phase: str | None) -> str | None:
    """'Executing 2/4: x' -> '2'; 'Decomposing…' -> 'plan'; consolidation -> 'consolidation'."""
    if not phase:
        return None
    if phase.startswith('Decompos'):
        return 'plan'
    if 'consolidat' in phase.lower():
        return 'consolidation'
    m = re.search(r'(\d+)/\d+:', phase)
    return m.group(1) if m else None


def build_turn(result: dict, inter_dir: Path | None, test: dict | None, prompt_text: str,
               compare: dict[str, tuple[dict | None, dict | None]]) -> dict:
    steps, plan, prev_parts = [], None, []
    if inter_dir is not None and inter_dir.is_dir():
        for f in sorted(inter_dir.glob('*.json'), key=lambda f: step_number(f.name)):
            data = load_json(f)
            kind = data.get('kind')
            if kind == 'plan':
                hist = data.get('decomposition_history') or {}
                plan = {'sub_tasks': data.get('sub_tasks') or [],
                        'decomposition_prompt': cap(hist.get('decomposition_prompt') or ''),
                        'critique': cap(hist.get('critique') or ''),
                        'regeneration_needed': hist.get('regeneration_needed'),
                        'initial_count': hist.get('initial_decomposition_count')}
                continue
            parts = (data.get('snapshot') or {}).get('parts') or []
            steps.append({
                'kind': kind, 'step': data.get('step'), 'of': data.get('of'),
                'sub_task': data.get('sub_task'), 'status': data.get('status'),
                'error': data.get('error'),
                'result': cap(data['result']) if 'result' in data else None,
                'compose_attempts': [
                    {**a, 'ops': [{k: (cap(v) if k == 'body' else v) for k, v in op.items()}
                                  for op in a.get('ops') or []]}
                    for a in data['compose_attempts']] if 'compose_attempts' in data else None,
                'summary': (data.get('snapshot') or {}).get('summary'),
                'parts': parts_diff(prev_parts, parts)})
            prev_parts = parts
    calls = []
    if inter_dir is not None and (inter_dir / 'calls').is_dir():
        for f in sorted((inter_dir / 'calls').glob('*.json')):
            c = load_json(f)
            rec = c.get('record') or {}
            params = c.get('params') or {}
            rf = params.get('response_format')
            calls.append({
                'index': rec.get('index'), 'kind': rec.get('kind'), 'phase': rec.get('phase'),
                'step': phase_step(rec.get('phase')), 'label': rec.get('step'),
                'prompt_tokens': rec.get('prompt_tokens'), 'completion_tokens': rec.get('completion_tokens'),
                'finish_reason': rec.get('finish_reason'), 'error': rec.get('error'),
                'seconds': rec.get('seconds'), 'thinking': rec.get('thinking'),
                'max_tokens': params.get('max_tokens'),
                'response_format': (rf.get('type') if isinstance(rf, dict) else rf),
                'schema': cap(rf) if isinstance(rf, dict) and rf.get('type') == 'json_schema' else None,
                'messages': [{'role': m.get('role'), 'text': cap(message_text(m))}
                             for m in c.get('messages') or [] if isinstance(m, dict)],
                'content': cap(c.get('content') or ''), 'reasoning': cap(c.get('reasoning') or '')})
    output = result.get('output') or {}
    return {
        'prompt_id': result['prompt_id'], 'arm': result['arm'], 'run': result['run'],
        'error': result.get('error'), 'prompt': cap(prompt_text), 'plan': plan, 'steps': steps,
        'calls': calls, 'traced': bool(calls),
        'output': cap(output.get('text') or ''),
        'test': None if not test else {
            'score': score(test), 'extraction': test.get('extraction'),
            'outcomes': (test.get('tests') or {}).get('outcomes') or {},
            'output_tail': cap((test.get('tests') or {}).get('output_tail') or '')},
        'compare': {label: {'score': score(t), 'output': cap(((r or {}).get('output') or {}).get('text') or ''),
                            'error': (r or {}).get('error')}
                    for label, (r, t) in compare.items()},
    }


def problems(turn: dict) -> list[dict]:
    """What went wrong, in pipeline order; `anchor` names the step section."""
    out = []
    for s in turn['steps']:
        anchor = f"step-{s['step']}"
        if s['kind'] == 'compose_failed':
            out.append({'anchor': anchor, 'what': f"composer gave up at step {s['step']}: {s.get('error')}"})
        if s.get('status') and 'FAILED' in str(s['status']).upper():
            out.append({'anchor': anchor, 'what': f"sub-task {s['step']} failed"})
        for a in s.get('compose_attempts') or []:
            if a.get('attempt') == 'fallback':
                out.append({'anchor': anchor, 'what': f"step {s['step']}: fallback (result added verbatim) after: {a.get('fallback_after')}"})
            elif a.get('error'):
                out.append({'anchor': anchor, 'what': f"step {s['step']} attempt {a.get('attempt')} rejected: {a['error']}"})
    for c in turn['calls']:
        if c.get('error') or c.get('finish_reason') == 'length':
            out.append({'anchor': f"call-{c['index']}",
                        'what': f"call {c['index']} ({c['kind']}): {c.get('error') or 'hit max_tokens'}"})
    if turn['error']:
        out.append({'anchor': 'final', 'what': f"turn error: {turn['error']}"})
    t = turn.get('test')
    if t:
        sc = t['score']
        if not sc['extraction_ok'] or sc['missing'] or sc['unclosed_fence']:
            out.append({'anchor': 'final', 'what': 'scorer could not fully extract the files'
                        + (f" (missing {', '.join(sc['missing'])})" if sc['missing'] else '')})
        if sc['total'] and sc['passed'] < sc['total']:
            out.append({'anchor': 'final', 'what': f"{sc['total'] - sc['passed']} of {sc['total']} hidden tests failed"})
    return out


def turn_slug(result: dict) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', f"{result['arm']}_{result['prompt_id']}_r{result['run']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run_file')
    ap.add_argument('--compare', nargs='*', default=[], help='other run files on the same prompts (a, a1, ...)')
    ap.add_argument('--bench', default=str(REPO_ROOT / 'journal/baseline/bench/v1'))
    ap.add_argument('--out', default=None)
    args = ap.parse_args(argv)

    run_file = Path(args.run_file).resolve()
    run = load_json(run_file)
    tests = tests_for(run_file)
    bench = Path(args.bench)
    titles = {}
    manifest = bench / 'manifest.yaml'
    if manifest.exists():
        import yaml
        titles = {p['id']: p.get('title', '') for p in yaml.safe_load(manifest.read_text()).get('prompts', [])}
    compares = []
    for f in args.compare:
        path = Path(f).resolve()
        data = load_json(path)
        label = data.get('label') or path.stem
        arms = sorted({r['arm'] for r in data['results']})
        compares.append((label, path, {(r['prompt_id'], r['run']): r for r in data['results']},
                         tests_for(path), arms))

    out = Path(args.out) if args.out else REPO_ROOT / 'runs' / 'trace-view' / run_file.stem
    (out / 'data').mkdir(parents=True, exist_ok=True)
    index = []
    for result in run['results']:
        pid = result['prompt_id']
        inter = (result.get('intermediates') or {}).get('dir')
        inter_dir = Path(inter) if inter else None
        if inter_dir is not None and not inter_dir.is_absolute():
            inter_dir = REPO_ROOT / inter_dir
        prompt_file = bench / 'prompts' / f'{pid}.md'
        prompt_text = prompt_file.read_text() if prompt_file.exists() else ''
        compare = {}
        for label, _, by_key, ctests, carms in compares:
            r = by_key.get((pid, result['run'])) or by_key.get((pid, 0))
            arm = r['arm'] if r else (carms[0] if carms else '')
            compare[label] = (r, ctests.get((pid, arm, r['run'] if r else 0)))
        test = tests.get((pid, result['arm'], result['run']))
        turn = build_turn(result, inter_dir, test, prompt_text, compare)
        turn['problems'] = problems(turn)
        slug = turn_slug(result)
        (out / 'data' / f'{slug}.js').write_text(
            'window.__turn(' + json.dumps(slug) + ',' + json.dumps(turn).replace('</', '<\\/') + ');\n')
        attempts = [a for s in turn['steps'] for a in (s.get('compose_attempts') or [])]
        index.append({
            'slug': slug, 'prompt_id': pid, 'title': titles.get(pid, ''), 'stratum': result.get('stratum'),
            'arm': result['arm'], 'run': result['run'], 'error': bool(result.get('error')),
            'score': score(test),
            'compare': {label: (c['score'] or {}).get('rate') if c['score'] else None
                        for label, c in turn['compare'].items()},
            'steps': len([s for s in turn['steps'] if isinstance(s.get('step'), int)]),
            'rejected': sum(1 for a in attempts if a.get('error') and a.get('attempt') != 'fallback'),
            'fallbacks': sum(1 for a in attempts if a.get('attempt') == 'fallback'),
            'traced': turn['traced'], 'problems': len(turn['problems'])})
    meta = {'run_file': str(run_file.relative_to(REPO_ROOT)) if run_file.is_relative_to(REPO_ROOT) else str(run_file),
            'label': run.get('label'), 'generator': run.get('generator'), 'model': run.get('model'),
            'commit': run.get('commit'), 'overrides': run.get('overrides') or [],
            'max_tokens': run.get('max_tokens'), 'trace_calls': run.get('trace_calls', False),
            'compare': [c[0] for c in compares]}
    page = (Path(__file__).with_name('trace_view.html').read_text()
            .replace('/*__INDEX__*/null', json.dumps({'meta': meta, 'turns': index}).replace('</', '<\\/')))
    (out / 'index.html').write_text(page)
    print(f'wrote {out / "index.html"} ({len(index)} turns'
          f'{", with call text" if any(t["traced"] for t in index) else ", no call text (run without --trace-calls)"})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
