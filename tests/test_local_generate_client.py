from reasoning_sub_agents.local_generate_client import (
    LocalGenerateClient,
    messages_to_prompt,
)
from reasoning_sub_agents.llama_utils import (
    extract_content,
    extract_message,
    generate_simple_llm_input,
    get_streamed_json_response,
)
from reasoning_sub_agents.schemas import BooleanResponse


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


def test_repair_truncated_json_array():
    from reasoning_sub_agents.llama_utils import parse_json_model
    from reasoning_sub_agents.schemas import (
        DecomposeItem,
        DecomposeSubTask,
        DecomposeThinkingStep,
    )

    truncated = (
        '[{"meta_type": "thinking", "thinking": "ok"},'
        '{"meta_type": "sub_task_detail", "name": "A", "type": "x",'
        ' "description": "d", "context": "c", "complexity": 3,'
        ' "objective": "unterminated'
    )
    result = parse_json_model(truncated, list[DecomposeItem])
    assert result
    names = [
        item.name
        for item in result
        if isinstance(item, DecomposeSubTask)
    ]
    assert names == ['A']
    assert isinstance(result[0], DecomposeThinkingStep)


def test_parse_bare_json_true_as_boolean_response():
    from reasoning_sub_agents.llama_utils import parse_json_model
    from reasoning_sub_agents.schemas import BooleanResponse

    result = parse_json_model('true', BooleanResponse)
    assert result.yes is True
    result = parse_json_model('{"yes": false}', BooleanResponse)
    assert result.yes is False


def test_json_response_without_instructor_openai_client():
    def generate(prompt, *, stream=False):
        return '{"yes": true, "reasoning": "ok"}'

    client = LocalGenerateClient(generate)
    result = get_streamed_json_response(
        llama_client=client,
        response_model=BooleanResponse,
        llm_input=generate_simple_llm_input('decide'),
        max_retries=1,
    )
    assert result.yes is True


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
