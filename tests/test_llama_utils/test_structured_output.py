"""options.structured_output (the user, 2026-10-25): what each mode sends, and
the per-turn JSON-call counts on the token meter."""

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI
from pydantic import BaseModel

from reasoning_sub_agents import llama_utils as L
from reasoning_sub_agents.schemas import LLMInput, LLMMessage


class Answer(BaseModel):
    title: str
    count: int


class Server:
    """Replies from a script: each entry is the content of one completion."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        content = self.replies.pop(0)
        return httpx.Response(200, json={
            'id': 'x', 'object': 'chat.completion', 'created': 0, 'model': 'm',
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': content}}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8}})


def _call(server, mode, max_retries=3):
    client = OpenAI(base_url='http://t/v1', api_key='x', max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(server.handle)))
    options = SimpleNamespace(structured_output=mode, structured_output_by_step={})
    with L.structured_output_session(options), L.token_meter() as meter:
        try:
            result = L.get_streamed_json_response(
                client, Answer, LLMInput(messages=[LLMMessage(role='user', content='Name it.')]),
                max_retries=max_retries)
        except Exception as exc:  # noqa: BLE001 - the counts are what is checked
            result = exc
    return result, meter.json_calls['other']


GOOD = '{"title": "t", "count": 2}'


def test_json_object_is_the_default_and_counts_one_attempt():
    server = Server([GOOD])
    result, stats = _call(server, 'json_object')
    assert result.model_dump() == {'title': 't', 'count': 2}
    assert server.requests[0]['response_format'] == {'type': 'json_object'}
    assert stats == {'mode': 'json_object', 'calls': 1, 'attempts': 1, 'failed': 0}


def test_json_schema_forces_the_parsed_models_schema():
    server = Server([GOOD])
    result, stats = _call(server, 'json_schema')
    assert result.count == 2
    fmt = server.requests[0]['response_format']
    assert fmt['type'] == 'json_schema'
    assert fmt['json_schema']['schema']['required'] == ['title', 'count']
    assert stats['mode'] == 'json_schema' and stats['attempts'] == 1


def test_two_pass_writes_prose_then_converts_it_under_the_schema():
    server = Server(['# Title\nt\n# Count\n2', GOOD])
    result, stats = _call(server, 'two_pass')
    assert result.model_dump() == {'title': 't', 'count': 2}
    prose, convert = server.requests
    assert 'response_format' not in prose
    assert prose['messages'][-1]['content'].startswith('Before any JSON')
    assert '"count"' in prose['messages'][-1]['content']  # it is told the structure
    assert convert['response_format']['type'] == 'json_schema'
    roles = [m['role'] for m in convert['messages']]
    assert roles[-2:] == ['assistant', 'user']
    assert convert['messages'][-2]['content'] == '# Title\nt\n# Count\n2'
    assert convert['messages'][-1]['content'] == L.TWO_PASS_CONVERT_PROMPT
    assert stats['attempts'] == 1  # the prose call is not a JSON attempt


def test_retries_and_failures_are_counted():
    _, stats = _call(Server(['not json', GOOD]), 'json_object')
    assert stats['attempts'] == 2 and stats['failed'] == 0
    result, stats = _call(Server(['nope'] * 3), 'json_object', max_retries=3)
    assert isinstance(result, Exception)
    assert stats['attempts'] == 3 and stats['failed'] == 1


def test_options_accept_the_modes():
    from reasoning_sub_agents.config.schema import OptionsConfig
    opts = OptionsConfig(structured_output='two_pass', structured_output_by_step={'compose': 'json_schema'})
    assert opts.structured_output == 'two_pass'
    with pytest.raises(ValueError):
        OptionsConfig(structured_output='grammar')
