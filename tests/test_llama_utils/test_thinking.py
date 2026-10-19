"""The thinking switch and reasoning capture at the call seam (0-15, D-013, P0-10).

Every call path in llama_utils (instructor JSON, the non-instructor JSON
retry, stream_conversation) must send an explicit
``chat_template_kwargs.enable_thinking``. The stock-OpenAI paths are checked
in the HTTP body the server receives; the non-instructor path, which only a
non-OpenAI client takes, in the kwargs its create() gets. Reasoning is
captured from ``reasoning``, ``reasoning_content`` and a leading
``<think>…</think>``, and goes only to the turn's side log.
"""

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI
from pydantic import BaseModel

from reasoning_sub_agents.config.schema import OptionsConfig
from reasoning_sub_agents.llama_utils import (
    extract_content,
    get_streamed_json_response,
    split_reasoning,
    stream_conversation,
    thinking_session,
)
from reasoning_sub_agents.progress import llm_step
from reasoning_sub_agents.schemas import LLMInput, LLMMessage


class Verdict(BaseModel):
    ok: bool


def _llm_input() -> LLMInput:
    return LLMInput(messages=[LLMMessage(role='user', content='Is this fine?')])


def _options(tmp_path, **kwargs) -> OptionsConfig:
    return OptionsConfig(thinking_log_dir=str(tmp_path), **kwargs)


def _completion(message: dict, usage: dict | None = None) -> dict:
    return {
        'id': 'c', 'object': 'chat.completion', 'created': 0, 'model': 'llama',
        'choices': [{'index': 0, 'finish_reason': 'stop',
                     'message': {'role': 'assistant', **message}}],
        'usage': usage or {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10},
    }


def _sse(deltas: list[dict]) -> bytes:
    events = [
        {'id': 'c', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'llama',
         'choices': [{'index': 0, 'delta': d, 'finish_reason': None}]}
        for d in deltas
    ]
    return (''.join(f'data: {json.dumps(e)}\n\n' for e in events)
            + 'data: [DONE]\n\n').encode()


class Server:
    """Records request bodies; answers non-streamed calls with `message`."""

    def __init__(self, message: dict | None = None, deltas: list[dict] | None = None,
                 usage: dict | None = None):
        self.bodies: list[dict] = []
        self.message = message or {'content': json.dumps({'ok': True})}
        self.deltas = deltas or [{'role': 'assistant', 'content': 'fine'}]
        self.usage = usage

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if body.get('stream'):
            return httpx.Response(200, content=_sse(self.deltas),
                                  headers={'content-type': 'text/event-stream'})
        return httpx.Response(200, json=_completion(self.message, self.usage))

    def client(self) -> OpenAI:
        return OpenAI(base_url='http://thinking.test/v1', api_key='sk-no-key-needed',
                      max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(self.handle)))


class NonOpenAIClient:
    """Takes the non-instructor JSON path (not an OpenAI instance)."""

    def __init__(self, message: dict, usage=None):
        self.kwargs: list[dict] = []
        msg = SimpleNamespace(content=None, reasoning=None, reasoning_content=None)
        for k, v in message.items():
            setattr(msg, k, v)
        self.response = SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason='stop')], usage=usage)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs.append(kwargs)
        return self.response


def _switch(body: dict) -> bool | None:
    return (body.get('chat_template_kwargs') or {}).get('enable_thinking')


def _all_paths(tmp_path, options: OptionsConfig | None, kind: str | None = None):
    """Make one call on each path; return the switch each one sent."""
    server = Server()
    client = server.client()
    other = NonOpenAIClient({'content': json.dumps({'ok': True})})

    def calls():
        with llm_step('step', kind):
            get_streamed_json_response(client, Verdict, _llm_input(), max_retries=1)
            get_streamed_json_response(other, Verdict, _llm_input(), max_retries=1)
            stream_conversation(client, _llm_input())

    if options is None:
        calls()
    else:
        with thinking_session(options, turn_id='t'):
            calls()
    instructor_body, stream_body = server.bodies
    return {
        'instructor': _switch(instructor_body),
        'json': _switch(other.kwargs[0]['extra_body']),
        'stream': _switch(stream_body),
    }


