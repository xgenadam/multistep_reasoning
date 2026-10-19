"""Baseline scenarios for the harness (Phase 0 performance pass criteria).

Each scenario is a list of turns; each turn is a user prompt. `prior` names a
previous turn in the same scenario whose document snapshot is loaded as the
input Document for that turn (multi-turn continuation). `expect` encodes the
PASS CRITERIA from PLAN.md so a future `check` step can score runs against
them without human judgement.

Scenario map to plan criteria:
  s1_cli_code      -> P0-1 (code request lands as `file` parts, not prose)
  s2_report        -> P0-2 (report stays in sections; `section` parts)
  s3_followup      -> P0-3 (overlapping follow-up; dedupe quality via
                      max_dup_jaccard < 0.50 across part pairs, and the
                      follow-up keeps turn 0's parts: none dropped unless
                      merged into a surviving part)
  s4_anchors       -> P0-4 anchor set (total wall-clock + tokens, cheap
                      multi-sub-task prompt, pre-consolidation numbers)
"""

SCENARIOS: list[dict] = [
    {
        'id': 's1_cli_code',
        'title': 'Code deliverable: CLI tool (expect file parts)',
        'expect': {
            'criterion': 'P0-1',
            'part_kinds_include': ['file'],
            'file_parts_min': 1,
            'section_parts_max': 0,  # no prose-report parts about the tool
            'non_empty': True,
        },
        'turns': [
            {
                'name': 's1:t0',
                'text': (
                    'Write a small CLI tool in Python called "wordcount" that, '
                    'given one or more file paths, prints for each file: line '
                    'count, word count, and character count, in a simple table. '
                    'It should exit non-zero if a path does not exist. Provide '
                    'the code.'
                ),
            }
        ],
    },
    {
        'id': 's1b_csv2json_cli',
        'title': 'Code deliverable: CSV-to-JSON converter CLI (P0-1, X2 of 3)',
        'expect': {
            'criterion': 'P0-1',
            'part_kinds_include': ['file'],
            'file_parts_min': 1,
            'section_parts_max': 0,  # no prose-report parts about the tool
            'non_empty': True,
            'note': '0-05 verification: different tool than s1 (X2: conversion).',
        },
        'turns': [
            {
                'name': 's1b:t0',
                'text': (
                    'Write a small CLI tool in Python called "csv2json" that, '
                    'given a path to a CSV file, prints the rows as a JSON '
                    'array of objects (header row = keys) to stdout. Flag '
                    '"--indent" for pretty-printing. Exit non-zero if the '
                    'file is missing or empty. Provide the code.'
                ),
            }
        ],
    },
    {
        'id': 's1c_logscan_cli',
        'title': 'Code deliverable: log scanner CLI (P0-1, X3 of 3)',
        'expect': {
            'criterion': 'P0-1',
            'part_kinds_include': ['file'],
            'file_parts_min': 1,
            'section_parts_max': 0,  # no prose-report parts about the tool
            'non_empty': True,
            'note': '0-05 verification: different tool than s1 (X3: filtering).',
        },
        'turns': [
            {
                'name': 's1c:t0',
                'text': (
                    'Write a small CLI tool in Python called "logscan" that, '
                    'given a log file path and a level (INFO, WARN, ERROR), '
                    'prints only the matching log lines, newest last, with a '
                    'count on stderr. Flag "--limit N" caps the number '
                    'printed. Exit non-zero if the file does not exist. '
                    'Provide the code.'
                ),
            }
        ],
    },
    {
        'id': 's2_report',
        'title': 'Written deliverable: report (expect section parts)',
        'expect': {
            'criterion': 'P0-2',
            'part_kinds_include': ['section'],
            'section_parts_min': 2,
            'file_parts_max': 0,
            'non_empty': True,
        },
        'turns': [
            {
                'name': 's2:t0',
                'text': (
                    'Write a short internal report (about 300-500 words total) '
                    'on why a team of four engineers should adopt a '
                    'file-based ticketing system (markdown files in git) '
                    'instead of an external issue tracker. Cover: cost and '
                    'hosting, searchability, review culture, and one honest '
                    'drawback. Use clear section headings.'
                ),
            }
        ],
    },
    {
        'id': 's3_followup',
        'title': 'Multi-turn overlap: follow-up on the report (dedupe quality)',
        'expect': {
            'criterion': 'P0-3',
            'max_dup_jaccard_below': 0.50,
            # P0-3 (D-014): the follow-up edits the report (an artifact), so
            # it must keep turn 0's parts rather than rebuild them.
            'followup_keeps_parts': True,
            'non_empty': True,
            'note': 'turn 1 continues turn 0\'s document; duplicate part '
                    'pairs indicate the composer is re-emitting instead of '
                    'updating',
        },
        'turns': [
            {
                'name': 's3:t0',
                'text': (
                    'Write a one-page report (about 300 words) with clear '
                    'sections covering: what a file-based ticketing system is, '
                    'its main benefits, and its main drawbacks.'
                ),
            },
            {
                'prior': 's3:t0',
                'name': 's3:t1',
                'text': (
                    'Extend the report: add a section on how to migrate an '
                    'existing set of tickets from an external tracker to the '
                    'file-based system, including a concrete migration plan '
                    'with three steps. Keep the existing sections accurate '
                    'and do not repeat their content.'
                ),
            },
        ],
    },
    {
        'id': 's4_anchors',
        'title': 'P0-4 anchor: wall-clock + tokens, multi-sub-task prompt',
        'expect': {
            'criterion': 'P0-4',
            'note': 'anchor for total wall-clock and token totals; compare '
                    'pre- vs post-consolidation. Also exercises '
                    'decompose->execute->compose breadth (2 sub-tasks).',
            'min_sub_tasks': 2,
            'non_empty': True,
        },
        'turns': [
            {
                'name': 's4:t0',
                'text': (
                    'Plan a 7-day study schedule for learning the basics of '
                    'linear algebra (vectors, matrices, systems of equations). '
                    'Deliverable 1: a day-by-day schedule table. '
                    'Deliverable 2: a short checklist of 10 concepts that '
                    'must be solid before moving on to numerical linear '
                    'algebra.'
                ),
            }
        ],
    },
]