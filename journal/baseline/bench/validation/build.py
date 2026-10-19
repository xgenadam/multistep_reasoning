#!/usr/bin/env python3
"""Cut the Q-1 validation set (Q-01 design note § 4) from the 0-16 run file.

Writes candidates/<pair>_<side>.md and pairs.yaml beside this file. Real
pairs (R1-R5) are run 0 (a) against run 1 (b), with `expected` left empty
until the user's labelling app fills it. Damaged (W1-W5) and padded (L1-L2)
pairs are the original (a) against an edited copy (b); every edit is an
exact string replacement on the snapshot, so a miss fails loudly.

Usage (from the repo root): .venv/bin/python journal/baseline/bench/validation/build.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parents[1]
RUN_FILE = ('20261019T051008Z_rebaseline-0-16_s1_cli_code-s1b_csv2json_cli-'
            's1c_logscan_cli-s2_report-s3_followup-s4_anchors.json')

_spec = importlib.util.spec_from_file_location('quality', BASELINE / 'quality.py')
quality = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(quality)

FOLLOWUP_TASK = (
    'This is a follow-up turn on an existing document.\n\n'
    'The original request was:\n{prior}\n\n'
    'The follow-up request is:\n{text}\n\n'
    'Each response is the whole document after the follow-up.'
)

REAL = [
    ('R1', 's1_cli_code', 0, 'one file part against four: shape differs'),
    ('R2', 's1b_csv2json_cli', 0, 'same tool, two different sizes'),
    ('R3', 's2_report', 0, 'three sections against one'),
    ('R4', 's3_followup', 1, 'the follow-up with its prior; two against four parts'),
    ('R5', 's4_anchors', 0, 'two deliverables; four parts against two'),
]

S2_DRAWBACK = (
    '## Drawback\n\nThe most significant limitation of a file-based ticketing system is its '
    'lack of accessibility for non-developers.'
)
S3_BENEFITS = (
    'The most significant advantage of this approach is its architectural simplicity. By '
    'eliminating the need for a dedicated database server, installation and maintenance overhead '
    'is drastically reduced. This makes the system ideal for small teams, embedded environments, '
    'or projects requiring minimal dependency management. Furthermore, data portability and '
    'backup are exceptionally straightforward; a ticketing system can be backed up or migrated '
    'simply by copying directories or creating a zip archive. Version control systems like Git '
    'can also integrate seamlessly, allowing ticket history to be tracked alongside code changes. '
    'This transparency and ease of access foster a developer-friendly environment where '
    'troubleshooting tickets directly in the file structure is intuitive.'
)
S3_MIGRATION_INTRO_END = 'three-step process: Extraction, Mapping, and Import/Validation.'

L1_PADDING = """Before closing, it is worth stepping back to consider the broader picture that the sections above describe. Cost and hosting matter: as noted, a file-based system removes per-seat subscription fees and runs on the Git hosting the team already uses, so there is no separate database or web application to maintain. This keeps the toolchain small and the budget predictable for a team of four.

Searchability is the second consideration. Because every ticket is plain text in the repository, the team can find anything with the tools it already knows, such as grep, ripgrep or an IDE's project search, without learning a separate search interface. In practice this means old discussions are as easy to find as old code.

Review culture is the third. Tickets that live in Git can be changed through pull requests, linked from commits and reviewed like code, which keeps the reasoning behind a change next to the change itself. Reviewers see the history of a decision rather than scattered comments in another tool.

Finally, the drawback deserves restating: people who do not use Git day to day will find a file-based tracker harder to use than a graphical one, and dashboards such as burndown charts need extra work. Weighing these considerations together, the team should keep all four in mind when deciding."""

L2_PADDING = """This section explains how the logscan tool works, step by step.

First, the tool parses its command-line arguments with argparse. It takes a log file path and a level, which must be one of INFO, WARN or ERROR, and an optional --limit flag that caps how many lines are printed.