def test_every_path_sends_thinking_off_by_default(tmp_path):
    assert _all_paths(tmp_path, _options(tmp_path)) == dict.fromkeys(
        ('instructor', 'json', 'stream'), False)


def test_switch_is_explicit_outside_a_session(tmp_path):
    # Calls outside an orchestrator turn still say off, not the server default.
    assert set(_all_paths(tmp_path, None).values()) == {False}


def test_every_path_sends_thinking_on(tmp_path):
    assert set(_all_paths(tmp_path, _options(tmp_path, thinking='on')).values()) == {True}


def test_per_step_override_wins(tmp_path):
    options = _options(tmp_path, thinking='off', thinking_by_step={'compose': 'on'})
    assert set(_all_paths(tmp_path, options, kind='compose').values()) == {True}
    assert set(_all_paths(tmp_path, options, kind='summary').values()) == {False}
    on = _options(tmp_path, thinking='on', thinking_by_step={'oracle': 'off'})
    assert set(_all_paths(tmp_path, on, kind='oracle').values()) == {False}


def test_unknown_step_kind_is_rejected():
    with pytest.raises(ValueError):
        with llm_step('x', 'not_a_kind'):
            pass


def test_yaml_booleans_read_as_switches():
    options = OptionsConfig.model_validate(
        {'thinking': True, 'thinking_by_step': {'compose': False}})
    assert options.thinking == 'on'
    assert options.thinking_by_step == {'compose': 'off'}


@pytest.mark.parametrize('field', ['reasoning', 'reasoning_content'])
def test_instructor_path_captures_parser_reasoning(tmp_path, field):
    server = Server(message={'content': '\n\n' + json.dumps({'ok': True}),
                             field: 'weighing it up'},
                    usage={'prompt_tokens': 7, 'completion_tokens': 9, 'total_tokens': 16,
                           'completion_tokens_details': {'reasoning_tokens': 6}})
    with thinking_session(_options(tmp_path, thinking='on'), turn_id='s1#r0:t0') as log:
        with llm_step('Compose document ops (JSON)', 'compose'):
            result = get_streamed_json_response(server.client(), Verdict, _llm_input())
    assert result.ok is True
    [record] = log.records
    assert record['text'] == 'weighing it up'
    assert record['reasoning_tokens'] == 6  # per attempt, before instructor sums usage
    assert (record['kind'], record['path'], record['setting']) == ('compose', 'instructor', 'on')
    [line] = log.path().read_text().splitlines()
    assert json.loads(line) == record
    assert log.path().name == 's1_r0_t0.jsonl'


@pytest.mark.parametrize('field', ['reasoning', 'reasoning_content'])
def test_json_path_captures_parser_reasoning(tmp_path, field):
    usage = SimpleNamespace(completion_tokens_details=SimpleNamespace(reasoning_tokens=4))
    client = NonOpenAIClient({'content': '\n\n{"ok": true}', field: 'hmm'}, usage)
    with thinking_session(_options(tmp_path, thinking='on'), turn_id='t') as log:
        assert get_streamed_json_response(client, Verdict, _llm_input()).ok is True
    [record] = log.records
    assert (record['text'], record['reasoning_tokens'], record['path']) == ('hmm', 4, 'json')


def test_json_path_strips_think_block_before_parse(tmp_path):
    # Braces inside the block would break a first-'{'-to-last-'}' parse.
    client = NonOpenAIClient({'content': '<think>is {ok} true? yes</think>\n{"ok": true}'})
    with thinking_session(_options(tmp_path, thinking='on'), turn_id='t') as log:
        result = get_streamed_json_response(client, Verdict, _llm_input(), max_retries=1)
    assert result.ok is True
    assert len(client.kwargs) == 1  # parsed first time, no retry
    assert [r['text'] for r in log.records] == ['is {ok} true? yes']


