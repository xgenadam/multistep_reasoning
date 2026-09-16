"""
oobabooga extension: run TaskOrchestrator instead of a single generate.

Install:
  ln -s /path/to/this/repo/oobabooga_extension \\
        /path/to/text-generation-webui/user_data/extensions/multistep_reasoning
  pip install -e /path/to/this/repo
  # or set MULTISTEP_REASONING_ROOT to the repo root

Enable with:  --extensions openai multistep_reasoning

Inner model calls use oobabooga's generate_reply_HF / generate_reply_custom
directly (never generate_reply) so this hook does not recurse.
"""

from __future__ import annotations

import copy
import logging
import os
import queue
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from pathlib import Path
from typing import Any, Iterator

params = {
    'display_name': 'Multi-step reasoning',
    'is_tab': False,
    'enable': True,
    'intercept_mode': 'chat_only',
}

_inner: ContextVar[bool] = ContextVar('multistep_inner', default=False)
_active_ui_state: dict | None = None
_pending_lock = threading.Lock()
_pending_turn: dict[str, Any] = {}
WAIT_PLACEHOLDER = 'Please wait while the response is being processed.'

_orchestrator = None
_sessions: dict[str, Any] = {}
_last_trace = (
    '(no pipeline run yet)\n'
    'If a Gradio reply already finished and this did not change, '
    'this extension did not handle generate_reply '
    '(another extension may own custom_generate_reply, e.g. deep_reason).'
)
try:
    from modules.logging_colors import logger
except ImportError:
    logger = logging.getLogger('multistep_reasoning')


def _ensure_import_path() -> None:
    """Prefer the copy next to this extension over a leftover site-packages install."""
    env = os.environ.get('MULTISTEP_REASONING_ROOT')
    here = Path(__file__).resolve().parent
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend([here, here.parent, here.parent.parent])
    for cand in candidates:
        pkg = cand / 'reasoning_sub_agents' / '__init__.py'
        if pkg.is_file():
            path = str(cand)
            if path in sys.path:
                sys.path.remove(path)
            sys.path.insert(0, path)
            return


def setup() -> None:
    global _orchestrator, _last_trace
    _ensure_import_path()
    try:
        import reasoning_sub_agents
        from reasoning_sub_agents.local_generate_client import LocalGenerateClient
        from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

        yaml_path = _orchestrator_yaml()
        from reasoning_sub_agents import chat_adapter

        logger.info(
            'multi-step reasoning setup: package=%s chat_adapter=%s yaml=%s',
            getattr(reasoning_sub_agents, '__file__', None),
            getattr(chat_adapter, '__file__', None),
            yaml_path,
        )
        client = LocalGenerateClient(_inner_generate)
        if yaml_path is not None:
            _orchestrator = TaskOrchestrator.from_yaml(
                yaml_path, llm_client=client
            )
        else:
            _orchestrator = TaskOrchestrator.instantiate(llm_client=client)
        logger.info('multi-step reasoning extension ready (yaml=%s)', yaml_path)
        _last_trace = f'Orchestrator ready (yaml={yaml_path}). Waiting for a Gradio turn.'
    except Exception as exc:
        logger.exception('failed to initialise multi-step reasoning; leaving disabled')
        params['enable'] = False
        _orchestrator = None
        _last_trace = f'setup() failed:\n{type(exc).__name__}: {exc}'


def ui() -> None:
    import gradio as gr

    enable = gr.Checkbox(
        value=params.get('enable', True),
        label='Enable multi-step reasoning',
        info='Decompose the user turn, run sub-tasks, and edit a per-chat Document. '
        'Follow-ups in the same chat keep editing that document.',
    )
    intercept = gr.Radio(
        choices=['chat_only', 'always', 'never'],
        value=params.get('intercept_mode', 'chat_only'),
        label='Intercept mode',
        info='chat_only: skip Cline/OpenCode/Grok tool turns. '
        'always: intercept every chat turn (except inner calls). '
        'never: never intercept.',
    )

    def _set_enable(value: bool) -> None:
        params['enable'] = bool(value)

    def _set_mode(value: str) -> None:
        params['intercept_mode'] = value

    enable.change(_set_enable, enable, None)
    intercept.change(_set_mode, intercept, None)

    trace_box = gr.Textbox(
        value=_last_trace,
        label='Pipeline trace (live — Refresh if the timer is idle)',
        lines=22,
        interactive=False,
    )
    refresh = gr.Button('Refresh trace')
    refresh.click(_read_trace, outputs=trace_box)
    try:
        timer = gr.Timer(1)
        timer.tick(_read_trace, outputs=trace_box)
    except Exception:
        pass


