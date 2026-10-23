"""Bench v1's composition rules (journal/baseline/bench/v1/README.md, Q-9)."""

from collections import Counter

import pytest
import yaml

from tests.test_baseline.conftest import BASELINE

BENCH = BASELINE / 'bench' / 'v1'


@pytest.fixture(scope='module')
def entries():
    return yaml.safe_load((BENCH / 'manifest.yaml').read_text())['prompts']


def test_size_and_domains(entries):
    assert Counter(e['domain'] for e in entries) == {'code': 70, 'report': 70}
    ids = [e['id'] for e in entries]
    assert len(set(ids)) == len(ids)


def test_long_and_follow_up_shares(entries):
    assert sum(bool(e.get('long')) for e in entries) >= len(entries) / 3
    for domain in ('code', 'report'):
        mine = [e for e in entries if e['domain'] == domain]
        follow = [e for e in mine if e.get('follows')]
        assert len(follow) == 14
        assert sum(bool(e.get('overlap')) for e in mine) == 6


def test_follow_ups_are_depth_one_and_unique(entries):
    by_id = {e['id']: e for e in entries}
    parents = [e['follows'] for e in entries if e.get('follows')]
    assert len(parents) == len(set(parents))
    for e in entries:
        if e.get('follows'):
            parent = by_id[e['follows']]
            assert parent['domain'] == e['domain']
            assert not parent.get('follows')
            assert e['id'] == parent['id'] + 'f'


def test_g3_subset(entries):
    g3 = [e for e in entries if 'g3' in (e.get('subsets') or [])]
    assert Counter(e['domain'] for e in g3) == {'code': 5, 'report': 5}
    follow = [e for e in g3 if e.get('follows')]
    assert len(follow) == 2
    assert all(e['follows'] in {g['id'] for g in g3} for e in follow)


def test_entry_fields(entries):
    for e in entries:
        assert e['status'] in ('draft', 'written'), e['id']
        assert e.get('title') and e.get('brief'), e['id']
        if e['domain'] == 'code':
            assert e.get('files'), e['id']
            assert e['id'].startswith('c')
            if e.get('long'):
                assert len(e['files']) > 1, e['id']  # long code = more than one file
        else:
            assert e.get('target_words'), e['id']
            assert e['id'].startswith('r')
            if e.get('long'):
                assert e['target_words'] >= 6000, e['id']  # beyond 8,192 tokens


def test_written_entries_are_complete(entries):
    for e in entries:
        if e['status'] != 'written':
            continue
        assert (BENCH / 'prompts' / f'{e["id"]}.md').exists(), e['id']
        if e['domain'] == 'code':
            assert list((BENCH / 'tests' / e['id']).glob('test_*.py')), e['id']
            assert (BENCH / 'reference' / e['id']).is_dir(), e['id']
        else:
            assert (BENCH / 'checklists' / f'{e["id"]}.yaml').exists(), e['id']


def test_written_prompts_carry_the_delivery_lines(entries):
    for e in entries:
        if e['status'] != 'written':
            continue
        text = (BENCH / 'prompts' / f'{e["id"]}.md').read_text()
        if e['domain'] == 'code':
            assert 'Use only the Python 3.12 standard library.' in text
            assert "with the file's path on the line just before the block" in text
            if e.get('follows'):
                assert 'Give the complete updated files' in text
        elif e.get('follows'):
            assert 'Reply with the complete updated document.' in text


def test_arms_loads_the_written_entries_and_counts_drafts(entries):
    from tests.test_baseline.conftest import load_baseline_module
    arms = load_baseline_module('arms')
    bench = arms.load_bench(BENCH)
    written = {e['id'] for e in entries if e['status'] == 'written'}
    assert set(bench['prompts']) == written
    assert len(bench['drafts']) == len(entries) - len(written)
    assert bench['frozen'] is True and bench['drafts'] == []
