import json
import logging
import re
import threading
import types
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar, get_args, get_origin

import instructor
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessage
from pydantic import TypeAdapter

from .agent_detect import INNER_SKIP_SENTINEL
from .progress import begin_llm
from .schemas import BooleanResponse, ChatResponse, LLMInput, LLMMessage

_json_completion: ContextVar[bool] = ContextVar('json_completion', default=False)
_inner_token_limit: ContextVar[int | None] = ContextVar(
    'inner_token_limit', default=None
)
_log_prompts: ContextVar[bool] = ContextVar('log_prompts', default=False)


def json_completion_active() -> bool:
    """True while get_streamed_json_response is running (inner JSON, not prose)."""
    return _json_completion.get()


def log_prompts_enabled() -> bool:
    """True when orchestrator.yaml options.log_prompts is on."""
    return _log_prompts.get()


@contextmanager
def prompt_logging(enabled: bool):
    token = _log_prompts.set(bool(enabled))
    try:
        yield
    finally:
        _log_prompts.reset(token)


def maybe_log_prompt(llm_input: LLMInput, *, kind: str) -> None:
    if not _log_prompts.get():
        return
    parts = [
        f'[{message.role}]\n{message.content or ""}'
        for message in llm_input.messages
    ]
    blob = '\n\n'.join(parts)
    logger.info('LLM %s prompt (%s chars):\n%s', kind, len(blob), blob)


def inner_token_limit() -> int | None:
    """Optional max_new_tokens for the current inner generate (JSON/critique)."""
    return _inner_token_limit.get()


@contextmanager
def limited_inner_tokens(max_new_tokens: int):
    token = _inner_token_limit.set(max_new_tokens)
    try:
        yield
    finally:
        _inner_token_limit.reset(token)

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
        LLMMessage(
            **{
                'role': 'system',
                'content': f'{INNER_SKIP_SENTINEL} You are a helpful assistant.',
            }
        ),
        LLMMessage(**{'role': 'user', 'content': prompt}),
    ]
    return LLMInput(messages=messages)


def with_inner_sentinel(llm_input: LLMInput) -> LLMInput:
    """Tag orchestrator LLM calls so oobabooga will not intercept them."""
    messages = list(llm_input.messages)
    if not messages:
        return LLMInput(
            messages=[
                LLMMessage(role='system', content=INNER_SKIP_SENTINEL),
            ]
        )
    first = messages[0]
    content = first.content or ''
    if INNER_SKIP_SENTINEL in content:
        return llm_input
    if first.role == 'system':
        messages[0] = LLMMessage(
            role='system', content=f'{INNER_SKIP_SENTINEL} {content}'
        )
    else:
        messages.insert(0, LLMMessage(role='system', content=INNER_SKIP_SENTINEL))
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


def get_streamed_json_response(
    llama_client: OpenAI,
    response_model: Any,
    llm_input: LLMInput,
    partial_callbacks: list[Callable[[Any], None]] | None = None,
    max_retries: int = 5,
    instructor_kwargs: dict[str, Any] | None = None,
) -> T:
    if partial_callbacks is None:
        partial_callbacks = []
    begin_llm('JSON completion')
    maybe_log_prompt(llm_input, kind='JSON')
    json_token = _json_completion.set(True)
    limit_token = _inner_token_limit.set(_inner_token_limit.get() or 2048)
    try:
        return _get_streamed_json_response_inner(
            llama_client,
            response_model,
            llm_input,
            partial_callbacks,
            max_retries,
            instructor_kwargs,
        )
    finally:
        _json_completion.reset(json_token)
        _inner_token_limit.reset(limit_token)


def _get_streamed_json_response_inner(
    llama_client: OpenAI,
    response_model: Any,
    llm_input: LLMInput,
    partial_callbacks: list[Callable[[Any], None]],
    max_retries: int,
    instructor_kwargs: dict[str, Any] | None,
) -> T:
    messages = [
        msg.model_dump() for msg in with_inner_sentinel(llm_input).messages
    ]
    instructor_kwargs = instructor_kwargs or {}

    if isinstance(llama_client, OpenAI):
        instr_client = instructor.from_openai(
            llama_client,
            mode=instructor.Mode.JSON,
        )
        if instr_client is not None and callable(getattr(instr_client, 'create', None)):
            response = instr_client.create(
                model='llama',
                messages=messages,
                response_model=response_model,
                max_retries=max_retries,
                timeout=3600,
                **instructor_kwargs,
            )
            return _finalize_instructor_response(response, partial_callbacks)

    last_error: Exception | None = None
    for attempt in range(max(1, max_retries)):
        try:
            completion = llama_client.chat.completions.create(
                model='llama',
                messages=messages,
                stream=False,
                timeout=3600,
            )
            content = extract_message(completion).content or ''
            final_model = parse_json_model(content, response_model)
            for callback in partial_callbacks:
                try:
                    callback(final_model)
                except Exception as exc:
                    logger.error('Full model callback error: %s', exc)
            return final_model
        except Exception as exc:
            last_error = exc
            logger.warning(
                'JSON parse attempt %s/%s failed: %s',
                attempt + 1,
                max_retries,
                exc,
            )
            messages = list(messages) + [
                {
                    'role': 'user',
                    'content': (
                        'Your previous reply was not valid JSON for the schema. '
                        f'Error: {exc}. Reply with JSON only.'
                    ),
                }
            ]
    raise last_error or ValueError('JSON response failed')