def _read_trace() -> str:
    return _last_trace


def _pipeline_skip_reason(
    question: str, original_question: str, state: dict
) -> str | None:
    """Why we would not run TaskOrchestrator. None means run it."""
    if not params.get('enable', True):
        return 'Enable checkbox is off'
    if _orchestrator is None:
        return (
            'orchestrator is None — setup() failed. '
            'Search the log for "failed to initialise multi-step reasoning".'
        )
    from reasoning_sub_agents.agent_detect import (
        INNER_SKIP_SENTINEL,
        looks_like_agent_turn,
        should_skip_orchestrator,
    )

    mode = str(params.get('intercept_mode', 'chat_only'))
    if not should_skip_orchestrator(
        intercept_mode=mode,
        state=state,
        question=question or '',
        original_question=original_question or '',
    ):
        return None
    blob = f'{question or ""}\n{original_question or ""}'
    if INNER_SKIP_SENTINEL in blob:
        return 'inner skip sentinel (this generate is an orchestrator LLM call)'
    if looks_like_agent_turn(
        state=state,
        question=question or '',
        original_question=original_question or '',
    ):
        return (
            f'intercept_mode={mode} treated this as an agent turn '
            '(tools in state, Cline/OpenCode markers, or tool-result history). '
            'For Gradio-only testing set intercept to always and disable other '
            'extensions that define custom_generate_reply (e.g. deep_reason).'
        )
    return f'intercept_mode={mode} skipped this turn'


def format_pipeline_trace(orchestrator) -> str:
    """Compact view of the last orchestrator run for the Gradio box."""
    if orchestrator is None:
        return '(orchestrator not loaded)'
    if not orchestrator.history:
        return '(no pipeline run yet)'
    last = orchestrator.history[-1]
    lines: list[str] = []
    user = last.get('user_input') or ''
    lines.append('## User')
    lines.append(_clip(user, 400))
    decomp = last.get('decomposition_history') or {}
    tasks = decomp.get('initial_tasks') or []
    lines.append('')
    lines.append(f'## Sub-tasks ({len(tasks)})')
    if not tasks:
        lines.append('(none recorded)')
    for idx, task in enumerate(tasks, start=1):
        detail = task.get('decomposed_sub_task') if isinstance(task, dict) else None
        if not isinstance(detail, dict):
            detail = task if isinstance(task, dict) else {}
        name = detail.get('name') or f'task-{idx}'
        objective = detail.get('objective') or ''
        lines.append(f'{idx}. {name}')
        if objective:
            lines.append(f'   { _clip(str(objective), 240) }')
    exec_hist = last.get('execution_results') or []
    lines.append('')
    lines.append(f'## Execution ({len(exec_hist)} records)')
    for idx, entry in enumerate(exec_hist, start=1):
        if not isinstance(entry, dict):
            lines.append(f'{idx}. { _clip(str(entry), 200) }')
            continue
        completed = entry.get('completed_sub_task') or {}
        detail = completed.get('decomposed_sub_task') if isinstance(completed, dict) else {}
        if not isinstance(detail, dict):
            detail = {}
        name = detail.get('name') or f'step-{idx}'
        result = ''
        sub_result = completed.get('sub_task_result') if isinstance(completed, dict) else None
        if isinstance(sub_result, dict):
            chat = sub_result.get('chat_response') or {}
            if isinstance(chat, dict):
                result = chat.get('content') or ''
        rounds = entry.get('oracle_rounds') or []
        extra = f', oracle_rounds={len(rounds)}' if rounds else ''
        lines.append(f'{idx}. {name}{extra}')
        if result:
            lines.append(f'   result: {_clip(str(result), 180)}')
    synth = last.get('synthesis_history') or []
    lines.append('')
    lines.append(f'## Compose ({len(synth)} attempts)')
    for idx, entry in enumerate(synth, start=1):
        if not isinstance(entry, dict):
            continue
        ops = entry.get('ops') or []
        err = entry.get('error')
        need = entry.get('need_part_ids') or []
        op_types = []
        for op in ops:
            if isinstance(op, dict):
                op_types.append(str(op.get('type') or op.get('id') or 'op'))
        bit = ', '.join(op_types) if op_types else '(no ops)'
        if need:
            bit += f' need_parts={need}'
        if err:
            bit += f' ERROR: {_clip(str(err), 160)}'
        lines.append(f'{idx}. {bit}')
    snapshot = last.get('document') or {}
    parts = snapshot.get('parts') or []
    lines.append('')
    lines.append(f'## Document parts ({len(parts)})')
    for part in parts:
        if not isinstance(part, dict):
            continue
        body = part.get('body') or ''
        lines.append(
            f'- {part.get("id")} [{part.get("kind")}] {part.get("title")} '
            f'({len(body)} chars)'
        )
    summary = snapshot.get('summary') or ''
    if summary:
        lines.append('')
        lines.append('## Rolling summary')
        lines.append(_clip(str(summary), 400))
    return '\n'.join(lines)


