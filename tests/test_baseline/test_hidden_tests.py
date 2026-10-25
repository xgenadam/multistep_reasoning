"""hidden_tests.py: deliverable extraction, the pytest sandbox, check-bench and score (Q-02)."""

import json
import textwrap

import pytest
import yaml

WC = textwrap.dedent('''\
    import sys


    def count(path):
        text = open(path).read()
        return len(text.splitlines()), len(text.split()), len(text)


    if __name__ == '__main__':
        for p in sys.argv[1:]:
            print(*count(p), p)
    ''')

TESTS = textwrap.dedent('''\
    import subprocess
    import sys
    from pathlib import Path

    from wordcount import count

    HERE = Path(__file__).parent


    def test_counts():
        assert count(HERE / 'sample.txt') == (2, 5, 24)


    def test_empty(tmp_path):
        p = tmp_path / 'e.txt'
        p.write_text('')
        assert count(p) == (0, 0, 0)


    def test_cli():
        out = subprocess.run([sys.executable, 'wordcount.py', str(HERE / 'sample.txt')],
                             capture_output=True, text=True, check=True).stdout
        assert out.split()[:3] == ['2', '5', '24']
    ''')

SAMPLE = 'one two three\nfour five\n'  # 2 lines, 5 words, 24 chars


def write(root, files):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


@pytest.fixture
def bench(tmp_path):
    root = tmp_path / 'bench'
    write(root, {
        'manifest.yaml': yaml.safe_dump({'prompts': [
            {'id': 'wc', 'domain': 'code', 'files': ['wordcount.py']},
            {'id': 'essay', 'domain': 'report'},
        ]}),
        'prompts/wc.md': 'Write a module `wordcount.py` ...\n',
        'prompts/essay.md': 'Write an essay.\n',
        'tests/wc/test_wordcount.py': TESTS,
        'tests/wc/sample.txt': SAMPLE,
        'reference/wc/wordcount.py': WC,
        # Off by one on characters: test_counts and test_cli fail.
        'reference/wc/broken/off_by_one/wordcount.py': WC.replace('len(text)\n', 'len(text) - 1\n'),
    })
    return root


# ---------------------------------------------------------------- text parsing

BODY = 'def count(path):\n    return 1, 2, 3'


@pytest.mark.parametrize('text, rule', [
    ('wordcount.py\n```python\n' + BODY + '\n```', 'label_line'),
    ('**wordcount.py**\n```python\n' + BODY + '\n```', 'label_line'),
    ('`wordcount.py`\n```python\n' + BODY + '\n```', 'label_line'),
    ('### wordcount.py\n\n```python\n' + BODY + '\n```', 'label_line'),
    ('# wordcount.py\n```python\n' + BODY + '\n```', 'label_line'),
    ('File: wordcount.py\n```python\n' + BODY + '\n```', 'label_line'),
    ('- **`wordcount.py`**:\n```python\n' + BODY + '\n```', 'label_line'),
    ('```python wordcount.py\n' + BODY + '\n```', 'info_string'),
    ('```python title="wordcount.py"\n' + BODY + '\n```', 'info_string'),
    ('```python:wordcount.py\n' + BODY + '\n```', 'info_string'),
    ('Intro.\n\n```python\n# wordcount.py\n' + BODY + '\n```', 'first_line_comment'),
    ('```python\n#!/usr/bin/env python3\n# file: wordcount.py\n' + BODY + '\n```',
     'first_line_comment'),
    ('Here is `wordcount.py`:\n```python\n' + BODY + '\n```', 'label_mention'),
    ('## wordcount.py (CLI)\n```python\n' + BODY + '\n```', 'label_mention'),
    ('Some code:\n```python\n' + BODY + '\n```', 'lone_python_block'),
    ('~~~python\n' + BODY + '\n~~~', 'lone_python_block'),
])
def test_text_forms(hidden_tests, text, rule):
    files, notes = hidden_tests.extract_files(text, ['wordcount.py'])
    assert list(files) == ['wordcount.py']
    assert 'def count(path):' in files['wordcount.py']
    assert notes['files']['wordcount.py']['rule'] == rule
    assert notes['missing'] == []


def test_lone_block_needs_expected_paths(hidden_tests):
    files, notes = hidden_tests.extract_files('```python\n' + BODY + '\n```')
    assert files == {}
    assert notes['unlabelled'][0]['lang'] == 'python'


