"""Bench v1-std, the standard slice (journal/baseline/bench/v1-std/README.md).

The slice's data and the IFEval checker are not in the repo: `make venv-ifeval
bench-std` fetches and builds them. The tests that read them skip when they
are absent; data.lock is checked whenever any of them is present.
"""

import hashlib
import importlib.util
import json
import re
from collections import Counter

import pytest

from tests.test_baseline.conftest import BASELINE, load_baseline_module

BENCH = BASELINE / 'bench' / 'v1-std'
_spec = importlib.util.spec_from_file_location('bench_v1_std_fetch', BENCH / 'fetch.py')
fetch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch)

DATA_DIRS = ('prompts', 'tests', 'reference', 'ifeval')
HAVE_DATA = all((BENCH / d).is_dir() for d in DATA_DIRS)
needs_data = pytest.mark.skipif(
    not HAVE_DATA, reason='bench v1-std data not fetched (make venv-ifeval bench-std)')
CHECKER_UTIL = BENCH / fetch.CHECKER_DIR / 'instructions_util.py'
ADDED_PARAGRAPH = ('Put the code in a file `task.py`. Use only the Python 3.12 standard library. '
                   'Give each file in its own fenced code block, with the file\'s path on the '
                   'line just before the block.')


@pytest.fixture(scope='module')
def bench():
    if not HAVE_DATA:
        pytest.skip('bench v1-std data not fetched (make venv-ifeval bench-std)')
    return load_baseline_module('arms').load_bench(BENCH)


@needs_data
def test_load_bench(bench):
    assert bench['version'] == 'v1-std'
    assert bench['frozen'] is True  # frozen by the delegated review, 2026-10-24 (D-026)
    assert bench['drafts'] == []


@needs_data
def test_counts_per_domain(bench):
    prompts = bench['prompts']
    assert Counter(e['domain'] for e in prompts.values()) == {'code': 18, 'report': 20}
    # Ids are numbered over the rule's 21 selected tasks; three are excluded (README).
    code_ids = sorted(pid for pid, e in prompts.items() if e['domain'] == 'code')
    assert code_ids == [f'sc{n:02d}' for n in range(1, 22) if n not in (2, 4, 14)]
    report_ids = sorted(pid for pid, e in prompts.items() if e['domain'] == 'report')
    assert report_ids == [f'sr{n:02d}' for n in range(1, 21)]


@needs_data
def test_code_entries_complete(bench):
    for pid, e in bench['prompts'].items():
        if e['domain'] != 'code':
            continue
        assert e['status'] == 'written' and e['title'] and e['brief'], pid
        assert e['files'] == ['task.py'], pid
        assert re.fullmatch(r'bigcodebench-hard v0\.1\.4 BigCodeBench/\d+', e['source']), pid
        assert e['text'].endswith(ADDED_PARAGRAPH), pid
        test = BENCH / 'tests' / pid / 'test_task.py'
        assert test.is_file(), pid
        assert 'from task import *' in test.read_text(), pid
        assert (BENCH / 'reference' / pid / 'task.py').is_file(), pid


@needs_data
def test_report_entries_complete(bench):
    for pid, e in bench['prompts'].items():
        if e['domain'] != 'report':
            continue
        assert e['status'] == 'written' and e['title'] and e['brief'], pid
        assert isinstance(e['target_words'], int), pid
        data = json.loads((BENCH / 'ifeval' / f'{pid}.json').read_text())
        assert set(data) == {'key', 'instruction_id_list', 'kwargs'}, pid
        assert e['source'] == f"ifeval {data['key']}", pid
        assert len(data['instruction_id_list']) == len(data['kwargs']), pid


@pytest.mark.skipif(not [f for f in fetch.tree_files(BENCH) if f != 'manifest.yaml'],
                    reason='bench v1-std data not fetched (make venv-ifeval bench-std)')
def test_tree_matches_data_lock():
    """Every fetched or generated file is byte-identical to what the experiments ran on."""
    assert fetch.check_lock(BENCH) == []


def test_data_lock_well_formed():
    pins = fetch.read_lock()
    assert 'manifest.yaml' in pins and 'LICENSE' in pins
    assert pins['manifest.yaml'] == hashlib.sha256((BENCH / 'manifest.yaml').read_bytes()).hexdigest()
    checker = {p.split('/')[-1]: s for p, s in pins.items() if p.startswith(fetch.CHECKER_DIR + '/')}
    assert checker == {**fetch.CHECKER_FILES, **fetch.PATCHED, '__init__.py': fetch.EMPTY_SHA}
    assert pins['LICENSE'] == pins['ifeval_checker/LICENSE'] == fetch.LICENSE_SHA


@pytest.mark.skipif(not CHECKER_UTIL.is_file(), reason='IFEval checker not fetched (make bench-std)')
def test_local_change_patch_round_trips():
    """Reversing the committed patch on the patched file gives upstream's pinned bytes."""
    hunks = fetch.parse_patch(fetch.PATCH.read_text())
    assert set(hunks) == {'instructions_util.py'}
    upstream = fetch.apply_hunks(CHECKER_UTIL.read_text(), hunks['instructions_util.py'], reverse=True)
    assert fetch.sha256_bytes(upstream.encode()) == fetch.CHECKER_FILES['instructions_util.py']
    again = fetch.apply_hunks(upstream, hunks['instructions_util.py'])
    assert fetch.sha256_bytes(again.encode()) == fetch.PATCHED['instructions_util.py']


def test_apply_hunks_refuses_a_mismatch():
    patch = '--- a/x/f.py\n+++ b/x/f.py\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n'
    hunks = fetch.parse_patch(patch)['f.py']
    assert fetch.apply_hunks('a\nb\nz\n', hunks) == 'a\nc\nz\n'
    with pytest.raises(fetch.FetchError):
        fetch.apply_hunks('a\nB\nz\n', hunks)


def test_check_lock_reports_every_difference(tmp_path):
    for rel, text in {'prompts/a.md': 'a', 'ifeval/b.json': 'b', 'manifest.yaml': 'm'}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    lock = tmp_path / 'data.lock'
    lock.write_text('\n'.join(fetch.lock_lines(tmp_path)) + '\n')
    assert fetch.check_lock(tmp_path, lock=lock) == []
    (tmp_path / 'prompts' / 'a.md').write_text('changed')
    (tmp_path / 'ifeval' / 'b.json').unlink()
    (tmp_path / 'tests' / 'x').mkdir(parents=True)
    (tmp_path / 'tests' / 'x' / 'extra.py').write_text('')
    (tmp_path / 'tests' / 'x' / '__pycache__').mkdir()
    (tmp_path / 'tests' / 'x' / '__pycache__' / 'extra.pyc').write_bytes(b'')  # ignored
    problems = fetch.check_lock(tmp_path, lock=lock)
    assert sorted(p.split(':')[0] for p in problems) == ['missing', 'not in data.lock', 'sha256 differs']
