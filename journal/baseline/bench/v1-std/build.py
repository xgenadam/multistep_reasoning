#!/usr/bin/env python3
"""Build bench v1-std (the standard slice for Q-E1) from the raw dataset files.

Usage (from the repo root; it never runs dataset code):
  .venv/bin/python -I journal/baseline/bench/v1-std/build.py [--raw DIR] [--all]

It reads the two JSONL files, applies the fixed selection rules (README.md
beside this file), and rewrites manifest.yaml, prompts/, tests/, reference/
and ifeval/ here. Titles and briefs are hand-written below; everything else
is taken verbatim from the rows. The tasks in EXCLUDED keep their sc id (ids
are numbered over the rule's selection) but get no files and no manifest
entry; README.md records why.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import shutil
import sys
import warnings
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_RAW = Path.home() / 'models' / 'bench-std-raw'
BCB_FILE = Path('BigCodeBench-Hard') / 'v0.1.4.jsonl'
IFEVAL_FILE = Path('IFEval') / 'ifeval_input_data.jsonl'

BANNED = frozenset({'subprocess', 'ftplib', 'socket', 'smtplib', 'urllib', 'http', 'ssl',
                    'ctypes', 'multiprocessing', 'threading', 'signal'})
REPORT_SEED, REPORT_COUNT, DEFAULT_TARGET_WORDS = 0, 20, 300

ADDED_PARAGRAPH = ('Put the code in a file `task.py`. Use only the Python 3.12 standard library. '
                   'Give each file in its own fenced code block, with the file\'s path on the '
                   'line just before the block.')

# task_id -> reason. Recorded in README.md § Exclusions.
EXCLUDED = {
    'BigCodeBench/287': 'test imports `faker` (third-party, not installed; installs are out of scope)',
    'BigCodeBench/313': 'test imports `faker` (third-party, not installed; installs are out of scope)',
    'BigCodeBench/826': 'test imports `faker` (third-party, not installed; installs are out of scope)',
}

CODE_TEXT = {  # task_id -> (title, brief)
    'BigCodeBench/19': ('Zip a directory\'s files',
                        'Zip the top-level files of a directory into files.zip and return its path; None when there are no files; FileNotFoundError when the directory is missing.'),
    'BigCodeBench/287': ('Word counts to JSON',
                         'Count the words in a directory\'s .txt files, write the per-word counts to a JSON file and return the total.'),
    'BigCodeBench/310': ('Simulated people CSV',
                         'Write a CSV of 100 simulated people (name, age, height, weight) followed by an average row; return the file\'s path.'),
    'BigCodeBench/313': ('Organise files by bracket prefix',
                         'Move each file into a subdirectory named after the text before its first [bracketed] part; return the directory and a map of the moves.'),
    'BigCodeBench/368': ('Move a random file',
                         'Move one seeded-random file from a source to a destination directory and return its name; FileNotFoundError when the source is empty.'),
    'BigCodeBench/454': ('Move files by extension',
                         'Move files with a given extension to a destination unless a same-named file is already there; return the moved paths; FileNotFoundError for a missing directory.'),
    'BigCodeBench/592': ('Sensor data CSV',
                         'Write `hours` rows of random sensor readings (Time, Temperature, Humidity, Pressure) to output_dir/sensor_data.csv and return its path.'),
    'BigCodeBench/594': ('Weather CSV with backup',
                         'Write `hours` rows of random weather conditions to a CSV, copy it into a backup/ subdirectory and return the CSV\'s path.'),
    'BigCodeBench/720': ('Append sensor row',
                         'Append a random temperature/humidity row to task_func_data/Output.txt, writing the header only once; return the path.'),
    'BigCodeBench/765': ('Copy non-None files',
                         'Copy each existing file whose dict value is not None into a target directory; return the copied paths.'),
    'BigCodeBench/771': ('Rename-copy CSVs by pattern',
                         'For each CSV named like `prefix-N.csv`, write its rows to `prefix.csv`; return the new file names.'),
    'BigCodeBench/777': ('Unzip by name pattern',
                         'Extract each zip named like `prefix-N.zip` into a `prefix` directory; return the extraction directories.'),
    'BigCodeBench/800': ('Goals and penalties counter',
                         'Total goals and penalties from a CSV (when it exists) plus the given per-team dicts; return a Counter.'),
    'BigCodeBench/826': ('Move files by regex',
                         'Move files whose names match a regex from a source to a target directory (created if absent); return the count moved.'),
    'BigCodeBench/854': ('Permutation factorial sums',
                         'Return every permutation of a list of non-negative ints and each permutation\'s sum of factorials; TypeError / ValueError on bad input.'),
    'BigCodeBench/857': ('Transfer files with warnings',
                         'Move files with the given extensions from a source to a destination, warning on each failure; return the moved file names.'),
    'BigCodeBench/906': ('Archive processed files',
                         'Zip and move every `*_processed` file from a source to a target directory; return the archive\'s path.'),
    'BigCodeBench/928': ('Two-letter combination counts',
                         'Count each two-letter lowercase combination in a word; return a dict over all 676 combinations, zero when absent.'),
    'BigCodeBench/963': ('Zip by extension, recursively',
                         'Zip every .txt/.docx/.xlsx/.csv file under a source directory into target/zip_name.zip and return its absolute path; OSError for a missing source.'),
    'BigCodeBench/971': ('Directory file details',
                         'List each top-level file\'s name, size and UTC ISO creation and modification times; ValueError when the path is not a directory.'),
    'BigCodeBench/988': ('Directory item predicates',
                         'Evaluate the named predicates (is_file, is_dir, has_special_chars, has_numbers) on each directory item; ValueError / FileNotFoundError on bad input.'),
}

REPORT_TEXT = {  # IFEval key -> (title, brief)
    2943: ('Darth Vader conversation', 'An angry conversation with Darth Vader in three ***-separated parts, all lowercase, "might" at least 6 times.'),
    3203: ('Canucks environment blog post', 'A blog post as Naomi telling the Canucks to mind their environments, ending with an exact sign-off phrase.'),
    334: ('Color Paper slogan', 'A slogan for a paper-towel company, wrapped in double quotes, with exactly two markdown bullets.'),
    2292: ('Pitch deck for moms', 'A casual pitch deck aimed at moms for a cancer-cure startup, using "clearly" at least twice.'),
    3710: ('Baby sleep rap', 'A rap for professionals on getting babies to sleep, with a <<title>>, two highlighted sections and a P.P.S.'),
    3565: ('What "jock" means', 'A two-part ***-separated answer on what "jock" means without using the word.'),
    3091: ('Quiz about bits', 'A quiz about bits that uses the word "elephant" at least three times.'),
    2482: ('Unusual-style rewrite', 'Repeat the request verbatim, then rewrite a biblical sentence in an unusual style.'),
    3513: ('Software engineer resume', 'A Bay Area software engineer resume with at least 20 all-capital words or phrases.'),
    2807: ('Ad for a witches\' lawyer', 'A weird all-lowercase ad for a copyright lawyer who represents witches, with a <<title>>.'),
    2035: ('Five-sentence joke', 'A joke of at least five sentences, two italicised sections, wrapped in double quotes.'),
    3680: ('Wilderness preservation essay', 'An essay on wilderness preservation using "knot" at least twice, with two italic sections.'),
    1551: ('Two cover letters', 'A concise and a long cover letter for a Google software engineer job, each with a <<title>>.'),
    2386: ('Expand two sentences', 'Expand two sentences about software localisation into exactly three ***-separated paragraphs using "humming".'),
    1561: ('Fashion company name', 'Repeat the request first, then name a new fashion company with a multi-meaning <<name>>.'),
    1259: ('Marathi haiku', 'A haiku about rushing to work, in Marathi only.'),
    2247: ('Alvin and the Chipmunks essay', 'An essay about Alvin and the Chipmunks in English, all capital letters.'),
    1593: ('Lowercase poem', 'An all-lowercase poem about a friend named Barnet.'),
    2532: ('Email about triggers', 'An email to a friend about what triggers you, wrapped in double quotation marks.'),
    1281: ('Limerick about Hannah', 'Repeat the request verbatim, then a limerick about an intern at a coffee company including "intern" and "grow".'),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def task_number(task_id: str) -> int:
    return int(task_id.split('/')[1])


def select_code(rows: list[dict]) -> list[dict]:
    """The std-code rule: every lib is stdlib and none is banned; task_id order."""
    chosen = []
    for row in rows:
        libs = ast.literal_eval(row['libs']) if isinstance(row['libs'], str) else row['libs']
        if all(lib in sys.stdlib_module_names for lib in libs) and not BANNED & set(libs):
            chosen.append(row)
    return sorted(chosen, key=lambda r: task_number(r['task_id']))


def select_report(rows: list[dict]) -> list[dict]:
    by_key = {row['key']: row for row in rows}
    return [by_key[k] for k in random.Random(REPORT_SEED).sample(sorted(by_key), REPORT_COUNT)]


def code_prompt_imports(code_prompt: str) -> list[str]:
    return [ln for ln in code_prompt.splitlines() if ln.startswith(('import ', 'from '))]


def test_file(row: dict) -> str:
    imports = '\n'.join(code_prompt_imports(row['code_prompt']))
    return f'''# Hidden tests for task.py: BigCodeBench-Hard v0.1.4 {row['task_id']}, the
# row's `test` field. Below the marker line it is unchanged.
#
# Adaptations (bench v1-std README, "Test adaptations"):
# 1. BigCodeBench executes the solution and this test code as one module,
#    solution first, so the tests use the solution's names (task_func, its
#    constants, the modules it imports) without importing them. Equivalent
#    here: the import lines of the task's `code_prompt` (the code the prompt
#    tells the model to start with), then `from task import *`.
# 2. Names that `from task import *` brings in and that pytest would collect
#    as tests (a test* function, a Test* class or a unittest.TestCase subclass
#    defined in task.py) are deleted, so a deliverable cannot add its own
#    tests to the count.
# 3. pytest (hidden_tests.py) runs the TestCases class; BigCodeBench runs it
#    with unittest. The test methods are the same.
{imports}
from task import *  # noqa: F401,F403
import unittest as _bcb_unittest

for _bcb_name, _bcb_value in list(globals().items()):
    if getattr(_bcb_value, '__module__', None) == 'task' and (
            _bcb_name.lower().startswith('test')
            or (isinstance(_bcb_value, type) and issubclass(_bcb_value, _bcb_unittest.TestCase))):
        del globals()[_bcb_name]

# ---- BigCodeBench test code (unchanged) ----
{row['test'].rstrip()}
'''


def reset(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--raw', type=Path, default=DEFAULT_RAW)
    ap.add_argument('--all', action='store_true',
                    help='write every selected task, ignoring EXCLUDED (to re-check the exclusions)')
    args = ap.parse_args(argv)
    excluded = {} if args.all else EXCLUDED
    bcb_path, ifeval_path = args.raw / BCB_FILE, args.raw / IFEVAL_FILE
    code = select_code(read_jsonl(bcb_path))
    report = select_report(read_jsonl(ifeval_path))
    for sub in ('prompts', 'tests', 'reference', 'ifeval'):
        reset(HERE / sub)
    entries = []
    for n, row in enumerate(code, 1):
        pid, tid = f'sc{n:02d}', row['task_id']
        if tid in excluded:
            print(f'{pid} {tid}: excluded ({excluded[tid]})')
            continue
        title, brief = CODE_TEXT[tid]
        prompt = row['instruct_prompt'].rstrip('\n') + '\n\n' + ADDED_PARAGRAPH + '\n'
        (HERE / 'prompts' / f'{pid}.md').write_text(prompt)
        (HERE / 'tests' / pid).mkdir()
        (HERE / 'tests' / pid / 'test_task.py').write_text(test_file(row))
        reference = row['code_prompt'] + row['canonical_solution']
        with warnings.catch_warnings():  # e.g. '\[' in a regex literal
            warnings.simplefilter('ignore', SyntaxWarning)
            ast.parse(reference)  # syntax only; nothing is executed
        (HERE / 'reference' / pid).mkdir()
        (HERE / 'reference' / pid / 'task.py').write_text(reference.rstrip('\n') + '\n')
        entries.append({'id': pid, 'domain': 'code', 'status': 'written', 'title': title,
                        'brief': brief, 'source': f'bigcodebench-hard v0.1.4 {tid}',
                        'files': ['task.py']})
    for n, row in enumerate(report, 1):
        pid, key = f'sr{n:02d}', row['key']
        title, brief = REPORT_TEXT[key]
        (HERE / 'prompts' / f'{pid}.md').write_text(row['prompt'])
        (HERE / 'ifeval' / f'{pid}.json').write_text(json.dumps(
            {'key': key, 'instruction_id_list': row['instruction_id_list'],
             'kwargs': row['kwargs']}, indent=2, ensure_ascii=False) + '\n')
        words = [kw['num_words'] for kw in row['kwargs'] if kw and kw.get('num_words')]
        entries.append({'id': pid, 'domain': 'report', 'status': 'written', 'title': title,
                        'brief': brief, 'source': f'ifeval {key}',
                        'target_words': words[0] if words else DEFAULT_TARGET_WORDS})
    header = (
        '# Bench v1-std manifest: the standard slice for Q-E1 (README.md beside this file).\n'
        '# Generated by build.py from the raw rows; do not hand-edit.\n'
        f'# Sources: {BCB_FILE} sha256 {sha256(bcb_path)}\n'
        f'#          {IFEVAL_FILE} sha256 {sha256(ifeval_path)}\n'
        '# Same schema as bench v1 (no follow-ups, no long or overlap flags, no subsets).\n')
    body = yaml.safe_dump({'version': 'v1-std', 'frozen': True, 'prompts': entries},
                          sort_keys=False, allow_unicode=True, width=1000)
    (HERE / 'manifest.yaml').write_text(header + body)
    counts = {d: sum(e['domain'] == d for e in entries) for d in ('code', 'report')}
    print(f'{len(code)} code tasks selected, {len(excluded)} excluded; '
          f'{counts["code"]} code and {counts["report"]} report entries written')
    return 0


if __name__ == '__main__':
    sys.exit(main())