def _phase_line(snapshot: str) -> str:
    """Current pipeline phase from a live snapshot, not the user-request body."""
    lines = snapshot.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == '## Phase' and idx + 1 < len(lines):
            phase = lines[idx + 1].strip()
            if phase:
                return phase
    return ''


def _wait_bubble(phase: str | None = None) -> str:
    phase = (phase or '').strip()
    if phase and phase != WAIT_PLACEHOLDER:
        return f'{WAIT_PLACEHOLDER}\n\n{phase}'
    return WAIT_PLACEHOLDER


def _set_processing_message(text: str) -> str:
    """Replace oobabooga's typing placeholder (often the character context)."""
    previous = ''
    try:
        from modules import shared

        previous = getattr(shared, 'processing_message', '') or ''
        shared.processing_message = text
    except Exception:
        pass
    return previous


def _clip(text: str, limit: int) -> str:
    text = text.replace('\n', ' ').strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + '…'


def chat_input_modifier(text, visible_text, state):
    """Capture the raw Chat-tab turn before it is baked into a prompt."""
    _stash_turn(text, state)
    return text, visible_text


def input_modifier(string, state, is_chat=False):
    """Same capture after other extensions rewrite the chat text."""
    if is_chat:
        _stash_turn(string, state)
    return string


def custom_generate_chat_prompt(user_input, state, **kwargs):
    """oobabooga passes the raw user_input here. Stash it, then use default prompt."""
    _stash_turn(user_input, state, history=kwargs.get('history'))
    from modules import chat

    return chat.generate_chat_prompt(user_input, state, **kwargs)


def _stash_turn(text, state, history=None) -> None:
    cleaned = _as_user_text(text)
    if not cleaned:
        return
    state = state if isinstance(state, dict) else {}
    chat_id = str(state.get('unique_id') or state.get('chat_id') or '')
    hist = history if history is not None else state.get('history')
    with _pending_lock:
        _pending_turn['user_text'] = cleaned
        _pending_turn['chat_id'] = chat_id
        if hist is not None:
            try:
                _pending_turn['history'] = copy.deepcopy(hist)
            except Exception:
                _pending_turn['history'] = hist
        logger.info(
            'stashed chat turn session=%s chars=%s preview=%r',
            chat_id or '(none)',
            len(cleaned),
            cleaned[:160],
        )


def _take_stashed_turn(state: dict | None) -> dict[str, Any]:
    with _pending_lock:
        taken = dict(_pending_turn)
        _pending_turn.clear()
        return taken


def _as_user_text(text) -> str:
    if text is None:
        return ''
    if isinstance(text, dict):
        text = text.get('text') or ''
    stripped = str(text).strip()
    if not stripped:
        return ''
    if stripped.startswith('<|BEGIN-') or stripped.startswith('<|begin-'):
        return ''
    if stripped in {
        '<|BEGIN-VISIBLE-CHAT|>',
        '<|begin-visible-chat|>',
        '<|END-VISIBLE-CHAT|>',
    }:
        return ''
    return stripped


