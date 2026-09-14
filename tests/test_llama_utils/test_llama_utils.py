"""Test suite for reasoning_sub_agents.llama_utils module."""

import pytest
from reasoning_sub_agents.llama_utils import (
    LLMInput,
    create_llama_client,
    extract_content,
    extract_message,
    generate_simple_llm_input,
    get_chat_response,
    run_multi_concurrent,
    stream_conversation,
)


def test_create_llama_client_with_config():
    """Test creating client from config dictionary."""
    config = {'key_word_args': {'--host': '127.0.0.1', '--port': '8080'}}

    client = create_llama_client(config=config)
    assert str(client.base_url) == 'http://127.0.0.1:8080/v1/'
    assert client.api_key == 'sk-no-key-needed'


def test_create_llama_client_with_explicit_params():
    """Test creating client with explicit host and port."""
    client = create_llama_client(host='localhost', port=9000)
    assert str(client.base_url) == 'http://localhost:9000/v1/'
    assert client.api_key == 'sk-no-key-needed'


def test_create_llama_client_with_defaults():
    """Test creating client with default parameters."""
    client = create_llama_client()
    assert str(client.base_url) == 'http://127.0.0.1:5000/v1/'
    assert client.api_key == 'sk-no-key-needed'


def test_create_llama_client_config_priority():
    """Test that config parameters take priority over explicit parameters."""
    config = {'key_word_args': {'--host': '192.168.1.1', '--port': '8080'}}
    client = create_llama_client(config=config, host='localhost', port=9000)
    assert str(client.base_url) == 'http://192.168.1.1:8080/v1/'


def test_create_llama_client_missing_port():
    """Test error handling when port is missing from config."""
    config = {
        'key_word_args': {
            '--host': '127.0.0.1'
            # No port
        }
    }

    with pytest.raises(ValueError, match='--port not specified'):
        create_llama_client(config=config)


def test_create_llama_client_invalid_port():
    """Test error handling when port is invalid."""
    config = {'key_word_args': {'--host': '127.0.0.1', '--port': 'invalid'}}

    with pytest.raises(ValueError, match='Invalid --port value'):
        create_llama_client(config=config)


def test_generate_simple_llm_input():
    """Test generating simple LLM input with objective."""
    prompt = 'Hello, how are you?'
    llm_input = generate_simple_llm_input(prompt)

    assert isinstance(llm_input, LLMInput)
    assert len(llm_input.messages) == 2

    # Check system message
    system_msg = llm_input.messages[0]
    assert system_msg.role == 'system'
    assert 'You are a helpful assistant.' in system_msg.content
    from reasoning_sub_agents.agent_detect import INNER_SKIP_SENTINEL

    assert INNER_SKIP_SENTINEL in system_msg.content

    # Check user message
    user_msg = llm_input.messages[1]
    assert user_msg.role == 'user'
    assert user_msg.content == prompt


def test_extract_content_non_streaming():
    """Test extracting content from non-streaming ChatCompletion."""
    # Use MockChatCompletion for testing
    from tests.mock_openai import MockChatCompletion, MockChoice, MockMessage

    response = MockChatCompletion(
        choices=[
            MockChoice(
                message=MockMessage(content='  Hello, world!  ', role='assistant')
            )
        ]
    )

    content = extract_content(response)
    assert content == 'Hello, world!'


def test_extract_content_streaming_iterator(mock_openai_client):
    """Test extracting content from streaming response (iterator)."""
    # Set up mock streaming response
    mock_openai_client.set_return_values(['Hello, ', 'world!'])

    # Get the iterator (simulate streaming)
    response = mock_openai_client.chat.completions.create(
        model='gpt-3.5-turbo',
        messages=[{'role': 'user', 'content': 'Hello'}],
        stream=True,
    )

    content = extract_content(response)
    assert content == 'Hello, world!'


def test_extract_content_streaming_list():
    """Test extracting content from pre-collected list of chunks."""
    # Use MockChatCompletionChunk for testing
    from tests.mock_openai import MockChatCompletionChunk, MockChoice, MockDelta

    chunks = [
        MockChatCompletionChunk(
            choices=[MockChoice(delta=MockDelta(content='Hello, '))]
        ),
        MockChatCompletionChunk(
            choices=[MockChoice(delta=MockDelta(content='world!'))]
        ),
    ]

    content = extract_content(chunks)
    assert content == 'Hello, world!'


def test_extract_content_empty_response():
    """Test extracting content from response with empty content."""
    # Use MockChatCompletion for testing
    from tests.mock_openai import MockChatCompletion, MockChoice, MockMessage

    response = MockChatCompletion(
        choices=[MockChoice(message=MockMessage(content='', role='assistant'))]
    )

    content = extract_content(response)
    assert content == ''


def test_extract_content_no_content():
    """Test extracting content when choices have no content."""
    # Use MockChatCompletion for testing
    from tests.mock_openai import MockChatCompletion, MockChoice, MockMessage

    response = MockChatCompletion(
        choices=[MockChoice(message=MockMessage(content=None, role='assistant'))]
    )

    content = extract_content(response)
    assert content == ''


def test_extract_message_non_streaming():
    """Test extracting full message from non-streaming response."""
    # Use MockChatCompletion for testing
    from tests.mock_openai import MockChatCompletion, MockChoice, MockMessage

    response = MockChatCompletion(
        choices=[
            MockChoice(message=MockMessage(content='Test content', role='assistant'))
        ]
    )

    message = extract_message(response)
    assert message.role == 'assistant'
    assert message.content == 'Test content'