def test_unlabelled_shell_and_output_blocks_are_recorded(hidden_tests):
    text = ('wordcount.py\n```python\n' + BODY + '\n```\n\n'
            'Run it with `python wordcount.py a.txt`:\n```bash\npython wordcount.py a.txt\n```\n'
            'Output:\n```\n2 5 24 a.txt\n```\n')
    files, notes = hidden_tests.extract_files(text, ['wordcount.py'])
    assert files == {'wordcount.py': BODY}
    assert [u['lang'] for u in notes['unlabelled']] == ['bash', '']


def test_several_unlabelled_python_blocks_guess_the_definitions(hidden_tests):
    # Was "ambiguous, nothing extracted" (S-022 changed it: a correct answer
    # with a usage example scored 0/N). The guess is named in the notes.
    text = '```python\n' + BODY + '\n```\n\n```python\nprint(count("a"))\n```\n'
    files, notes = hidden_tests.extract_files(text, ['wordcount.py'])
    assert files == {'wordcount.py': BODY}
    assert notes['files']['wordcount.py']['rule'] == 'largest_python_block_guess'
    assert [u['reason'] for u in notes['unlabelled']] == ['several unlabelled python blocks']


def test_later_block_wins_and_is_recorded(hidden_tests):
    text = 'wordcount.py\n```python\nOLD\n```\nFixed:\n\nwordcount.py\n```python\nNEW\n```\n'
    files, notes = hidden_tests.extract_files(text, ['wordcount.py'])
    assert files == {'wordcount.py': 'NEW'}
    assert notes['duplicates'] == [{'path': 'wordcount.py', 'replaced_block': 0, 'by_block': 1}]


def test_basename_and_suffix_map_to_expected(hidden_tests):
    text = ('core.py\n```python\nCORE\n```\n'
            '```python src/pkg/__init__.py\nINIT\n```\n'
            'other.py\n```python\nOTHER\n```\n')
    files, notes = hidden_tests.extract_files(text, ['pkg/core.py', 'pkg/__init__.py'])
    assert files == {'pkg/core.py': 'CORE', 'pkg/__init__.py': 'INIT', 'other.py': 'OTHER'}
    assert notes['files']['pkg/core.py']['rule'] == 'label_line+expected_basename'
    assert notes['files']['pkg/__init__.py']['rule'] == 'info_string+expected_suffix'


def test_longer_fence_holds_inner_fence(hidden_tests):
    text = 'README.md\n````markdown\n# T\n```bash\nmake\n```\n````\n'
    files, _ = hidden_tests.extract_files(text)
    assert files == {'README.md': '# T\n```bash\nmake\n```'}


def test_unclosed_fence_runs_to_end(hidden_tests):
    files, notes = hidden_tests.extract_files('wordcount.py\n```python\n' + BODY)
    assert files == {'wordcount.py': BODY}
    assert notes['unclosed_fence'] is True


# ---------------------------------------------------------------- path safety

@pytest.mark.parametrize('raw', ['/etc/passwd', '../x.py', 'a/../../x.py', 'C:/x.py',
                                 'c:\\x.py', '~/x.py', '', 'a/\0.py'])
def test_safe_path_rejects(hidden_tests, raw):
    with pytest.raises(hidden_tests.UnsafePath):
        hidden_tests.safe_path(raw)


def test_safe_path_normalises(hidden_tests):
    assert hidden_tests.safe_path('./pkg\\core.py') == 'pkg/core.py'
    assert hidden_tests.safe_path('pkg//./core.py') == 'pkg/core.py'


def test_unsafe_paths_are_ignored_in_text_and_snapshot(hidden_tests):
    files, notes = hidden_tests.extract_files('```python ../evil.py\nX\n```\n')
    assert files == {}
    assert notes['ignored'][0]['reason'] == 'unsafe path'
    snap = {'parts': [{'kind': 'file', 'title': '/tmp/evil.py', 'body': 'X'}]}
    files, notes = hidden_tests.extract_from_snapshot(snap)
    assert files == {} and notes['ignored'][0]['reason'] == 'unsafe path'


