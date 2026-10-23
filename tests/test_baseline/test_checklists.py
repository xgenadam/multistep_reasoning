"""checklists.py: mechanical report checks (Q-02 stage 0, bench v1)."""

import json

import pytest

DOC = """# Ticketing

## Cost and hosting

Markdown files live in git, so hosting costs nothing extra.

## Migration

1. Export the tickets.
2. Convert them.
3. Review the result.

| Step | Owner |
| --- | --- |
| Export | Ana |
| Convert | Bo |

```
## not a heading
1. not an item
```

- a bullet
- another bullet
Total cost: 1,250 dollars.
"""


@pytest.fixture(scope='module')
def cl():
    from tests.test_baseline.conftest import load_baseline_module
    return load_baseline_module('checklists')


@pytest.mark.parametrize('item, passed, detail', [
    ({'check': 'heading', 'pattern': '(?i)cost'}, True, 1),
    ({'check': 'heading', 'pattern': '(?i)not a heading'}, False, 0),  # inside a fence
    ({'check': 'heading', 'pattern': '.', 'min': 3}, True, 3),
    ({'check': 'contains', 'pattern': r'(?i)\bgit\b'}, True, 1),
    ({'check': 'not_contains', 'pattern': 'Jira'}, True, 0),
    ({'check': 'numbered_items', 'section': '(?i)migrat', 'min': 3, 'max': 3}, True, 3),
    ({'check': 'numbered_items', 'section': '(?i)cost'}, False, 0),
    ({'check': 'numbered_items', 'section': '(?i)nowhere'}, False, "no section matching '(?i)nowhere'"),
    ({'check': 'bullet_items', 'min': 2, 'max': 2}, True, 2),
    ({'check': 'table_rows', 'min': 2, 'max': 2}, True, 2),
    ({'check': 'number', 'pattern': r'Total cost: ([\d,]+)', 'value': 1250}, True, 1250.0),
    ({'check': 'number', 'pattern': r'Total cost: ([\d,]+)', 'value': 1200, 'tol': 10}, False, 1250.0),
])
def test_checks(cl, item, passed, detail):
    got = cl.check_item(DOC, {'id': 'x', **item})
    assert got == {'passed': passed, 'detail': detail}


def test_word_count_counts_words_not_markup(cl):
    assert cl.check_item('## Head\n\nIt’s a well-known fact, 42 times.',
                         {'id': 'w', 'check': 'word_count', 'min': 7, 'max': 7})['passed']


def test_section_overlap_flags_a_repeated_section(cl):
    body = 'alpha bravo charlie delta echoes foxtrot'
    same = f'## One\n\n{body}\n\n## Two\n\n{body}\n'
    distinct = f'## One\n\n{body}\n\n## Two\n\nwholly different words entirely here\n'
    item = {'id': 'o', 'check': 'max_section_overlap', 'max': 0.5}
    assert cl.check_item(same, item) == {'passed': False, 'detail': 1.0}
    assert cl.check_item(distinct, item) == {'passed': True, 'detail': 0.0}
    assert cl.check_item('no headings at all', item)['passed'] is True


def test_validate_reports_problems(cl):
    assert cl.validate({'items': [{'id': 'a', 'check': 'heading', 'pattern': 'x'}]}) == []
    problems = cl.validate({'items': [
        {'id': 'a', 'check': 'nope'}, {'id': 'b', 'check': 'heading'},
        {'id': 'c', 'check': 'contains', 'pattern': '('}, {'id': 'c', 'check': 'word_count'}]})
    assert any('unknown check' in p for p in problems)
    assert any('needs pattern' in p for p in problems)
    assert any('bad pattern regex' in p for p in problems)
    assert 'duplicate item ids' in problems


def test_score_run_scores_report_results_only(cl, tmp_path):
    bench = tmp_path / 'bench'
    (bench / 'checklists').mkdir(parents=True)
    (bench / 'manifest.yaml').write_text(
        'prompts:\n  - {id: r1, domain: report}\n  - {id: c1, domain: code}\n')
    (bench / 'checklists' / 'r1.yaml').write_text(
        "id: r1\nitems:\n  - {id: h, check: heading, pattern: '(?i)cost'}\n"
        "  - {id: g, check: contains, pattern: 'Jira'}\n")
    run = tmp_path / 'run.json'
    run.write_text(json.dumps({'results': [
        {'prompt_id': 'r1', 'arm': 'b', 'run': 0, 'error': None, 'output': {'text': DOC}},
        {'prompt_id': 'c1', 'arm': 'b', 'run': 0, 'error': None, 'output': {'text': ''}},
        {'prompt_id': 'zz', 'arm': 'b', 'run': 0, 'error': None, 'output': {'text': ''}}]}))
    assert cl.main(['score', str(run), '--bench', str(bench)]) == 0
    out = json.loads((tmp_path / 'run.checklists.json').read_text())
    [row] = out['results']
    assert (row['prompt_id'], row['passed'], row['total'], row['score']) == ('r1', 1, 2, 0.5)
    assert out['skipped_unknown_prompts'] == ['zz']
    assert len(out['commit']) == 40