def test_extract_message_streaming():
    """Test extracting message from streaming response."""
    # Use MockChatCompletionChunk for testing
    from tests.mock_openai import MockChatCompletionChunk, MockChoice, MockDelta

    chunks = [
        MockChatCompletionChunk(choices=[MockChoice(delta=MockDelta(content='Part '))]),
        MockChatCompletionChunk(choices=[MockChoice(delta=MockDelta(content='one'))]),
        MockChatCompletionChunk(
            choices=[MockChoice(delta=MockDelta(content=', part two!'))]
        ),
    ]

    message = extract_message(chunks)
    assert message.role == 'assistant'
    assert message.content == 'Part one, part two!'


def test_extract_message_empty_content():
    """Test extracting message when content is empty after stripping."""
    # Use MockChatCompletionChunk for testing
    from tests.mock_openai import MockChatCompletionChunk, MockChoice, MockDelta

    chunks = [
        MockChatCompletionChunk(choices=[MockChoice(delta=MockDelta(content='   '))])
    ]

    message = extract_message(chunks)
    assert message.content is None


def test_get_chat_response():
    """Test simple chat response extraction."""
    # Use MockChatCompletion for testing
    from tests.mock_openai import MockChatCompletion, MockChoice, MockMessage

    completion = MockChatCompletion(
        choices=[
            MockChoice(message=MockMessage(content='First message', role='assistant')),
            MockChoice(message=MockMessage(content='Second message', role='assistant')),
        ]
    )

    # Default choice_idx = 0
    content = get_chat_response(completion)
    assert content == 'First message'

    # Custom choice_idx
    content = get_chat_response(completion, choice_idx=1)
    assert content == 'Second message'


def test_stream_conversation_with_callbacks(mock_openai_client):
    """Test streaming conversation with callbacks."""
    callback_results = []

    def test_callback(chunk):
        callback_results.append(chunk)

    # Set up mock streaming response
    mock_openai_client.set_return_values(['Chunk1', 'Chunk2', 'Chunk3'])

    chunks = stream_conversation(
        llama_client=mock_openai_client,
        llm_input=generate_simple_llm_input('Test objective'),
        callbacks=[test_callback],
    )

    # Should get 3 chunks
    assert len(chunks) == 3
    assert len(callback_results) == 3

    # Verify callback was called with chunks (mock objects)
    for chunk in callback_results:
        assert hasattr(chunk, 'choices')  # Mock chunks have choices attribute


def test_stream_conversation_no_callbacks(mock_openai_client):
    """Test streaming conversation without callbacks."""
    mock_openai_client.set_return_values(['Single chunk'])

    chunks = stream_conversation(
        llama_client=mock_openai_client,
        llm_input=generate_simple_llm_input('Test'),
        callbacks=None,
    )

    assert len(chunks) == 1


def test_stream_conversation_callback_errors(mock_openai_client):
    """Test that callback errors don't interrupt streaming."""

    def failing_callback(chunk):
        raise ValueError('Callback error')

    mock_openai_client.set_return_values(['Chunk1', 'Chunk2'])

    # Should still complete despite callback errors
    chunks = stream_conversation(
        llama_client=mock_openai_client,
        llm_input=generate_simple_llm_input('Test'),
        callbacks=[failing_callback],
    )

    assert len(chunks) == 2


def test_run_multi_concurrent_success(mock_openai_client):
    """Test running multiple conversations concurrently."""

    def simple_processor(client, llm_input):
        return 'processed'

    llm_inputs = {
        'convo1': generate_simple_llm_input('Prompt 1'),
        'convo2': generate_simple_llm_input('Prompt 2'),
        'convo3': generate_simple_llm_input('Prompt 3'),
    }

    shared_results = {}

    def shared_callback(convo_id, result):
        shared_results[convo_id] = result

    results = run_multi_concurrent(
        llama_client=mock_openai_client,
        llm_inputs=llm_inputs,
        processor=simple_processor,
        shared_callbacks=[shared_callback],
    )

    # Check results
    assert len(results) == 3
    assert results['convo1'] == 'processed'
    assert results['convo2'] == 'processed'
    assert results['convo3'] == 'processed'

    # Check shared callbacks were called
    assert len(shared_results) == 3


def test_run_multi_concurrent_with_exception(mock_openai_client):
    """Test that exceptions in processor are properly raised."""

    def failing_processor(client, llm_input):
        if llm_input.messages[1].content == 'Prompt 2':
            raise ValueError('Test error')
        return 'success'

    llm_inputs = {
        'convo1': generate_simple_llm_input('Prompt 1'),
        'convo2': generate_simple_llm_input('Prompt 2'),
        'convo3': generate_simple_llm_input('Prompt 3'),
    }

    with pytest.raises(RuntimeError, match="Conversation 'convo2' failed"):
        run_multi_concurrent(
            llama_client=mock_openai_client,
            llm_inputs=llm_inputs,
            processor=failing_processor,
        )


def test_run_multi_concurrent_empty_inputs(mock_openai_client):
    """Test with empty llm_inputs dictionary."""

    def dummy_processor(client, llm_input):
        return 'result'

    results = run_multi_concurrent(
        llama_client=mock_openai_client, llm_inputs={}, processor=dummy_processor
    )

    assert results == {}


def test_maybe_log_prompt_off_by_default(caplog):
    from reasoning_sub_agents.llama_utils import maybe_log_prompt, prompt_logging

    llm_input = generate_simple_llm_input('SECRET SUB-TASK OBJECTIVE')
    with caplog.at_level('INFO', logger='reasoning_sub_agents.llama_utils'):
        maybe_log_prompt(llm_input, kind='JSON')
    assert 'SECRET SUB-TASK OBJECTIVE' not in caplog.text
    with prompt_logging(True), caplog.at_level(
        'INFO', logger='reasoning_sub_agents.llama_utils'
    ):
        maybe_log_prompt(llm_input, kind='JSON')
    assert 'SECRET SUB-TASK OBJECTIVE' in caplog.text