Next, it checks that the log file exists. If the path does not exist, it prints an error message to stderr and exits with status 1, so the exit code is non-zero as requested.

Then it reads the file line by line and keeps every line that contains the requested level, stripping the trailing newline from each one.

After that, it sorts the matching lines by timestamp so that the newest lines come last. A helper function, parse_timestamp, tries two common timestamp formats at the start of each line. Lines without a recognisable timestamp are treated as the oldest, and the original order is kept for ties.

If --limit is given, the tool keeps only the first N lines of the sorted list.

Finally, it prints the selected lines to stdout and prints the count of printed lines to stderr. Together these steps provide a simple and reliable way to scan a log file for a given level."""


def edit(snapshot: dict, part_title: str | None, old: str, new: str, *, index: int = 0) -> None:
    """Replace `old` once in the index-th part titled `part_title`."""
    parts = [p for p in snapshot['parts'] if p['title'] == part_title]
    body = parts[index]['body']
    if body.count(old) != 1:
        raise ValueError(f'{part_title!r}: {old[:40]!r} occurs {body.count(old)} times')
    parts[index]['body'] = body.replace(old, new)


def damaged(R: dict) -> list[tuple[str, str, int, int, dict, str]]:
    """(pair, scenario, run, turn, edited snapshot, description)."""
    out = []

    s = copy.deepcopy(R[('s2_report', 0)]['turns'][0]['snapshot'])
    part = next(p for p in s['parts'] if p['title'] == 'Drawback and Conclusion')
    start = part['body'].index(S2_DRAWBACK)
    end = part['body'].index('## Conclusion')
    part['body'] = part['body'][:start] + part['body'][end:]
    edit(s, 'Drawback and Conclusion', ' However, we must be honest about the trade-off: this '
         'approach assumes all relevant parties are developers comfortable with Git. If we '
         'anticipate needing significant input from non-technical stakeholders or require robust '
         'reporting dashboards immediately, the friction introduced by Markdown and Git workflows '
         'may outweigh the benefits.', '')
    part['title'] = 'Conclusion'
    out.append(('W1', 's2_report', 0, 0, s, 'the "one honest drawback" section removed '
                '(and the conclusion\'s trade-off sentences, which restated it)'))

    s = copy.deepcopy(R[('s1_cli_code', 0)]['turns'][0]['snapshot'])
    edit(s, 'wordcount.py', 'lines = len(content.splitlines())',
         'lines = len(content.splitlines()) - 1')
    out.append(('W2', 's1_cli_code', 0, 0, s, 'line count off by one (len(lines) - 1)'))

    s = copy.deepcopy(R[('s1b_csv2json_cli', 0)]['turns'][0]['snapshot'])
    n = 0
    for p in s['parts']:
        n += p['body'].count('json.dumps(data, indent=indent)')
        p['body'] = p['body'].replace('json.dumps(data, indent=indent)', 'json.dumps(data)')
    assert n == 3, n
    out.append(('W3', 's1b_csv2json_cli', 0, 0, s,
                '--indent parsed but ignored: json.dumps(data) in all three code copies'))

    s = copy.deepcopy(R[('s3_followup', 0)]['turns'][1]['snapshot'])
    edit(s, 'Migrating Existing Tickets', S3_MIGRATION_INTRO_END,
         S3_MIGRATION_INTRO_END + '\n\n### Why Migrate\n' + S3_BENEFITS)
    out.append(('W4', 's3_followup', 0, 1, s, 'the migration section repeats the benefits '
                'section verbatim ("do not repeat" broken)'))

    s = copy.deepcopy(R[('s4_anchors', 0)]['turns'][0]['snapshot'])
    for title in ('7-Day Curriculum Outline', '7-Day Study Schedule'):
        part = next(p for p in s['parts'] if p['title'] == title)
        lines = part['body'].split('\n')
        day7 = [ln for ln in lines if ln.startswith('| **7** |')]
        assert len(day7) == 1, (title, day7)
        part['body'] = '\n'.join(ln for ln in lines if ln not in day7)
    out.append(('W5', 's4_anchors', 0, 0, s, 'day 7 removed from both seven-day tables'))
    return out


def padded(R: dict) -> list[tuple[str, str, int, int, dict, str]]:
    out = []
    s = copy.deepcopy(R[('s2_report', 0)]['turns'][0]['snapshot'])
    s['parts'].insert(len(s['parts']) - 1, {
        'id': 'pad', 'kind': 'section', 'title': 'Further Considerations',
        'body': L1_PADDING, 'origin_task': None})
    out.append(('L1', 's2_report', 0, 0, s,
                'a "Further Considerations" section restating the earlier sections'))

    s = copy.deepcopy(R[('s1c_logscan_cli', 0)]['turns'][0]['snapshot'])
    s['parts'].append({'id': 'pad', 'kind': 'section', 'title': 'How It Works',
                       'body': L2_PADDING, 'origin_task': None})
    out.append(('L2', 's1c_logscan_cli', 0, 0, s,
                'a prose "How It Works" restatement of the code appended as a second part'))
    return out


def task_for(R: dict, scenario: str, turn: int) -> str:
    turns = R[(scenario, 0)]['turns']
    if turn == 0:
        return turns[0]['text']
    return FOLLOWUP_TASK.format(prior=turns[turn - 1]['text'], text=turns[turn]['text'])


def main() -> None:
    run = json.loads((BASELINE / 'runs' / RUN_FILE).read_text())
    R = {(r['scenario'], r['run']): r for r in run['results']}
    cand = HERE / 'candidates'
    cand.mkdir(exist_ok=True)
    pairs = []

    def write(name: str, text: str) -> str:
        (cand / name).write_text(text + '\n')
        return f'candidates/{name}'

    for pid, scenario, turn, why in REAL:
        a = write(f'{pid}_a.md', quality.render_snapshot(R[(scenario, 0)]['turns'][turn]['snapshot']))
        b = write(f'{pid}_b.md', quality.render_snapshot(R[(scenario, 1)]['turns'][turn]['snapshot']))
        pairs.append({'pair_id': pid, 'kind': 'real', 'task': task_for(R, scenario, turn),
                      'a': a, 'b': b, 'expected': None,
                      'source': f'{RUN_FILE} {scenario} t{turn}: run 0 (a) vs run 1 (b); {why}'})

    for kind, rows in (('damaged', damaged(R)), ('padded', padded(R))):
        for pid, scenario, rnum, turn, snap, why in rows:
            original = R[(scenario, rnum)]['turns'][turn]['snapshot']
            a = write(f'{pid}_a.md', quality.render_snapshot(original))
            b = write(f'{pid}_b.md', quality.render_snapshot(snap))
            pairs.append({'pair_id': pid, 'kind': kind, 'task': task_for(R, scenario, turn),
                          'a': a, 'b': b, 'expected': 'a',
                          'source': f'{RUN_FILE} {scenario} r{rnum} t{turn}: original (a) vs '
                                    f'edited (b): {why}'})

    manifest = {
        'version': 'validation_v1',
        'note': ('Q-1 validation set (journal/design/Q-01-judge.md § 4), written by build.py. '
                 'expected: a, b, tie, or empty until labelled. Padded pairs pass when the '
                 'padded side (b) is not preferred in either order.'),
        'pairs': pairs,
    }
    (HERE / 'pairs.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False, width=100,
                                                    allow_unicode=True))
    for p in pairs:
        sizes = [len((HERE / p[s]).read_text()) for s in ('a', 'b')]
        print(f'{p["pair_id"]:<3} {p["kind"]:<8} a={sizes[0]:>6} b={sizes[1]:>6} '
              f'({sizes[1] / sizes[0] - 1:+.0%})')


if __name__ == '__main__':
    main()
