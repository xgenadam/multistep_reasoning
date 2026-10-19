#!/usr/bin/env python3
"""Ticket board: print every ticket's front-matter as a table, then lint.

Stdlib only, so it runs without the venv. `make board` calls it.

    python journal/board.py           # every ticket
    python journal/board.py --open    # only tickets not done/dropped

Lint (exit 1 on any finding):
- an open ticket lacks criteria / model / effort / needs_server / depends_on
  (criterion O-6), or has an unknown status / needs_server value;
- a depends_on entry names no existing ticket;
- a D-nnn cited in a tracked file is not defined in journal/DECISIONS.md
  (criterion O-4).
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / 'journal' / 'tickets'
DECISIONS = ROOT / 'journal' / 'DECISIONS.md'

PHASE_ORDER = ['O', '0', 'Q', 'A', 'V', 'R', 'B', 'T', 'P', 'C', 'H']
STATUSES = ['in_progress', 'blocked', 'open', 'done', 'dropped']
CLOSED = {'done', 'dropped'}
SERVER_VALUES = {'none', 'behavioural', 'timing'}
REQUIRED_OPEN = ['criteria', 'model', 'effort', 'needs_server', 'depends_on']
LIST_FIELDS = {'criteria', 'depends_on', 'supersedes', 'runs'}
DECISION_RE = re.compile(r'\bD-\d{3}\b')


def split_list(raw):
    """Split `[a, b (x, y), c]` on top-level commas."""
    inner = raw.strip()
    if inner.startswith('[') and inner.endswith(']'):
        inner = inner[1:-1]
    items, depth, cur = [], 0, ''
    for ch in inner:
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == ',' and depth == 0:
            items.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        items.append(cur.strip())
    return items


def read_front_matter(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    if not lines or lines[0].strip() != '---':
        return None
    meta = {}
    for line in lines[1:]:
        if line.strip() == '---':
            break
        key, sep, value = line.partition(':')
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        meta[key] = split_list(value) if key in LIST_FIELDS else value
    return meta


def sort_key(meta):
    ticket_id = meta.get('id', '')
    phase = ticket_id.split('-', 1)[0]
    rank = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else len(PHASE_ORDER)
    return (rank, ticket_id)


def load_tickets():
    tickets = []
    for path in sorted(TICKETS.glob('*.md')):
        if path.name == 'README.md':
            continue
        meta = read_front_matter(path)
        if meta is None:
            meta = {'id': path.stem, 'status': '?', 'title': '(no front-matter)'}
        meta['_path'] = path
        tickets.append(meta)
    return sorted(tickets, key=sort_key)


def fmt_list(items):
    return ', '.join(items) if items else '-'


def print_table(tickets):
    headers = ['id', 'status', 'model / effort', 'server', 'depends_on', 'criteria', 'title']
    rows = []
    for t in tickets:
        model = t.get('model', '')
        effort = t.get('effort', '')
        rows.append([
            t.get('id', ''),
            t.get('status', ''),
            f'{model} / {effort}' if model or effort else '-',
            t.get('needs_server', '') or '-',
            fmt_list(t.get('depends_on', [])),
            fmt_list(t.get('criteria', [])),
            t.get('title', '')[:60],
        ])
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    print('  '.join(h.ljust(w) for h, w in zip(headers, widths)).rstrip())
    print('  '.join('-' * w for w in widths))
    for r in rows:
        print('  '.join(c.ljust(w) for c, w in zip(r, widths)).rstrip())


def lint_tickets(tickets):
    findings = []
    ids = {t.get('id') for t in tickets}
    for t in tickets:
        tid = t.get('id', t['_path'].stem)
        status = t.get('status', '')
        if status not in STATUSES:
            findings.append(f'{tid}: unknown status {status!r}')
        if status in CLOSED:
            continue
        for field in REQUIRED_OPEN:
            if field not in t:
                findings.append(f'{tid}: missing {field}')
            elif field != 'depends_on' and not t[field]:
                findings.append(f'{tid}: empty {field}')
        server = t.get('needs_server')
        if server and server not in SERVER_VALUES:
            findings.append(f'{tid}: needs_server {server!r} not in {sorted(SERVER_VALUES)}')
        for dep in t.get('depends_on', []):
            if dep not in ids:
                findings.append(f'{tid}: depends_on {dep} is not a ticket')
    return findings


def tracked_text_files():
    try:
        out = subprocess.run(['git', 'ls-files'], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout
        paths = [ROOT / p for p in out.splitlines()]
    except (OSError, subprocess.CalledProcessError):
        paths = [ROOT / 'AGENTS.md', *(ROOT / 'journal').rglob('*.md')]
    return [p for p in paths if p.suffix in {'.md', '.py', '.yaml', '.toml', ''} and p.is_file()]


def lint_decisions():
    if not DECISIONS.exists():
        return ['journal/DECISIONS.md is missing']
    defined = set(re.findall(r'^## (D-\d{3}) ', DECISIONS.read_text(encoding='utf-8'), re.M))
    findings = []
    for path in tracked_text_files():
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for ref in DECISION_RE.findall(line):
                if ref not in defined:
                    findings.append(f'{path.relative_to(ROOT)}:{lineno}: {ref} not in DECISIONS.md')
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--open', action='store_true', help='hide done/dropped tickets')
    args = parser.parse_args()

    tickets = load_tickets()
    shown = [t for t in tickets if not (args.open and t.get('status') in CLOSED)]
    print_table(shown)

    findings = lint_tickets(tickets) + lint_decisions()
    if findings:
        print(f'\nlint: {len(findings)} finding(s)')
        for f in findings:
            print(f'  {f}')
        return 1
    print(f'\nlint: ok ({len(tickets)} tickets)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