def custom_generate_reply(
    question: str,
    original_question: str,
    state: dict,
    stopping_strings=None,
    is_chat: bool = False,
) -> Iterator[str]:
    global _last_trace
    # Nested model calls must not rewrite the trace box.
    if _inner.get():
        yield from _default_generate(
            question, original_question, state, stopping_strings, is_chat=is_chat
        )
        return

    skip = _pipeline_skip_reason(question, original_question, state)
    if skip:
        _take_stashed_turn(state)
        _last_trace = f'Skipped pipeline:\n{skip}'
        logger.info('pipeline skipped: %s', skip)
        yield from _default_generate(
            question, original_question, state, stopping_strings, is_chat=is_chat
        )
        return

    from reasoning_sub_agents.chat_adapter import (
        chat_id_from_state,
        compact_chat_history,
        compact_chat_history_from_state,
    )
    from reasoning_sub_agents.document import Document

    stashed = _take_stashed_turn(state)
    user_text = question
    if not user_text.strip():
        _last_trace = (
            'Skipped pipeline:\nno stashed chat_input and could not parse '
            'the current user message out of the rendered prompt. '
            'Refusing to reuse an older history turn.'
        )
        logger.warning('%s', _last_trace)
        yield from _default_generate(
            question, original_question, state, stopping_strings, is_chat=is_chat
        )
        return

    global _active_ui_state
    _active_ui_state = state if isinstance(state, dict) else None
    previous_processing = _set_processing_message(WAIT_PLACEHOLDER)
    try:
        session_id = str(stashed.get('chat_id') or '') or chat_id_from_state(state)
        document = _sessions.get(session_id)
        if document is None:
            render_mode = _orchestrator.options.render
            document = Document.empty(render_mode=render_mode)
            _sessions[session_id] = document
        if stashed.get('history') is not None:
            chat_context = compact_chat_history(stashed.get('history'))
        else:
            chat_context = compact_chat_history_from_state(state)
        events: queue.Queue = queue.Queue()

        def on_live(snapshot: str) -> None:
            global _last_trace
            _last_trace = snapshot
            events.put(('live', snapshot))

        def run_pipeline() -> None:
            from reasoning_sub_agents.progress import live_session

            try:
                with live_session(on_live):
                    for kind, payload in _orchestrator.iter_query(
                        user_text,
                        document=document,
                        chat_context=chat_context or None,
                    ):
                        if kind == 'status':
                            events.put(('status', str(payload)))
                        elif kind == 'done':
                            events.put(('done', payload))
            except Exception as exc:
                logger.exception('multi-step reasoning failed')
                events.put(('error', exc))

        ctx = copy_context()
        worker = threading.Thread(
            target=lambda: ctx.run(run_pipeline), daemon=True
        )
        worker.start()
        yield WAIT_PLACEHOLDER
        while True:
            kind, payload = events.get()
            if kind == 'live':
                yield _wait_bubble(_phase_line(str(payload)))
            elif kind == 'status':
                yield _wait_bubble(str(payload))
            elif kind == 'done':
                board = _last_trace
                history = format_pipeline_trace(_orchestrator)
                _last_trace = board + '\n\n---\n\n' + history
                n_parts = 0
                snapshot = getattr(payload, 'document_snapshot', None) or {}
                if isinstance(snapshot, dict):
                    n_parts = len(snapshot.get('parts') or [])
                content = payload.chat_response.content or ''
                if content.strip():
                    yield content
                else:
                    yield (
                        f'Done. {n_parts} document part(s) — see Pipeline trace.'
                    )
                return
            elif kind == 'error':
                _last_trace = f'FAILED: {payload}'
                yield f'Multi-step reasoning failed: {payload}'
                return
    except Exception as exc:
        logger.exception('multi-step reasoning failed')
        _last_trace = f'FAILED: {exc}'
        yield f'Multi-step reasoning failed: {exc}'
    finally:
        _active_ui_state = None
        _set_processing_message(previous_processing)


def _inner_generate(prompt: str, *, stream: bool = False):
    if stream:
        return _inner_generate_stream(prompt)
    token = _inner.set(True)
    try:
        with _oobabooga_prompt_print():
            state = _generation_state(stream=False)
            last = ''
            for cumulative in _default_generate(
                prompt, prompt, state, None, is_chat=False
            ):
                last = cumulative or last
            return last
    finally:
        _inner.reset(token)


def _inner_generate_stream(prompt: str) -> Iterator[str]:
    token = _inner.set(True)
    try:
        with _oobabooga_prompt_print():
            state = _generation_state(stream=True)
            prev = ''
            for cumulative in _default_generate(
                prompt, prompt, state, None, is_chat=False
            ):
                text = cumulative or ''
                delta = text[len(prev) :] if text.startswith(prev) else text
                prev = text
                if delta:
                    yield delta
    finally:
        _inner.reset(token)