def parse_json_model(content: str, response_model: Any) -> Any:
    """Parse model text (optionally fenced) into a Pydantic object or list."""
    text = (content or '').strip()
    fenced = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fenced:
        text = fenced.group(1).strip()
    else:
        for idx, char in enumerate(text):
            if char in '{[':
                text = text[idx:]
                break
    data = _loads_json(text)
    data = _coerce_response_data(data, response_model)
    try:
        return TypeAdapter(response_model).validate_python(data)
    except Exception:
        salvaged = _salvage_list_items(data, response_model)
        if salvaged is not None:
            return salvaged
        raise


def _loads_json(text: str) -> Any:
    try:
        data, _end = json.JSONDecoder().raw_decode(text)
        return data
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_repair_truncated_json(text))


def _repair_truncated_json(text: str) -> str:
    """Close an unterminated string and unmatched braces/brackets after a token cap."""
    in_string = False
    escape = False
    stack: list[str] = []
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            stack.append('}')
        elif char == '[':
            stack.append(']')
        elif char in '}]' and stack:
            stack.pop()
    if in_string:
        text += '"'
    text = text.rstrip()
    if text.endswith(','):
        text = text[:-1]
    while stack:
        text += stack.pop()
    return text


def _salvage_list_items(data: Any, response_model: Any) -> Any | None:
    if get_origin(response_model) is not list or not isinstance(data, list):
        return None
    inner = get_args(response_model)[0]
    kept = []
    for item in data:
        try:
            kept.append(TypeAdapter(inner).validate_python(item))
        except Exception:
            continue
    return kept or None


_DECOMPOSE_META_ALIASES = {
    'thinking': 'thinking_step',
    'thought': 'thinking_step',
    'thinking_step': 'thinking_step',
    'sub_task': 'sub_task_detail',
    'subtask': 'sub_task_detail',
    'task': 'sub_task_detail',
    'sub_task_detail': 'sub_task_detail',
}


def _coerce_response_data(data: Any, response_model: Any) -> Any:
    """Accept a bare JSON bool when the schema is BooleanResponse {yes: bool}."""
    if get_origin(response_model) is list and isinstance(data, list):
        return [_normalize_item_meta_type(item) for item in data]
    is_boolean = response_model is BooleanResponse or (
        isinstance(response_model, type)
        and issubclass(response_model, BooleanResponse)
    )
    if not is_boolean:
        return data
    if isinstance(data, bool):
        return {'yes': data}
    if isinstance(data, str) and data.lower() in {'true', 'false', 'yes', 'no'}:
        return {'yes': data.lower() in {'true', 'yes'}}
    if isinstance(data, dict) and 'yes' not in data:
        for key in ('value', 'result', 'decision', 'regenerate'):
            if key in data and isinstance(data[key], bool):
                return {'yes': data[key]}
    return data


def _normalize_item_meta_type(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    meta = item.get('meta_type')
    if not isinstance(meta, str):
        return item
    alias = _DECOMPOSE_META_ALIASES.get(meta.strip().lower())
    if alias is None or alias == meta:
        return item
    normalized = dict(item)
    normalized['meta_type'] = alias
    return normalized


def _finalize_instructor_response(
    response: Any, partial_callbacks: list[Callable[[Any], None]]
) -> Any:
    if isinstance(response, types.GeneratorType):
        final_model: Any = None
        for partial_model in response:
            for callback in partial_callbacks:
                try:
                    callback(partial_model)
                except Exception as exc:
                    logger.error('Partial callback error: %s', exc)
            final_model = partial_model
        if final_model is None:
            raise ValueError('Stream completed without any output')
        return final_model
    for callback in partial_callbacks:
        try:
            callback(response)
        except Exception as exc:
            logger.error('Full model callback error: %s', exc)
    return response


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
    begin_llm('stream completion')
    maybe_log_prompt(llm_input, kind='stream')

    standard_messages = [
        msg.model_dump() for msg in with_inner_sentinel(llm_input).messages
    ]

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


def run_multi_concurrent(
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
