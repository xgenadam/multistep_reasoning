"""Heuristics for when the oobabooga extension should not intercept generation."""

from __future__ import annotations

from typing import Any

INNER_SKIP_SENTINEL = '[[multistep-inner]]'

InterceptMode = str  # 'always' | 'chat_only' | 'never'

_AGENT_MARKERS = (
    'you are cline',
    'you are opencode',
    'attempt_completion',
    'execute_command',
    'search_replace',
    'run_terminal_command',
    'use_tool',
    '<read_file>',
    '<write_to_file>',
    '<execute_command>',
    '<attempt_completion>',
    'act:read_file',
    'tool_result',
    '[tool result]',
)

_TOOL_ROLES = frozenset({'tool', 'function', 'tool_result'})


def should_skip_orchestrator(
    *,
    intercept_mode: str = 'chat_only',
    state: dict[str, Any] | None = None,
    question: str = '',
    original_question: str = '',
    history: dict | list | None = None,
) -> bool:
    """
    Return True when custom_generate_reply should fall through to default generate.

    Prefer skip when intercept_mode is chat_only and the turn looks like an
    agent (Cline / OpenCode / Grok Build) or an inner orchestrator HTTP call.
    """
    mode = (intercept_mode or 'chat_only').strip().lower()
    if mode == 'never':
        return True
    if mode == 'always':
        return _has_inner_sentinel(state, question, original_question, history)
    # chat_only
    if looks_like_agent_turn(
        state=state,
        question=question,
        original_question=original_question,
        history=history,
    ):
        return True
    return False


def looks_like_agent_turn(
    *,
    state: dict[str, Any] | None = None,
    question: str = '',
    original_question: str = '',
    history: dict | list | None = None,
) -> bool:
    state = state or {}
    if _has_inner_sentinel(state, question, original_question, history):
        return True
    if _has_tool_schema(state):
        return True
    haystack = _text_haystack(state, question, original_question, history)
    if _has_agent_marker(haystack):
        return True
    hist = history if history is not None else state.get('history')
    if _history_has_tool_turns(hist):
        return True
    if _messages_have_tool_roles(state.get('messages')):
        return True
    return False


def _has_inner_sentinel(
    state: dict[str, Any] | None,
    question: str,
    original_question: str,
    history: dict | list | None,
) -> bool:
    blob = _text_haystack(state, question, original_question, history)
    return INNER_SKIP_SENTINEL in blob


def _has_tool_schema(state: dict[str, Any]) -> bool:
    for key in ('tools', 'functions', 'tool_choice'):
        value = state.get(key)
        if value:
            return True
    body = state.get('body')
    if isinstance(body, dict):
        for key in ('tools', 'functions'):
            if body.get(key):
                return True
    return False


def _has_agent_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _AGENT_MARKERS)


def _text_haystack(
    state: dict[str, Any] | None,
    question: str,
    original_question: str,
    history: dict | list | None,
) -> str:
    parts = [question or '', original_question or '']
    state = state or {}
    for key in ('context', 'system', 'system_message', 'instruction', 'prompt'):
        value = state.get(key)
        if isinstance(value, str):
            parts.append(value)
    messages = state.get('messages')
    if isinstance(messages, list):
        for item in messages:
            if isinstance(item, dict):
                content = item.get('content')
                if isinstance(content, str):
                    parts.append(content)
    hist = history if history is not None else state.get('history')
    parts.append(_flatten_history(hist))
    return '\n'.join(parts)


def _flatten_history(history: dict | list | None) -> str:
    if not history:
        return ''
    chunks: list[str] = []
    if isinstance(history, dict):
        for key in ('internal', 'visible'):
            pairs = history.get(key) or []
            for pair in pairs:
                if isinstance(pair, (list, tuple)):
                    chunks.extend(str(x) for x in pair if x)
                elif isinstance(pair, str):
                    chunks.append(pair)
        if 'messages' in history:
            chunks.append(_flatten_history(history.get('messages')))
        return '\n'.join(chunks)
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict):
                content = item.get('content')
                if content:
                    chunks.append(str(content))
            elif isinstance(item, (list, tuple)):
                chunks.extend(str(x) for x in item if x)
            elif item:
                chunks.append(str(item))
    return '\n'.join(chunks)


def _history_has_tool_turns(history: dict | list | None) -> bool:
    if not history:
        return False
    if isinstance(history, dict):
        if _messages_have_tool_roles(history.get('messages')):
            return True
        blob = _flatten_history(history).lower()
        return 'tool_result' in blob or '[tool result]' in blob
    return _messages_have_tool_roles(history)


def _messages_have_tool_roles(messages: list | None) -> bool:
    if not isinstance(messages, list):
        return False
    for item in messages:
        if isinstance(item, dict) and item.get('role') in _TOOL_ROLES:
            return True
    return False