def test_run_tests_never_writes_outside_sandbox(hidden_tests, bench, tmp_path):
    res = hidden_tests.run_tests({'../escape.py': 'X', '/abs.py': 'X', 'wordcount.py': WC},
                                 bench / 'tests' / 'wc', timeout_s=60)
    assert len(res['rejected']) == 2
    assert not (tmp_path / 'escape.py').exists()
    assert res['passed'] == 3


# ---------------------------------------------------------------- snapshot

def test_snapshot_file_parts(hidden_tests):
    snap = {'parts': [
        {'id': 'p1', 'kind': 'section', 'title': 'Intro', 'body': 'text'},
        {'id': 'p2', 'kind': 'file', 'title': 'wordcount.py', 'body': 'OLD'},
        {'id': 'p3', 'kind': 'file', 'title': 'pkg/core.py', 'body': 'CORE'},
        {'id': 'p4', 'kind': 'file', 'title': 'wordcount.py', 'body': WC},
    ]}
    assert hidden_tests.files_from_snapshot(snap) == {'wordcount.py': WC, 'pkg/core.py': 'CORE'}
    _, notes = hidden_tests.extract_from_snapshot(snap)
    assert notes['duplicates'][0]['path'] == 'wordcount.py'


def test_rendered_snapshot_parses_back(hidden_tests):
    from reasoning_sub_agents.document import Document
    snap = {'parts': [{'id': 'p1', 'kind': 'file', 'title': 'pkg/core.py', 'body': 'CORE'},
                      {'id': 'p2', 'kind': 'section', 'title': 'Usage',
                       'body': '```bash\npython -m pkg.core\n```'}]}
    text = Document.from_dict(snap).render()
    assert hidden_tests.files_from_text(text) == {'pkg/core.py': 'CORE'}


def test_extract_output_prefers_snapshot(hidden_tests):
    out = {'text': 'wordcount.py\n```python\nTEXT\n```',
           'snapshot': {'parts': [{'kind': 'file', 'title': 'wordcount.py', 'body': 'SNAP'}]}}
    files, notes = hidden_tests.extract_output(out, ['wordcount.py'])
    assert files == {'wordcount.py': 'SNAP'} and notes['source'] == 'snapshot'
    files, notes = hidden_tests.extract_output({'text': out['text'], 'snapshot': None})
    assert files == {'wordcount.py': 'TEXT'} and notes['source'] == 'text'
    files, notes = hidden_tests.extract_output(None, ['wordcount.py'])
    assert files == {} and notes['missing'] == ['wordcount.py']


# ---------------------------------------------------------------- running

def test_passing_and_failing_deliverables(hidden_tests, bench):
    tests = bench / 'tests' / 'wc'
    good = hidden_tests.run_tests({'wordcount.py': WC}, tests, timeout_s=60)
    assert (good['passed'], good['failed'], good['total']) == (3, 0, 3)
    assert good['exit_code'] == 0 and not good['collection_error'] and not good['timed_out']
    assert set(good['outcomes'].values()) == {'passed'}
    assert good['isolation'] in ('netns', 'none')
    bad = hidden_tests.run_tests({'wordcount.py': WC.replace('len(text)\n', '0\n')}, tests, 60)
    assert (bad['passed'], bad['failed']) == (1, 2)
    assert bad['outcomes']['test_wordcount::test_counts'] == 'failed'
    assert bad['exit_code'] == 1 and 'test_counts' in bad['output_tail']


def test_hidden_tests_override_and_own_tests_not_collected(hidden_tests, bench):
    files = {'wordcount.py': WC, 'test_wordcount.py': 'def test_x(): assert False\n',
             'test_mine.py': 'def test_mine(): pass\n', 'sample.txt': 'junk\n',
             'pytest.ini': '[pytest]\naddopts = -x --bogus-flag\n'}
    res = hidden_tests.run_tests(files, bench / 'tests' / 'wc', timeout_s=60)
    assert sorted(res['overridden']) == ['sample.txt', 'test_wordcount.py']
    assert (res['passed'], res['total']) == (3, 3)


def test_collection_error(hidden_tests, bench):
    res = hidden_tests.run_tests({'wordcount.py': 'def count(:\n'}, bench / 'tests' / 'wc', 60)
    assert res['collection_error'] is True
    assert res['passed'] == 0 and res['errors'] >= 1
    assert res['exit_code'] == 2


