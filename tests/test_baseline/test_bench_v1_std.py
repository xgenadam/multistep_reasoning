"""Bench v1-std, the standard slice (journal/baseline/bench/v1-std/README.md)."""

import json
import re
from collections import Counter

import pytest

from tests.test_baseline.conftest import BASELINE, load_baseline_module

BENCH = BASELINE / 'bench' / 'v1-std'
ADDED_PARAGRAPH = ('Put the code in a file `task.py`. Use only the Python 3.12 standard library. '
                   'Give each file in its own fenced code block, with the file\'s path on the '
                   'line just before the block.')


@pytest.fixture(scope='module')
def bench():
    return load_baseline_module('arms').load_bench(BENCH)


def test_load_bench(bench):
    assert bench['version'] == 'v1-std'
    assert bench['frozen'] is False
    assert bench['drafts'] == []


def test_counts_per_domain(bench):
    prompts = bench['prompts']
    assert Counter(e['domain'] for e in prompts.values()) == {'code': 18, 'report': 20}
    # Ids are numbered over the rule's 21 selected tasks; three are excluded (README).
    code_ids = sorted(pid for pid, e in prompts.items() if e['domain'] == 'code')
    assert code_ids == [f'sc{n:02d}' for n in range(1, 22) if n not in (2, 4, 14)]
    report_ids = sorted(pid for pid, e in prompts.items() if e['domain'] == 'report')
    assert report_ids == [f'sr{n:02d}' for n in range(1, 21)]


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
