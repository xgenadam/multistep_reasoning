import json
import logging
import os
import re
import threading
import types
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin

import instructor
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessage
from pydantic import TypeAdapter

from .agent_detect import INNER_SKIP_SENTINEL
from .progress import begin_llm, current_step_kind, live
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


# ---------------------------------------------------------------------------
# Thinking (D-013): an explicit switch on every call, reasoning captured and
# logged out of band. Nothing here is read back by a prompt builder, the
# summary or the composer.
# ---------------------------------------------------------------------------


@dataclass
class ThinkingLog:
    """One orchestrator turn's thinking setting and its captured reasoning."""

    setting: str = 'off'
    by_step: dict[str, str] = field(default_factory=dict)
    log: str = 'off'  # 'off' | 'jsonl'
    log_dir: str = 'runs/thinking'
    turn_id: str = ''
    records: list[dict] = field(default_factory=list)

    def path(self) -> Path:
        safe = re.sub(r'[^A-Za-z0-9._-]+', '_', self.turn_id) or 'turn'
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        return Path(self.log_dir) / day / f'{safe}.jsonl'


_thinking_log: ContextVar[ThinkingLog | None] = ContextVar('thinking_log', default=None)


def thinking_log() -> ThinkingLog | None:
    """The current turn's thinking log, or None outside a thinking_session."""
    return _thinking_log.get()


@contextmanager
def thinking_session(options: Any = None, *, turn_id: str | None = None):
    """Apply options.thinking* for one orchestrator turn.

    log_thinking None means jsonl when any step thinks, off otherwise.
    """
    setting = getattr(options, 'thinking', 'off')
    by_step = dict(getattr(options, 'thinking_by_step', None) or {})
    log = getattr(options, 'log_thinking', None)
    if log is None:
        log = 'jsonl' if 'on' in (setting, *by_step.values()) else 'off'
    session = ThinkingLog(
        setting=setting,
        by_step=by_step,
        log=log,
        log_dir=getattr(options, 'thinking_log_dir', 'runs/thinking'),
        turn_id=turn_id
        or f"{datetime.now(timezone.utc).strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}",
    )
    token = _thinking_log.set(session)
    try:
        yield session
    finally:
        _thinking_log.reset(token)


@dataclass
class TokenMeter:
    """Completion tokens spent in one orchestrator turn, against an optional
    ceiling (OptionsConfig.token_ceiling). Every call path below adds to it."""

    ceiling: int | None = None
    completion_tokens: int = 0
    estimated_calls: int = 0  # calls without usage, counted as len(text) // 4

    @property
    def exceeded(self) -> bool:
        return self.ceiling is not None and self.completion_tokens >= self.ceiling


_token_meter: ContextVar[TokenMeter | None] = ContextVar('token_meter', default=None)


@contextmanager
def token_meter(ceiling: int | None = None):
    """Meter one turn's completion tokens (TaskOrchestrator.iter_query)."""
    meter = TokenMeter(ceiling=ceiling)
    token = _token_meter.set(meter)
    try:
        yield meter
    finally:
        _token_meter.reset(token)


def current_token_meter() -> TokenMeter | None:
    return _token_meter.get()


def meter_completion(usage: Any, text: str | None) -> None:
    """Add one call's completion tokens to the turn's meter, if there is one."""
    meter = _token_meter.get()
    if meter is None:
        return
    n = getattr(usage, 'completion_tokens', None)
    if n is None:
        meter.estimated_calls += 1
        n = len(text or '') // 4
    meter.completion_tokens += n


def thinking_enabled() -> bool:
    """Whether the call about to be made should think (per-step override first)."""
    session = _thinking_log.get()
    if session is None:
        return False
    return session.by_step.get(current_step_kind() or '', session.setting) == 'on'


def thinking_extra_body() -> dict:
    """The explicit switch every call sends (vLLM and llama-server templates)."""
    return {'chat_template_kwargs': {'enable_thinking': thinking_enabled()}}


_THINK_BLOCK = re.compile(r'\s*<think>(.*?)(?:</think>|$)\s*', re.DOTALL)


def split_reasoning(content: str | None) -> tuple[str, str]:
    """(reasoning, answer): a leading <think>…</think> moved out of content.

    The fallback for servers without a reasoning parser. An unterminated
    block (truncated generation) is all reasoning.
    """
    if not content:
        return '', content or ''
    match = _THINK_BLOCK.match(content)
    if match is None:
        return '', content
    return match.group(1).strip(), content[match.end():]


def message_reasoning(message: Any) -> str:
    """Reasoning text a server's parser put beside the content, if any."""
    if message is None:
        return ''
    extra = getattr(message, 'model_extra', None) or {}
    for name in ('reasoning_content', 'reasoning'):
        value = getattr(message, name, None) or extra.get(name)
        if value:
            return str(value)
    return ''


def reasoning_tokens(usage: Any) -> int | None:
    details = getattr(usage, 'completion_tokens_details', None)
    if isinstance(details, dict):
        return details.get('reasoning_tokens')
    return getattr(details, 'reasoning_tokens', None)


def record_reasoning(
    text: str, *, path: str, tokens: int | None = None
) -> dict | None:
    """Log one call's reasoning to the turn's side log (never to a prompt)."""
    session = _thinking_log.get()
    if session is None or not (text or tokens):
        return None
    state = live()
    record = {
        'ts': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'turn_id': session.turn_id,
        'step': state.llm_label if state is not None else '',
        'kind': current_step_kind(),
        'setting': 'on' if thinking_enabled() else 'off',
        'path': path,
        'reasoning_tokens': tokens,
        'chars': len(text),
        'text': text,
    }
    session.records.append(record)
    if session.log == 'jsonl':
        try:
            out = session.path()
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record) + '\n')
        except OSError as exc:
            logger.warning('thinking log write failed: %s', exc)
    return record