@pytest.mark.parametrize('deltas, reasoning', [
    ([{'role': 'assistant', 'reasoning_content': 'let me '},
      {'reasoning_content': 'think'}, {'content': 'A summary.'}], 'let me think'),
    ([{'role': 'assistant', 'reasoning': 'brief'}, {'content': 'A summary.'}], 'brief'),
    ([{'role': 'assistant', 'content': '<think>quiet'}, {'content': ' thoughts</think>\n\n'},
      {'content': 'A summary.'}], 'quiet thoughts'),
])
def test_stream_path_captures_reasoning_and_keeps_it_out_of_content(tmp_path, deltas, reasoning):
    server = Server(deltas=deltas)
    with thinking_session(_options(tmp_path, thinking='on'), turn_id='t') as log:
        with llm_step('Rolling summary', 'summary'):
            chunks = stream_conversation(server.client(), _llm_input())
    assert extract_content(chunks) == 'A summary.'
    [record] = log.records
    assert (record['text'], record['path'], record['kind']) == (reasoning, 'stream', 'summary')


def test_no_reasoning_writes_no_log(tmp_path):
    with thinking_session(_options(tmp_path), turn_id='t') as log:
        get_streamed_json_response(Server().client(), Verdict, _llm_input())
    assert log.records == []
    assert log.log == 'off'
    assert not any(tmp_path.iterdir())


def test_log_defaults_to_jsonl_when_any_step_thinks(tmp_path):
    with thinking_session(_options(tmp_path, thinking_by_step={'oracle': 'on'})) as log:
        assert log.log == 'jsonl'
    with thinking_session(_options(tmp_path, thinking='on', log_thinking='off')) as log:
        assert log.log == 'off'


def test_split_reasoning_shapes():
    assert split_reasoning('<think>a</think>\n\nanswer') == ('a', 'answer')
    assert split_reasoning('  <think>cut off') == ('cut off', '')
    assert split_reasoning('\n\n391') == ('', '\n\n391')
    assert split_reasoning('x <think>y</think>') == ('', 'x <think>y</think>')  # leading only
    assert split_reasoning(None) == ('', '')


class Item(BaseModel):
    name: str


def test_instructor_path_strips_think_block_before_its_parse(tmp_path):
    # instructor parses from the first '{' to the last '}'; braces inside the
    # block would break that and cost a retry.
    server = Server(message={'content': '<think>is {ok} set?</think>\n' + json.dumps({'ok': True})})
    with thinking_session(_options(tmp_path, thinking='on'), turn_id='t') as log:
        result = get_streamed_json_response(server.client(), Verdict, _llm_input(), max_retries=1)
    assert result.ok is True
    assert len(server.bodies) == 1
    assert [r['text'] for r in log.records] == ['is {ok} set?']


def test_instructor_path_logs_every_attempt(tmp_path):
    replies = iter([{'content': 'not json', 'reasoning': 'first try'},
                    {'content': json.dumps({'ok': True}), 'reasoning': 'second try'}])

    class Retrying(Server):
        def handle(self, request):
            self.message = next(replies)
            return super().handle(request)

    server = Retrying()
    with thinking_session(_options(tmp_path, thinking='on'), turn_id='t') as log:
        assert get_streamed_json_response(server.client(), Verdict, _llm_input()).ok is True
    assert [r['text'] for r in log.records] == ['first try', 'second try']
    # The retry re-sends the switch too.
    assert [_switch(b) for b in server.bodies] == [True, True]


def test_instructor_path_captures_list_models(tmp_path):
    # instructor returns list[...] results without a _raw_response.
    server = Server(message={'content': json.dumps({'content': [{'name': 'a'}]}),
                             'reasoning': 'listing'})
    with thinking_session(_options(tmp_path, thinking='on'), turn_id='t') as log:
        result = get_streamed_json_response(server.client(), list[Item], _llm_input())
    assert [i.name for i in result] == ['a']
    assert [r['text'] for r in log.records] == ['listing']