@contextmanager
def _oobabooga_prompt_print():
    """oobabooga prints full prompts when args.verbose; keep that off unless yaml says so."""
    try:
        from reasoning_sub_agents.llama_utils import log_prompts_enabled

        enabled = log_prompts_enabled()
    except Exception:
        enabled = False
    if enabled:
        yield
        return
    previous = None
    try:
        from modules import shared

        args = getattr(shared, 'args', None)
        if args is not None and getattr(args, 'verbose', False):
            previous = True
            args.verbose = False
    except Exception:
        previous = None
    try:
        yield
    finally:
        if previous is not None:
            try:
                from modules import shared

                shared.args.verbose = True
            except Exception:
                pass


# Keys llama.cpp prepare_payload / generate_with_streaming require.
_GENERATION_DEFAULTS = {
    'temperature': 0.7,
    'dynamic_temperature': False,
    'dynatemp_low': 1.0,
    'dynatemp_high': 1.0,
    'dynatemp_exponent': 1,
    'top_k': 40,
    'top_p': 0.9,
    'min_p': 0.0,
    'top_n_sigma': 0,
    'adaptive_target': 0,
    'adaptive_decay': 0,
    'typical_p': 1.0,
    'repetition_penalty': 1.0,
    'repetition_penalty_range': 0,
    'presence_penalty': 0.0,
    'frequency_penalty': 0.0,
    'dry_multiplier': 0.0,
    'dry_base': 1.75,
    'dry_allowed_length': 2,
    'dry_sequence_breakers': '["\\n", ":", "\\"", "*"]',
    'xtc_probability': 0.0,
    'xtc_threshold': 0.1,
    'mirostat_mode': 0,
    'mirostat_tau': 5,
    'mirostat_eta': 0.1,
    'grammar_string': '',
    'seed': -1,
    'ban_eos_token': False,
    'sampler_priority': '',
    'temperature_last': False,
    'custom_token_bans': '',
    'add_bos_token': True,
    'auto_max_new_tokens': False,
    'max_new_tokens': 2048,
    'truncation_length': 8192,
    'skip_special_tokens': True,
    'negative_prompt': '',
    'static_cache': False,
    'prompt_lookup_num_tokens': 0,
    'epsilon_cutoff': 0,
    'eta_cutoff': 0,
    'max_tokens_second': 0,
    'stream': True,
}


def _generation_state(*, stream: bool) -> dict:
    """Full oobabooga generate() state so llama.cpp prepare_payload does not KeyError."""
    state: dict = {}
    try:
        from modules import shared

        settings = getattr(shared, 'settings', None)
        if isinstance(settings, dict):
            state.update(settings)
    except Exception:
        pass
    outer = _active_ui_state
    if outer:
        try:
            if isinstance(outer, dict):
                state.update(outer)
            else:
                state.update(dict(outer))
        except Exception:
            try:
                state.update(copy.copy(outer))
            except Exception:
                pass
    for key, value in _GENERATION_DEFAULTS.items():
        state.setdefault(key, value)
    state['stream'] = stream
    try:
        from reasoning_sub_agents.llama_utils import inner_token_limit

        limit = inner_token_limit()
        if limit:
            inherited = int(state.get('max_new_tokens') or 2048)
            state['max_new_tokens'] = max(256, min(inherited, limit))
            state['auto_max_new_tokens'] = False
    except Exception:
        pass
    return state


def _default_generate(
    question: str,
    original_question: str,
    state: dict,
    stopping_strings=None,
    is_chat: bool = False,
) -> Iterator[str]:
    from modules import shared
    from modules.text_generation import generate_reply_HF, generate_reply_custom

    model = getattr(shared, 'model', None)
    name = model.__class__.__name__ if model is not None else ''
    if name in {'LlamaServer', 'Exllamav3Model', 'TensorRTLLMModel'}:
        func = generate_reply_custom
    else:
        func = generate_reply_HF
    yield from func(
        question, original_question, state, stopping_strings, is_chat=is_chat
    )


def _orchestrator_yaml() -> Path | None:
    env = os.environ.get('MULTISTEP_ORCHESTRATOR_YAML')
    if env:
        path = Path(env)
        if path.is_file():
            return path
    here = Path(__file__).resolve().parent
    for cand in (
        here / 'orchestrator.yaml',
        here.parent / 'orchestrator.yaml',
        Path.cwd() / 'orchestrator.yaml',
    ):
        if cand.is_file():
            return cand
    return None
