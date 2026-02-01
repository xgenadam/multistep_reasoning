import logging
import threading
from collections.abc import Callable, Iterator
from typing import Any, TypeVar
import types

import instructor
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessage

from .schemas import BooleanResponse, ChatResponse, LLMInput, LLMMessage

logger = logging.getLogger(__name__)

R = TypeVar('R')
Processor = Callable[[OpenAI, LLMInput], R]


def create_llama_client(
    config: dict | None = None, *, host: str | None = None, port: int | None = None
) -> OpenAI:
    """
    Creates and returns an OpenAI-compatible client for the llama.cpp server.

    Priority:
    - If config is provided, host/port are extracted from it.
    - Otherwise, use explicit host/port arguments.
    - Defaults: host="127.0.0.1", port=5000

    Example:
        client = create_llama_client(config=my_config)
        client = create_llama_client(host="127.0.0.1", port=5000)
    """
    if config is not None:
        host = config['key_word_args'].get('--host', '127.0.0.1')
        port_str = config['key_word_args'].get('--port')
        if port_str is None:
            raise ValueError("--port not specified in config['key_word_args']")
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f'Invalid --port value in config: {port_str}')

    if host is None:
        host = '127.0.0.1'
    if port is None:
        port = 5000

    base_url = f'http://{host}:{port}/v1'
    logger.info('Creating OpenAI client for server at %s', base_url)

    client = OpenAI(base_url=base_url, api_key='sk-no-key-needed')
    return client


def generate_simple_llm_input(prompt: str) -> LLMInput:
    messages = [
        LLMMessage(**{'role': 'system', 'content': 'You are a helpful assistant.'}),
        LLMMessage(**{'role': 'user', 'content': prompt}),
    ]
    return LLMInput(messages=messages)


def extract_content(response: ChatResponse) -> str:
    """
    Extracts the full assistant message content from either:
    - A non-streaming ChatCompletion
    - An iterator of ChatCompletionChunk (streaming, not yet consumed)
    - A pre-collected list of ChatCompletionChunk

    Returns the complete content string.
    """
    content = ''

    # Duck typing: check if it has choices with message (non-streaming)
    if hasattr(response, 'choices') and len(response.choices) > 0:
        choice = response.choices[0]
        if hasattr(choice, 'message') and choice.message.content:
            content = choice.message.content
        return content.strip()

    # Streaming case: handle iterator or list uniformly
    chunks: Iterator[ChatCompletionChunk]
    if isinstance(response, list):
        chunks = iter(response)  # Treat list as iterable
    else:
        chunks = response  # Assume it's the iterator

    for chunk in chunks:
        delta = chunk.choices[0].delta
        if delta.content is not None:
            content += delta.content

    return content.strip()


def extract_message(response: ChatResponse) -> ChatCompletionMessage:
    """
    Extracts a full ChatCompletionMessage object (with role/content/tool_calls etc.)
    from either non-streaming or streaming response.

    For streaming, accumulates deltas into a single message.
    """
    # Duck typing: check if it has choices with message (non-streaming)
    if (
        hasattr(response, 'choices')
        and len(response.choices) > 0
        and hasattr(response.choices[0], 'message')
    ):
        return response.choices[0].message

    # Streaming accumulation
    accumulated = ChatCompletionMessage(role='assistant', content='')
    # tool_calls = []  # If you need tool_calls accumulation, expand here

    chunks = response if isinstance(response, list) else response
    for chunk in chunks:
        delta = chunk.choices[0].delta
        if delta.content is not None:
            accumulated.content += delta.content
        # Handle tool_calls delta accumulation if needed
        if hasattr(delta, 'tool_calls') and delta.tool_calls:
            # Tool call accumulation is more complex (index-based merging)
            # See OpenAI docs/cookbook for full example if you use tools
            pass

    accumulated.content = accumulated.content.strip() or None
    return accumulated


T = TypeVar('T')