R = TypeVar('R')
Processor = Callable[[OpenAI, LLMInput], R]


LLM_BASE_URL_ENV = 'LLM_BASE_URL'
LLM_MODEL_ENV = 'LLM_MODEL'


def _model_name() -> str:
    # llama-server ignores the name; vLLM and other servers need the real one.
    return os.environ.get(LLM_MODEL_ENV) or 'llama'


def create_llama_client(
    config: dict | None = None,
    *,
    base_url: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> OpenAI:
    """
    Creates and returns an OpenAI-compatible client for the llama.cpp server.

    Resolution order (D-P: there is no silent default endpoint):
    1. the LLM_BASE_URL environment variable;
    2. config['key_word_args'] (--host / --port), as written by the server
       launcher config;
    3. explicit base_url;
    4. explicit host + port.
    With none of these a ValueError is raised.

    Example:
        client = create_llama_client(base_url='http://host.containers.internal:5000/v1')
        client = create_llama_client(host='127.0.0.1', port=8000)
    """
    env_url = os.environ.get(LLM_BASE_URL_ENV)
    if env_url:
        base_url = env_url
    elif config is not None:
        host = config['key_word_args'].get('--host', '127.0.0.1')
        port_str = config['key_word_args'].get('--port')
        if port_str is None:
            raise ValueError("--port not specified in config['key_word_args']")
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f'Invalid --port value in config: {port_str}')
        base_url = f'http://{host}:{port}/v1'
    elif not base_url:
        if host is None or port is None:
            raise ValueError(
                'No LLM endpoint configured: set LLM_BASE_URL, llm.base_url '
                '(or llm.host + llm.port) in orchestrator.yaml, or pass '
                'base_url / host + port to create_llama_client'
            )
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
        return split_reasoning(content)[1].strip()

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

    # D-013: reasoning is logged by the call path, never returned as content.
    return split_reasoning(content)[1].strip()


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

    accumulated.content = split_reasoning(accumulated.content)[1].strip() or None
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
        # What instructor.from_openai builds, with create wrapped so every
        # attempt's reasoning is logged and stripped before instructor parses
        # (D-013, D-015). Built per request: it must bind the client's current
        # chat.completions.create, which is the harness seam (O-03).
        instr_client = instructor.Instructor(
            client=llama_client,
            create=instructor.patch(
                create=_reasoning_capture(llama_client.chat.completions.create),
                mode=instructor.Mode.JSON,
            ),
            mode=instructor.Mode.JSON,
        )
        if instr_client is not None and callable(getattr(instr_client, 'create', None)):
            response = instr_client.create(
                model=_model_name(),
                messages=messages,
                response_model=response_model,
                max_retries=max_retries,
                timeout=3600,
                extra_body=thinking_extra_body(),
                **instructor_kwargs,
            )
            return _finalize_instructor_response(response, partial_callbacks)

    last_error: Exception | None = None
    for attempt in range(max(1, max_retries)):
        try:
            completion = llama_client.chat.completions.create(
                model=_model_name(),
                messages=messages,
                stream=False,
                timeout=3600,
                extra_body=thinking_extra_body(),
            )
            message = completion.choices[0].message if completion.choices else None
            meter_completion(getattr(completion, 'usage', None), getattr(message, 'content', None))
            think, content = split_reasoning(getattr(message, 'content', None) or '')
            record_reasoning(
                message_reasoning(message) or think,
                path='json',
                tokens=reasoning_tokens(getattr(completion, 'usage', None)),
            )
            final_model = parse_json_model(content.strip(), response_model)
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


def _reasoning_capture(create: Callable[..., Any]) -> Callable[..., Any]:
    """chat.completions.create as instructor calls it, once per attempt.

    instructor 1.3.2 cannot be asked for this afterwards: _raw_response holds
    only the last attempt and is missing for list[...] models, its usage is a
    summed copy without completion_tokens_details, and its JSON mode parses
    from the first '{' to the last '}', which a <think> block can contain.
    """

    def create_and_capture(*args: Any, **kwargs: Any) -> Any:
        response = create(*args, **kwargs)
        choices = getattr(response, 'choices', None)
        if kwargs.get('stream') or not choices:
            return response
        message = choices[0].message
        meter_completion(getattr(response, 'usage', None), message.content)
        think, content = split_reasoning(message.content)
        if think:
            message.content = content
        record_reasoning(
            message_reasoning(message) or think,
            path='instructor',
            tokens=reasoning_tokens(getattr(response, 'usage', None)),
        )
        return response

    return create_and_capture


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
        model=_model_name(),
        messages=standard_messages,
        stream=True,
        timeout=3600,
        extra_body=thinking_extra_body(),
    )

    chunks: list[ChatCompletionChunk] = []
    reasoning: list[str] = []
    content: list[str] = []
    tokens = None
    usage = None
    for chunk in stream:
        if getattr(chunk, 'usage', None) is not None:
            usage = chunk.usage
            tokens = reasoning_tokens(chunk.usage)
        if chunk.choices:
            delta = chunk.choices[0].delta
            reasoning.append(message_reasoning(delta))
            content.append(delta.content or '')
        # Real-time processing via callbacks
        for callback in callbacks:
            try:
                callback(chunk)
            except Exception as e:
                # Optional: log or ignore callback errors to not interrupt streaming
                print(f'Callback error: {e}')

        chunks.append(chunk)

    meter_completion(usage, ''.join(reasoning) + ''.join(content))
    record_reasoning(
        ''.join(reasoning) or split_reasoning(''.join(content))[0],
        path='stream',
        tokens=tokens,
    )
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
