"""
Test the mock OpenAI client fixture.
And provide examples of how to use it for future developers
"""
import pytest

from mock_openai import MockChatCompletion, MockChatCompletionChunk, MockChoice, MockMessage, MockDelta

def test_mock_openai_non_streaming(mock_openai_client):
    """Test non-streaming chat completion."""
    # Set a simple string return value
    mock_openai_client.set_return_values("Hello, world!")

    # Test regular call
    result = mock_openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}]
    )

    # Result should be a MockChatCompletion object
    assert isinstance(result, MockChatCompletion)
    assert len(result.choices) == 1
    assert result.choices[0].message.content == "Hello, world!"
    assert result.choices[0].finish_reason == "stop"

def test_mock_openai_streaming_with_string(mock_openai_client):
    """Test streaming with auto-split string."""
    # Set a string that will be auto-split into chunks
    mock_openai_client.set_return_values("Hello, world!")

    # Test stream call
    stream_results = list(mock_openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        stream=True
    ))

    # Should get multiple chunks (auto-split at ~10 chars)
    assert len(stream_results) > 1
    assert all(isinstance(chunk, MockChatCompletionChunk) for chunk in stream_results)

    # Reconstruct full message from chunks
    full_content = ""
    for chunk in stream_results:
        assert len(chunk.choices) == 1
        if chunk.choices[0].delta and chunk.choices[0].delta.content:
            full_content += chunk.choices[0].delta.content

    assert full_content == "Hello, world!"
    # Last chunk should have finish_reason="stop"
    assert stream_results[-1].choices[0].finish_reason == "stop"

def test_mock_openai_streaming_with_explicit_chunks(mock_openai_client):
    """Test streaming with explicitly defined chunks."""
    # Set explicit chunk strings
    mock_openai_client.set_return_values(["hello", " world", "!"])

    # Test stream call
    stream_results = list(mock_openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        stream=True
    ))

    assert len(stream_results) == 3
    assert stream_results[0].choices[0].delta.content == "hello"
    assert stream_results[1].choices[0].delta.content == " world"
    assert stream_results[2].choices[0].delta.content == "!"
    assert stream_results[2].choices[0].finish_reason == "stop"

def test_mock_openai_multiple_calls(mock_openai_client):
    """Test multiple successive calls with different return values."""
    # Set multiple return values for successive calls
    mock_openai_client.set_return_values("First response", "Second response")

    # First call
    result1 = mock_openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "First"}]
    )
    assert result1.choices[0].message.content == "First response"

    # Second call
    result2 = mock_openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Second"}]
    )
    assert result2.choices[0].message.content == "Second response"

def test_mock_openai_error(mock_openai_client):
    """Test that exceptions can be raised."""
    # Set an exception to be raised
    mock_openai_client.set_return_values(ValueError("API error"))

    with pytest.raises(ValueError, match="API error"):
        mock_openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Error"}]
        )

def test_mock_openai_custom_objects(mock_openai_client):
    """Test using custom MockChatCompletion objects."""
    # Create custom response
    custom_response = MockChatCompletion(
        choices=[MockChoice(
            message=MockMessage(content="Custom message", role="assistant")
        )]
    )
    mock_openai_client.set_return_values(custom_response)

    # Test call
    result = mock_openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Custom"}]
    )

    assert result is custom_response
    assert result.choices[0].message.content == "Custom message"
    assert result.choices[0].message.role == "assistant"

def test_mock_openai_custom_streaming_objects(mock_openai_client):
    """Test using custom MockChatCompletionChunk objects for streaming."""
    # Create custom streaming chunks
    custom_chunks = [
        MockChatCompletionChunk(
            choices=[MockChoice(delta=MockDelta(content="custom"), finish_reason=None)]
        ),
        MockChatCompletionChunk(
            choices=[MockChoice(delta=MockDelta(content=" chunks"), finish_reason="stop")]
        )
    ]
    mock_openai_client.set_return_values(custom_chunks)

    # Test stream call
    stream_results = list(mock_openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Custom stream"}],
        stream=True
    ))

    assert len(stream_results) == 2
    assert stream_results[0].choices[0].delta.content == "custom"
    assert stream_results[1].choices[0].delta.content == " chunks"
    assert stream_results[1].choices[0].finish_reason == "stop"

def test_mock_openai_no_more_responses(mock_openai_client):
    """Test that calling without set_return_values raises RuntimeError."""
    with pytest.raises(RuntimeError, match="No more mock responses available"):
        mock_openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "No response set"}]
        )
