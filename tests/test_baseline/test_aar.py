"""aar.py (the user, 2026-10-25): condensed traces, the review prompt, and the evidence check
that throws out a diagnosis whose quotes are not in the trace."""

import json

import pytest


@pytest.fixture(scope='module')
def aar():
    from tests.test_baseline.conftest import load_baseline_module
    return load_baseline_module('aar')


TURN = {
    'prompt_id': 'c01', 'arm': 'b', 'run': 0, 'error': None, 'prompt': 'Write wordcount.py.', 'traced': True,
    'plan': {'sub_tasks': [{'name': 'Parse args', 'type': 'code', 'objective': 'parse argv', 'context': 'first'}],
             'critique': 'No critique'},
    'steps': [{'kind': 'document', 'step': 1, 'of': 1, 'sub_task': 'Parse args', 'result': 'def main(): pass',
               'compose_attempts': [{'attempt': 1, 'ops': [{'type': 'add_part', 'id': 'p', 'body': 'x = ('}],
                                     'error': "file part 'p' does not parse as Python"}],
               'parts': [{'id': 'p', 'kind': 'file', 'change': 'added', 'body': 'def main(): pass'}]}],
    'calls': [{'index': 7, 'kind': 'executor_turn', 'step': '1', 'label': 'Execute', 'prompt_tokens': 5,
               'completion_tokens': 2, 'finish_reason': 'stop', 'error': None, 'reasoning': '',
               'messages': [{'role': 'system', 'text': 'You are an executor.'}, {'role': 'user', 'text': 'Do: parse argv'}],
               'content': '{"result": "def main(): pass"}'}],
    'output': 'final answer text',
    'test': {'score': {'passed': 0, 'total': 3, 'extraction_ok': False, 'missing': ['wordcount.py'],
                       'unclosed_fence': False}, 'extraction': {'files': {}}, 'outcomes': {'t::a': 'failed'},
             'output_tail': 'E   FileNotFoundError'},
    'compare': {'relaxed-a': {'score': {'passed': 3, 'total': 3}, 'output': 'the direct answer'}},
}


def test_condense_shows_every_stage_in_order(aar):
    text = aar.condense(TURN)
    order = ["## The user's request", '## Plan', 'Step 1 / executor', 'Call 7', 'Do: parse argv',
             'Step 1 / sub-task result', "REJECTED: file part 'p' does not parse", 'document after this step',
             '## Final answer', 'INCOMPLETE; missing wordcount.py', 'Failed: t::a', 'single direct answer (relaxed-a), 3 of 3']
    positions = [text.index(s) for s in order]
    assert positions == sorted(positions)


def test_repeated_system_prompts_are_given_once(aar):
    turn = json.loads(json.dumps(TURN))
    second = dict(turn['calls'][0], index=8)
    turn['steps'].append(dict(turn['steps'][0], step=2, of=2))
    turn['calls'].append(dict(second, step='2'))
    text = aar.condense(turn)
    assert text.count('You are an executor.') == 1 and '[system prompt: same as call 7]' in text


def test_evidence_must_be_quoted_from_the_trace(aar):
    trace = aar.condense(TURN)
    good = {'category': 'composer', 'evidence': [{'quote': "file part 'p'   does not parse as Python"}]}
    assert aar.check_evidence(good, trace) == {'quotes': 1, 'found': 1, 'valid': True, 'category_known': True}
    made_up = {'category': 'plan', 'evidence': [{'quote': 'the planner ignored the file format entirely'}]}
    assert aar.check_evidence(made_up, trace)['valid'] is False
    assert aar.check_evidence({'category': 'plan', 'evidence': []}, trace)['valid'] is False


def test_replies_parse_with_or_without_a_fence(aar):
    assert aar.parse_reply('```json\n{"category": "plan"}\n```') == {'category': 'plan'}
    assert aar.parse_reply('Here: {"category": "other"} done') == {'category': 'other'}
    assert aar.parse_reply('no json') is None


def test_the_review_prompt_offers_every_category_and_the_record(aar):
    prompt = aar.review_prompt('RECORD-TEXT')
    assert all(k in prompt for k in aar.CATEGORIES) and 'RECORD-TEXT' in prompt
    assert 'suspect' not in prompt.lower()  # no hypothesis is handed to the reviewer
