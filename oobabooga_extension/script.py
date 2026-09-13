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
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

params = {
    'display_name': 'Multi-step reasoning',
    'is_tab': False,
    'enable': True,
    'intercept_mode': 'chat_only',
}

_inner: ContextVar[bool] = ContextVar('multistep_inner', default=False)
_gen_state: ContextVar[dict | None] = ContextVar('multistep_state', default=None)

_orchestrator = None
_sessions: dict[str, Any] = {}
logger = logging.getLogger('multistep_reasoning')


def _ensure_import_path() -> None:
    try:
        import reasoning_sub_agents  # noqa: F401

        return
    except ImportError:
        pass
    env = os.environ.get('MULTISTEP_REASONING_ROOT')
    candidates = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parent
    candidates.extend([here, here.parent, here.parent.parent])
    for cand in candidates:
        if (cand / 'reasoning_sub_agents' / '__init__.py').is_file():
            sys.path.insert(0, str(cand))
            return


def setup() -> None:
    global _orchestrator
    _ensure_import_path()
    try:
        from reasoning_sub_agents.local_generate_client import LocalGenerateClient
        from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

        yaml_path = _orchestrator_yaml()
        client = LocalGenerateClient(_inner_generate)
        if yaml_path is not None:
            _orchestrator = TaskOrchestrator.from_yaml(
                yaml_path, llm_client=client
            )
        else:
            _orchestrator = TaskOrchestrator.instantiate(llm_client=client)
        logger.info('multi-step reasoning extension ready (yaml=%s)', yaml_path)
    except Exception:
        logger.exception('failed to initialise multi-step reasoning; leaving disabled')
        params['enable'] = False
        _orchestrator = None


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


def custom_generate_reply(
    question: str,
    original_question: str,
    state: dict,
    stopping_strings=None,
    is_chat: bool = False,
) -> Iterator[str]:
    if _inner.get() or not params.get('enable', True) or _orchestrator is None:
        yield from _default_generate(
            question, original_question, state, stopping_strings, is_chat=is_chat
        )
        return

    from reasoning_sub_agents.agent_detect import should_skip_orchestrator

    if should_skip_orchestrator(
        intercept_mode=str(params.get('intercept_mode', 'chat_only')),
        state=state,
        question=question or '',
        original_question=original_question or '',
    ):
        yield from _default_generate(
            question, original_question, state, stopping_strings, is_chat=is_chat
        )
        return

    from reasoning_sub_agents.chat_adapter import (
        chat_id_from_state,
        compact_chat_history_from_state,
        last_user_message_from_state,
    )
    from reasoning_sub_agents.document import Document

    user_text = last_user_message_from_state(state, fallback=question)
    if not user_text.strip():
        yield from _default_generate(
            question, original_question, state, stopping_strings, is_chat=is_chat
        )
        return

    token = _gen_state.set(state)
    try:
        session_id = chat_id_from_state(state)
        document = _sessions.get(session_id)
        if document is None:
            render_mode = _orchestrator.options.render
            document = Document.empty(render_mode=render_mode)
            _sessions[session_id] = document
        chat_context = compact_chat_history_from_state(state)
        yield '⏳ Multi-step reasoning: decomposing and executing sub-tasks…'
        response = _orchestrator.query(
            user_text,
            document=document,
            chat_context=chat_context or None,
        )
        content = response.content or ''
        yield content
    except Exception as exc:
        logger.exception('multi-step reasoning failed')
        yield f'Multi-step reasoning failed: {exc}'
    finally:
        _gen_state.reset(token)


def _inner_generate(prompt: str, *, stream: bool = False):
    if stream:
        return _inner_generate_stream(prompt)
    token = _inner.set(True)
    try:
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


def _generation_state(*, stream: bool) -> dict:
    outer = _gen_state.get()
    if outer:
        try:
            state = copy.copy(outer)
        except Exception:
            state = dict(outer)
    else:
        state = {
            'stream': stream,
            'max_new_tokens': 2048,
            'temperature': 0.7,
            'seed': -1,
            'truncation_length': 8192,
            'custom_stopping_strings': '',
            'max_tokens_second': 0,
            'add_bos_token': True,
            'ban_eos_token': False,
            'skip_special_tokens': True,
            'auto_max_new_tokens': False,
            'grammar_string': '',
            'negative_prompt': '',
            'static_cache': False,
            'sampler_priority': '',
            'custom_token_bans': '',
            'prompt_lookup_num_tokens': 0,
            'epsilon_cutoff': 0,
            'eta_cutoff': 0,
        }
    state['stream'] = stream
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