def test_timeout_kills_the_run(hidden_tests, tmp_path):
    tests = tmp_path / 'tests'
    write(tests, {'test_slow.py': 'import time\n\ndef test_slow():\n    time.sleep(30)\n'})
    res = hidden_tests.run_tests({}, tests, timeout_s=2)
    assert res['timed_out'] is True
    assert res['seconds'] < 10
    assert res['passed'] == 0 and res['total'] == 0


def test_a_hanging_test_costs_only_itself(hidden_tests, tmp_path):
    """One infinite loop fails its own test; the file's other tests still count."""
    tests = tmp_path / 'tests'
    write(tests, {'test_mix.py': 'def test_ok():\n    assert True\n\n'
                                 'def test_hangs():\n    while True:\n        pass\n\n'
                                 'def test_ok_too():\n    assert True\n'})
    res = hidden_tests.run_tests({}, tests, timeout_s=60, test_timeout_s=1)
    assert res['timed_out'] is False
    assert res['outcomes'] == {'test_mix::test_ok': 'passed',
                               'test_mix::test_hangs': 'failed',
                               'test_mix::test_ok_too': 'passed'}
    assert 'per-test timeout' in res['output_tail']


def test_no_network_when_isolated(hidden_tests, tmp_path):
    if hidden_tests.isolation() != 'netns':
        pytest.skip('unshare -rn unavailable here')
    tests = tmp_path / 'tests'
    write(tests, {'test_net.py': textwrap.dedent('''\
        import socket

        def test_offline():
            s = socket.socket()
            s.settimeout(1)
            try:
                s.connect(('1.1.1.1', 53))
            except OSError:
                return
            raise AssertionError('network reachable')
        ''')})
    assert hidden_tests.run_tests({}, tests, timeout_s=30)['passed'] == 1


# ---------------------------------------------------------------- CLI

def test_check_bench_passes(hidden_tests, bench, capsys):
    assert hidden_tests.main(['check-bench', '--bench', str(bench), '--timeout', '60']) == 0
    out = capsys.readouterr().out
    assert 'wc  OK' in out and 'reference 3/3' in out and 'broken 1/1 caught' in out
    assert 'essay' not in out


def test_check_bench_fails_on_wrong_test(hidden_tests, bench, capsys):
    p = bench / 'tests' / 'wc' / 'test_wordcount.py'
    p.write_text(p.read_text().replace('(2, 5, 24)', '(2, 5, 25)'))
    assert hidden_tests.main(['check-bench', '--bench', str(bench), '--timeout', '60']) == 1
    out = capsys.readouterr().out
    assert 'wc  FAIL' in out and 'reference 2/3' in out


def test_check_bench_fails_on_uncaught_broken_and_missing_file(hidden_tests, bench, capsys):
    write(bench, {'reference/wc/broken/same/wordcount.py': WC})
    manifest = yaml.safe_load((bench / 'manifest.yaml').read_text())
    manifest['prompts'][0]['files'].append('extra.py')
    (bench / 'manifest.yaml').write_text(yaml.safe_dump(manifest))
    assert hidden_tests.main(['check-bench', '--bench', str(bench), '--timeout', '60']) == 1
    out = capsys.readouterr().out
    assert "broken variant 'same' passes every test" in out
    assert "not in reference: ['extra.py']" in out


