"""arms.py --trace-calls (the user, 2026-10-25: a viewer to follow a harness turn and see where
it broke): MeasuredCompletions.trace gets every call's request and reply text, and
IntermediateWriter.call writes one file per call under the turn's intermediates."""

import json
from types import SimpleNamespace

import pytest


def _choice(content, delta=False):
    body = SimpleNamespace(content=content, reasoning_content=None)
    return SimpleNamespace(finish_reason='stop', **({'delta': body} if delta else {'message': body}))


class Fake:
    def create(self, **kwargs):
        usage = SimpleNamespace(prompt_tokens=7, completion_tokens=3)
        if kwargs.get('stream'):
            return iter([SimpleNamespace(choices=[_choice('Hel', True)], usage=None),
                         SimpleNamespace(choices=[_choice('lo', True)], usage=None),
                         SimpleNamespace(choices=[], usage=usage)])
        return SimpleNamespace(choices=[_choice('{"ops": []}')], usage=usage)


class Failing:
    def create(self, **kwargs):
        raise ConnectionError('server went away')


@pytest.fixture
def arms():
    from tests.test_baseline.conftest import load_baseline_module
    return load_baseline_module('arms')


def _traced(arms, tmp_path, real):
    measured = arms.harness.MeasuredCompletions(real)
    writer = arms.IntermediateWriter(tmp_path / 'run')
    measured.trace = writer.call
    return measured, writer


def test_every_call_is_written_with_its_messages_and_reply(arms, tmp_path):
    measured, writer = _traced(arms, tmp_path, Fake())
    token = arms.harness._current_turn.set('b:c01#r0:t0')
    try:
        writer('plan', {'sub_tasks': []})
        measured.create(model='m', messages=[{'role': 'user', 'content': 'compose this'}],
                        response_format={'type': 'json_object'})
        list(measured.create(model='m', messages=[{'role': 'user', 'content': 'say hello'}], stream=True))
    finally:
        arms.harness._current_turn.reset(token)
    turn = tmp_path / 'run' / 'b_c01_r0_t0'
    assert (turn / '01_plan.json').exists()  # the step files survive the first call
    first, second = [json.loads(f.read_text()) for f in sorted((turn / 'calls').iterdir())]
    assert first['messages'] == [{'role': 'user', 'content': 'compose this'}]
    assert first['content'] == '{"ops": []}' and first['params']['response_format'] == {'type': 'json_object'}
    assert first['record']['turn'] == 'b:c01#r0:t0' and first['record']['prompt_tokens'] == 7
    assert second['content'] == 'Hello' and second['record']['stream'] is True
    assert second['record']['index'] == first['record']['index'] + 1


def test_a_call_that_raises_is_traced_with_its_exception(arms, tmp_path):
    measured, _ = _traced(arms, tmp_path, Failing())
    token = arms.harness._current_turn.set('t-err')
    try:
        with pytest.raises(ConnectionError):
            measured.create(model='m', messages=[{'role': 'user', 'content': 'x'}])
    finally:
        arms.harness._current_turn.reset(token)
    [f] = (tmp_path / 'run' / 't-err' / 'calls').iterdir()
    traced = json.loads(f.read_text())
    assert traced['record']['error'] == 'ConnectionError' and 'server went away' in traced['content']


def test_a_trace_that_fails_never_changes_the_call(arms):
    measured = arms.harness.MeasuredCompletions(Fake())
    measured.trace = lambda *a: 1 / 0
    resp = measured.create(model='m', messages=[])
    assert resp.choices[0].message.content == '{"ops": []}' and measured.total_calls == 1


def test_no_trace_by_default(arms):
    assert arms.harness.MeasuredCompletions(Fake()).trace is None


def test_trace_view_builds_a_turn_and_lists_its_problems(tmp_path):
    from tests.test_baseline.conftest import load_baseline_module
    view = load_baseline_module('trace_view')
    turn = tmp_path / 'inter' / 'b_c01_r0_t0'
    (turn / 'calls').mkdir(parents=True)
    (turn / '01_plan.json').write_text(json.dumps({'kind': 'plan', 'sub_tasks': [{'name': 'Parse', 'objective': 'parse args'}],
                                                   'decomposition_history': {'critique': 'fine'}}))
    attempts = [{'attempt': 1, 'ops': [{'type': 'add_part', 'id': 'p', 'body': 'x'}], 'error': 'does not parse'},
                {'attempt': 'fallback', 'ops': [], 'error': None, 'fallback_after': 'does not parse'}]
    (turn / '02_document_1.json').write_text(json.dumps({
        'kind': 'document', 'step': 1, 'of': 1, 'sub_task': 'Parse', 'status': 'TaskStatus.COMPLETED',
        'result': 'def main(): ...', 'compose_attempts': attempts,
        'snapshot': {'parts': [{'id': 'p', 'kind': 'file', 'title': 'a.py', 'body': 'def main(): ...'}]}}))
    (turn / 'calls' / '00003_compose.json').write_text(json.dumps({
        'record': {'index': 3, 'kind': 'compose', 'phase': 'Composing after 1/1: Parse', 'turn': 'b:c01#r0:t0'},
        'messages': [{'role': 'user', 'content': 'compose'}], 'params': {'max_tokens': 9}, 'content': '{}', 'reasoning': ''}))
    run = {'label': 'relaxed-b-x', 'results': [{'prompt_id': 'c01', 'arm': 'b', 'run': 0, 'error': None,
                                                'intermediates': {'dir': str(turn)}, 'output': {'text': 'final'}}]}
    run_file = tmp_path / 'r.json'
    run_file.write_text(json.dumps(run))
    (tmp_path / 'r.tests.json').write_text(json.dumps({'results': [{
        'prompt_id': 'c01', 'arm': 'b', 'run': 0, 'extraction_ok': False, 'extraction': {'missing': ['a.py']},
        'tests': {'passed': 1, 'total': 4, 'outcomes': {'t::x': 'failed'}}}]}))
    out = tmp_path / 'view'
    assert view.main([str(run_file), '--bench', str(tmp_path), '--out', str(out)]) == 0
    assert (out / 'index.html').exists() and '/*__INDEX__*/' not in (out / 'index.html').read_text()
    data = (out / 'data' / 'b_c01_r0.js').read_text()
    built = json.loads(data[data.index(',') + 1:data.rindex(');')])
    assert built['traced'] and built['calls'][0]['step'] == '1'
    assert built['steps'][0]['parts'][0]['change'] == 'added'
    whats = [p['what'] for p in built['problems']]
    assert whats[0] == 'step 1 attempt 1 rejected: does not parse'
    assert any('fallback' in w for w in whats) and any('extract' in w for w in whats)
    assert whats[-1] == '3 of 4 hidden tests failed'