def get_streamed_json_response[T](
    llama_client: OpenAI,
    response_model: Any,
    llm_input: LLMInput,
    partial_callbacks: list[Callable[[Any], None]] | None = None,
    max_retries: int = 5,
    instructor_kwargs: dict[str, Any] | None = None,
) -> T:
    if partial_callbacks is None:
        partial_callbacks = []

    instr_client = instructor.from_openai(
        llama_client,
        mode=instructor.Mode.JSON,
    )

    messages = [msg.model_dump() for msg in llm_input.messages]
    instructor_kwargs = instructor_kwargs or {}

    response = instr_client.create(
        model='llama',
        messages=messages,
        response_model=response_model,
        # stream=True,
        max_retries=max_retries,
        timeout=3600,
        **instructor_kwargs,
    )

    if isinstance(response, types.GeneratorType):
        final_model: Any = None
        for partial_model in response:
            for callback in partial_callbacks:
                try:
                    callback(partial_model)
                except Exception as e:
                    logger.error(f'Partial callback error: {e}')

            final_model = partial_model

        if final_model is None:
            raise ValueError('Stream completed without any output')
    else:
        final_model = response
        for callback in partial_callbacks:
            try:
                callback(final_model)
            except Exception as e:
                logger.error(f'Full model callback error: {e}')

    return final_model


def get_streamed_boolean_decision(
    llama_client: OpenAI,
    llm_input: LLMInput,
    partial_callbacks: list[Callable[[BooleanResponse], None]] | None = None,
) -> bool:
    """
    Streams a boolean decision using BooleanResponse schema.
    Supports partial callbacks (receiving partial BooleanResponse models).
    Returns the final boolean value.
    """
    final_model = get_streamed_json_response(
        llama_client=llama_client,
        response_model=BooleanResponse,
        llm_input=llm_input,
        partial_callbacks=partial_callbacks or [],
    )
    return final_model.yes


def get_chat_response(completion: ChatCompletion, choice_idx: int = 0) -> str:
    return completion.choices[choice_idx].message.content


def stream_conversation(
    llama_client: OpenAI,
    llm_input: LLMInput,
    callbacks: list[Callable[[ChatCompletionChunk], None]] | None = None,
) -> list[ChatCompletionChunk]:
    """
    Streams a single conversation, calls real-time callbacks on each chunk,
    and returns the collected chunks for post-processing.

    callbacks: Optional list of callables that take a ChatCompletionChunk
               and perform side-effects (e.g., print, update UI, queue).
               Defaults to empty list (no callbacks).
    """
    if callbacks is None:
        callbacks = []

    standard_messages = [msg.model_dump() for msg in llm_input.messages]

    # TODO: timeout = none is not ideal, but when we send lots of tasks and they
    #  get processed sequentially this causes a timeout. for now setting it to None
    #  is good enough
    stream = llama_client.chat.completions.create(
        model='llama', messages=standard_messages, stream=True, timeout=3600
    )

    chunks: list[ChatCompletionChunk] = []
    for chunk in stream:
        # Real-time processing via callbacks
        for callback in callbacks:
            try:
                callback(chunk)
            except Exception as e:
                # Optional: log or ignore callback errors to not interrupt streaming
                print(f'Callback error: {e}')

        chunks.append(chunk)

    return chunks


def run_multi_concurrent[R](
    llama_client: OpenAI,
    llm_inputs: dict[str, LLMInput],
    processor: Processor[R],
    shared_callbacks: list[Callable[[str, Any], None]] | None = None,
) -> dict[str, R]:
    """
    Generic concurrent runner for multiple conversations.

    processor: Callable that handles ONE conversation (llama_client, llm_input) -> result R
    shared_callbacks: Optional real-time callbacks receiving (convo_id, intermediate_value)
    """
    if shared_callbacks is None:
        shared_callbacks = []

    results: dict[str, R] = {}
    lock = threading.Lock()

    def target(convo_id: str, llm_input: LLMInput):
        try:
            # If processor supports callbacks, pass wrapped ones here (omitted for brevity)
            result = processor(llama_client, llm_input)

            # Example real-time callback (adapt based on processor output)
            for cb in shared_callbacks:
                cb(convo_id, result)  # Or pass intermediates if processor yields them

            with lock:
                results[convo_id] = result
        except Exception as e:
            with lock:
                results[convo_id] = e

    threads = {
        convo_id: threading.Thread(target=target, args=(convo_id, llm_input))
        for convo_id, llm_input in llm_inputs.items()
    }

    for thread in threads.values():
        thread.start()
    for thread in threads.values():
        thread.join()

    for convo_id, res in results.items():
        if isinstance(res, Exception):
            raise RuntimeError(f"Conversation '{convo_id}' failed: {res}")

    return results