def test_score_run_file(hidden_tests, bench, tmp_path, capsys):
    snap = {'parts': [{'kind': 'file', 'title': 'wordcount.py', 'body': WC}]}
    run = {'results': [
        {'prompt_id': 'wc', 'arm': 'single', 'run': 0, 'error': None,
         'output': {'text': '**wordcount.py**\n```python\n' + WC + '```\n', 'snapshot': None}},
        {'prompt_id': 'wc', 'arm': 'single', 'run': 1, 'error': None,
         'output': {'text': 'Sorry, no code.', 'snapshot': None}},
        {'prompt_id': 'wc', 'arm': 'harness', 'run': 0, 'error': None,
         'output': {'text': 'ignored', 'snapshot': snap}},
        {'prompt_id': 'essay', 'arm': 'single', 'run': 0, 'error': None,
         'output': {'text': 'An essay.', 'snapshot': None}},
        {'prompt_id': 'wc', 'arm': 'harness', 'run': 1, 'error': 'timeout', 'output': None},
    ]}
    run_file = tmp_path / 'runs' / '20261023T000000Z_q02.json'
    run_file.parent.mkdir()
    run_file.write_text(json.dumps(run))
    assert hidden_tests.main(['score', str(run_file), '--bench', str(bench),
                              '--jobs', '4', '--timeout', '60']) == 0
    out = capsys.readouterr().out
    assert 'harness' in out and '3/3 0/3*' in out
    data = json.loads((run_file.parent / '20261023T000000Z_q02.tests.json').read_text())
    assert len(data['run_file_sha256']) == 64 and len(data['manifest_sha256']) == 64
    assert data['isolation'] in ('netns', 'none') and 'commit' in data
    assert data['references'] == {'wc': {'n_tests': 3, 'passed': 3, 'source': 'reference'}}
    rows = {(r['arm'], r['run']): r for r in data['results']}
    assert set(rows) == {('single', 0), ('single', 1), ('harness', 0), ('harness', 1)}
    assert rows['single', 0]['pass_rate'] == 1.0
    assert rows['single', 0]['extraction']['files']['wordcount.py']['rule'] == 'label_line'
    assert rows['harness', 0]['extraction']['source'] == 'snapshot'
    assert rows['single', 1]['extraction_ok'] is False
    assert rows['single', 1]['tests']['collection_error'] is True
    assert rows['single', 1]['pass_rate'] == 0.0 and rows['single', 1]['n_tests'] == 3
    assert rows['harness', 1]['run_error'] == 'timeout'


def test_markdown_wrapper_is_unwrapped(hidden_tests):
    text = ('```markdown\nHere is the module.\n\nlru.py\n```python\nclass LRUCache:\n    pass\n```\n\n'
            'Run it with `python lru.py`.\n```\n')
    files, notes = hidden_tests.extract_files(text, ['lru.py'])
    assert files == {'lru.py': 'class LRUCache:\n    pass'}
    assert notes['unwrapped_markdown'] is True
    plain, notes = hidden_tests.extract_files('lru.py\n```python\nx = 1\n```\n', ['lru.py'])
    assert plain == {'lru.py': 'x = 1'} and notes['unwrapped_markdown'] is False


def test_several_unlabelled_python_blocks_take_the_definitions(hidden_tests):
    text = ('```python\nclass LRUCache:\n    def get(self):\n        pass\n```\n\nUsage:\n\n'
            '```python\ncache = LRUCache(2)\ncache.put(1, 1)\nprint(cache.get(1))\n```\n')
    files, notes = hidden_tests.extract_files(text, ['lru.py'])
    assert files['lru.py'].startswith('class LRUCache')
    assert notes['files']['lru.py']['rule'] == 'largest_python_block_guess'
    assert any(u.get('reason') == 'several unlabelled python blocks' for u in notes['unlabelled'])


def test_snapshot_file_part_holding_a_markdown_reply(hidden_tests):
    # The executor's reply kept verbatim in a file part (Q-02, 2026-10-25):
    # the code inside the fence is the file, by the text rule.
    code = 'import sys\n\nprint(sys.argv)'
    snap = {'parts': [
        {'id': 'a', 'kind': 'file', 'title': 'csv2json.py', 'body': f'csv2json.py\n```\n{code}\n```'},
        {'id': 'b', 'kind': 'file', 'title': 'pkg/core.py', 'body': f'\n```python\n{code}\n```\n'},
        {'id': 'c', 'kind': 'file', 'title': 'doc.py',
         'body': 'def f():\n    """Example:\n    ```\n    f()\n    ```\n    """'},
        {'id': 'd', 'kind': 'file', 'title': 'tictactoe.py',
         'body': f'Here is `games/tictactoe.py`:\n\n```python\n{code}\n```\nDone.'},
        {'id': 'e', 'kind': 'file', 'title': 'notes.txt', 'body': 'plain text'},
    ]}
    files, notes = hidden_tests.extract_from_snapshot(snap)
    assert files['csv2json.py'] == code and files['pkg/core.py'] == code
    assert notes['files']['csv2json.py']['rule'] == 'snapshot_part+fenced_body'
    assert files['doc.py'].startswith('def f():')  # a real file with fences inside
    assert files['tictactoe.py'] == code             # intro and a longer label
    assert files['notes.txt'] == 'plain text'
