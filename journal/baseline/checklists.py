#!/usr/bin/env python3
"""Report checklists for bench v1 (Q-02 stage 0; design note § 1, P5).

Scores a report's text against `checklists/<id>.yaml` mechanically: no
model, no judgement. The judge scores what a checklist cannot (design
§ 3); a checklist result is reported beside the verdict, never pooled with
the code domain's test results (Q-8). Formats: bench/v1/README.md.

Usage (from the repo root):
  .venv/bin/python journal/baseline/checklists.py score RUN_FILE --bench journal/baseline/bench/v1
  .venv/bin/python journal/baseline/checklists.py check-bench --bench journal/baseline/bench/v1

`score` writes <run file stem>.checklists.json beside the run file. It
scores each report-domain result's `output.text`, which for the harness
arms is the rendered Document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

from hidden_tests import git_commit  # noqa: E402

CHECKS = ('word_count', 'heading', 'contains', 'not_contains', 'numbered_items',
          'bullet_items', 'table_rows', 'max_section_overlap', 'number')
_HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
_NUMBERED = re.compile(r'^ {0,3}\d+[.)]\s+\S')
_BULLET = re.compile(r'^ {0,3}[-*+]\s+\S')
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')


def lines_outside_fences(text: str) -> list[tuple[str, bool]]:
    """Each line with whether it sits inside a fenced code block."""
    out, fence = [], None
    for line in text.splitlines():
        m = _FENCE.match(line)
        if fence is None and m:
            fence = m.group(1)[0] * len(m.group(1))
            out.append((line, True))
        elif fence is not None:
            out.append((line, True))
            if line.strip().startswith(fence) and set(line.strip()) <= {fence[0]}:
                fence = None
        else:
            out.append((line, False))
    return out


def headings(text: str) -> list[tuple[int, str, int]]:
    """(level, title, line index) for each markdown heading outside code."""
    out = []
    for i, (line, fenced) in enumerate(lines_outside_fences(text)):
        m = None if fenced else _HEADING.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2), i))
    return out


def section(text: str, pattern: str | None) -> str | None:
    """The text under the first heading matching pattern, up to the next
    heading of the same or a higher level; the whole text when pattern is
    None; None when no heading matches."""
    if pattern is None:
        return text
    lines = text.splitlines()
    heads = headings(text)
    for n, (level, title, i) in enumerate(heads):
        if re.search(pattern, title):
            end = next((j for lv, _, j in heads[n + 1:] if lv <= level), len(lines))
            return '\n'.join(lines[i + 1:end])
    return None


def sections_by_heading(text: str) -> list[str]:
    """Bodies split at ## headings (a rendered Document's parts), or at the
    top level present when there are none; the units the overlap check
    compares."""
    heads = headings(text)
    if not heads:
        return [text]
    levels = {lv for lv, _, _ in heads}
    level = 2 if 2 in levels else min(levels)
    lines = text.splitlines()
    starts = [i for lv, _, i in heads if lv == level]
    return ['\n'.join(lines[a + 1:b]) for a, b in zip(starts, starts[1:] + [len(lines)])]


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def _jaccard_max(bodies: list[str]) -> float | None:
    sets = [{w for w in b.lower().split() if len(w) > 3} for b in bodies]
    best = None
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            union = sets[i] | sets[j]
            if union:
                v = len(sets[i] & sets[j]) / len(union)
                best = v if best is None else max(best, v)
    return best


def _count_lines(scope: str, pattern: re.Pattern) -> int:
    return sum(1 for line, fenced in lines_outside_fences(scope)
               if not fenced and pattern.match(line))


def _table_rows(scope: str) -> int | None:
    rows, in_table, seen_sep = 0, False, False
    for line, fenced in lines_outside_fences(scope):
        cell = line.strip()
        if not fenced and cell.startswith('|'):
            if not in_table:
                in_table = True
                continue  # header row
            if not seen_sep and re.fullmatch(r'\|?[\s:|-]+\|?', cell) and '-' in cell:
                seen_sep = True
                continue
            rows += 1
        elif in_table:
            break
    return rows if in_table and seen_sep else None


def _bounds(value: float | None, item: dict) -> bool:
    if value is None:
        return False
    if 'min' in item and value < item['min']:
        return False
    return not ('max' in item and value > item['max'])


def check_item(text: str, item: dict) -> dict:
    """One checklist item: passed and a detail value (what was measured)."""
    kind = item['check']
    scope = section(text, item.get('section'))
    if scope is None:
        return {'passed': False, 'detail': f'no section matching {item["section"]!r}'}
    if kind == 'word_count':
        n = len(_words(scope))
        return {'passed': _bounds(n, item), 'detail': n}
    if kind == 'heading':
        n = sum(1 for _, title, _ in headings(scope) if re.search(item['pattern'], title))
        return {'passed': _bounds(n, {'min': 1, **item}), 'detail': n}
    if kind in ('contains', 'not_contains'):
        n = len(re.findall(item['pattern'], scope))
        if kind == 'not_contains':
            return {'passed': n == 0, 'detail': n}
        return {'passed': _bounds(n, {'min': 1, **item}), 'detail': n}
    if kind in ('numbered_items', 'bullet_items'):
        n = _count_lines(scope, _NUMBERED if kind == 'numbered_items' else _BULLET)
        return {'passed': _bounds(n, {'min': 1, **item}), 'detail': n}
    if kind == 'table_rows':
        n = _table_rows(scope)
        return {'passed': _bounds(n, item), 'detail': n}
    if kind == 'max_section_overlap':
        v = _jaccard_max(sections_by_heading(scope))
        # Strictly below, as P0-3's max_dup_jaccard < 0.50; one section passes.
        return {'passed': v is None or v < item['max'],
                'detail': None if v is None else round(v, 3)}
    if kind == 'number':
        m = re.search(item['pattern'], scope)
        if m is None:
            return {'passed': False, 'detail': None}
        try:
            got = float(m.group(1).replace(',', ''))
        except (IndexError, ValueError):
            return {'passed': False, 'detail': m.group(0)}
        return {'passed': abs(got - item['value']) <= item.get('tol', 0), 'detail': got}
    raise ValueError(f'unknown check {kind!r}')


def validate(checklist: dict) -> list[str]:
    """Problems with a checklist file (unknown checks, bad regexes, missing keys)."""
    problems = []
    ids = [it.get('id') for it in checklist.get('items') or []]
    if not ids:
        problems.append('no items')
    if len(set(ids)) != len(ids):
        problems.append('duplicate item ids')
    for it in checklist.get('items') or []:
        kind = it.get('check')
        if kind not in CHECKS:
            problems.append(f'{it.get("id")}: unknown check {kind!r}')
            continue
        need = {'heading': ('pattern',), 'contains': ('pattern',),
                'not_contains': ('pattern',), 'max_section_overlap': ('max',),
                'number': ('pattern', 'value')}.get(kind, ())
        problems += [f'{it["id"]}: {kind} needs {k}' for k in need if k not in it]
        for key in ('pattern', 'section'):
            if key in it:
                try:
                    re.compile(it[key])
                except re.error as exc:
                    problems.append(f'{it["id"]}: bad {key} regex: {exc}')
    return problems


def score_text(text: str, checklist: dict) -> dict:
    items = [{'id': it['id'], 'check': it['check'], **check_item(text, it)}
             for it in checklist['items']]
    passed = sum(it['passed'] for it in items)
    return {'items': items, 'passed': passed, 'total': len(items),
            'score': round(passed / len(items), 4) if items else None}


def load_checklist(bench: Path, pid: str) -> dict:
    return yaml.safe_load((Path(bench) / 'checklists' / f'{pid}.yaml').read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def score_run(run_file: Path, bench: Path) -> dict:
    data = json.loads(Path(run_file).read_text())
    manifest = yaml.safe_load((Path(bench) / 'manifest.yaml').read_text())
    domains = {p['id']: p['domain'] for p in manifest['prompts']}
    rows, unknown = [], set()
    for r in data.get('results') or []:
        pid = r['prompt_id']
        if pid not in domains:
            unknown.add(pid)
            continue
        if domains[pid] != 'report':
            continue
        text = (r.get('output') or {}).get('text') or ''
        rows.append({'prompt_id': pid, 'arm': r['arm'], 'run': r['run'],
                     'run_error': r.get('error'),
                     **score_text(text, load_checklist(bench, pid))})
    return {'run_file': str(run_file), 'run_file_sha256': _sha(run_file),
            'bench': str(bench), 'manifest_sha256': _sha(Path(bench) / 'manifest.yaml'),
            **git_commit(),
            'scored_at': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
            'skipped_unknown_prompts': sorted(unknown), 'results': rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Report checklists (bench v1)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sc = sub.add_parser('score', help='score a run file\'s report results')
    sc.add_argument('run_file')
    sc.add_argument('--bench', required=True)
    cb = sub.add_parser('check-bench', help='validate every written report checklist')
    cb.add_argument('--bench', required=True)
    args = ap.parse_args(argv)
    bench = Path(args.bench)
    if args.cmd == 'score':
        payload = score_run(Path(args.run_file), bench)
        out = Path(args.run_file).with_suffix('.checklists.json')
        out.write_text(json.dumps(payload, indent=2))
        for r in payload['results']:
            print(f'{r["prompt_id"]:<6} {r["arm"]:<3} r{r["run"]}: {r["passed"]}/{r["total"]}'
                  + ''.join(f' -{it["id"]}' for it in r['items'] if not it['passed']))
        print(f'Wrote {out}')
        return 0
    manifest = yaml.safe_load((bench / 'manifest.yaml').read_text())
    failed = checked = 0
    for p in manifest['prompts']:
        if p['domain'] != 'report' or p.get('status') == 'draft':
            continue
        checked += 1
        path = bench / 'checklists' / f'{p["id"]}.yaml'
        problems = ['no checklist'] if not path.exists() else validate(
            yaml.safe_load(path.read_text()) or {})
        if not (bench / 'prompts' / f'{p["id"]}.md').exists():
            problems.append('no prompt file')
        failed += bool(problems)
        print(f'{p["id"]:<6} {"FAIL" if problems else "OK  "}  ' + '; '.join(problems))
    print(f'{checked - failed}/{checked} written report prompts OK')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
