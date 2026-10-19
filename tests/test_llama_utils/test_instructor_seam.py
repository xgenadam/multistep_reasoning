"""The instrumentation seam at chat.completions.create (O-03).

The baseline harness measures every LLM call by replacing
``client.chat.completions`` on a stock ``openai.OpenAI`` client.
``instructor.from_openai`` binds ``client.chat.completions.create`` when it is
constructed, so JSON calls are only measured because
``_get_streamed_json_response_inner`` builds the instructor client per
request. These tests pin that: hoisting the construction to set-up time makes
every JSON call invisible to the harness.
"""

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import instructor
from openai import OpenAI
from pydantic import BaseModel

from reasoning_sub_agents.llama_utils import get_streamed_json_response
from reasoning_sub_agents.schemas import LLMInput, LLMMessage

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        'baseline_harness', REPO_ROOT / 'journal' / 'baseline' / 'harness.py'
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses resolve annotations here
    spec.loader.exec_module(module)
    return module


class Verdict(BaseModel):
    ok: bool


def _completion_body(content: str) -> dict:
    return {
        'id': 'chatcmpl-test',
        'object': 'chat.completion',
        'created': 0,
        'model': 'llama',
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': content},
                'finish_reason': 'stop',
            }
        ],
        'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10},
    }


def _client_over_mock_transport(requests: list[httpx.Request]) -> OpenAI:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_body(json.dumps({'ok': True})))

    return OpenAI(
        base_url='http://seam.test/v1',
        api_key='sk-no-key-needed',
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _llm_input() -> LLMInput:
    return LLMInput(messages=[LLMMessage(role='user', content='Is this fine?')])


def test_json_call_passes_through_harness_instrumentation():
    harness = _load_harness()
    requests: list[httpx.Request] = []
    client = _client_over_mock_transport(requests)
    measured = harness.install_instrumentation(client)
    assert measured is not None, 'harness refused a stock OpenAI client'

    result = get_streamed_json_response(client, Verdict, _llm_input(), max_retries=1)

    assert result.ok is True
    assert len(requests) == 1
    assert measured.total_calls == 1
    record = measured.records_between(0, 1)[0]
    assert record.prompt_tokens == 7
    assert record.completion_tokens == 3


def test_instructor_client_built_before_instrumentation_bypasses_it():
    """Why the per-request instructor.from_openai must stay."""
    harness = _load_harness()
    requests: list[httpx.Request] = []
    client = _client_over_mock_transport(requests)
    hoisted = instructor.from_openai(client, mode=instructor.Mode.JSON)
    measured = harness.install_instrumentation(client)

    result = hoisted.create(
        model='llama',
        messages=[{'role': 'user', 'content': 'Is this fine?'}],
        response_model=Verdict,
        max_retries=1,
    )

    assert result.ok is True
    assert len(requests) == 1  # the call reached the server ...
    assert measured.total_calls == 0  # ... but the harness never saw it
