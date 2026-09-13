from reasoning_sub_agents.local_generate_client import (
    LocalGenerateClient,
    messages_to_prompt,
)
from reasoning_sub_agents.llama_utils import extract_content, extract_message


def test_messages_to_prompt():
    prompt = messages_to_prompt(
        [
            {'role': 'system', 'content': 'Be brief.'},
            {'role': 'user', 'content': 'Hello'},
        ]
    )
    assert 'system: Be brief.' in prompt
    assert 'user: Hello' in prompt
    assert prompt.endswith('assistant:')


def test_non_streaming_create():
    def generate(prompt, *, stream=False):
        assert 'Hello' in prompt
        assert stream is False
        return 'Hi there'

    client = LocalGenerateClient(generate)
    completion = client.chat.completions.create(
        model='llama',
        messages=[{'role': 'user', 'content': 'Hello'}],
        stream=False,
        timeout=3600,
    )
    assert extract_message(completion).content == 'Hi there'


def test_streaming_create_yields_deltas():
    def generate(prompt, *, stream=False):
        assert stream is True
        yield 'Hel'
        yield 'lo'

    client = LocalGenerateClient(generate)
    chunks = list(
        client.chat.completions.create(
            model='llama',
            messages=[{'role': 'user', 'content': 'Hi'}],
            stream=True,
        )
    )
    assert extract_content(chunks) == 'Hello'
