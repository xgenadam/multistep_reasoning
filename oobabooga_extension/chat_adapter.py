"""Helpers for turning oobabooga / Open WebUI chat state into orchestrator inputs."""

from __future__ import annotations

import re

_PLACEHOLDERS = (
    '<|BEGIN-VISIBLE-CHAT|>',
    '<|begin-visible-chat|>',
    '<|END-VISIBLE-CHAT|>',
)

_PROMPT_MARKERS = (
    '<|im_start|>',
    '<|start_header_id|>',
    '[INST]',
    '<start_of_turn>',
    '<|BEGIN-VISIBLE-CHAT|>',
    '<|user|>',
    '<|assistant|>',
)

_CHATML_USER = re.compile(
    r'<\|im_start\|>\s*user\s*\n?(.*?)(?:<\|im_end\|>|$)',
    re.DOTALL | re.IGNORECASE,
)
_LLAMA3_USER = re.compile(
    r'<\|start_header_id\|>user<\|end_header_id\|>\s*(.*?)'
    r'(?:<\|eot_id\|>|<\|start_header_id\|>|$)',
    re.DOTALL | re.IGNORECASE,
)
_GEMMA_USER = re.compile(
    r'<start_of_turn>user\s*\n(.*?)(?:<end_of_turn>|$)',
    re.DOTALL,
)
_INST_USER = re.compile(r'\[INST\](.*?)\[/INST\]', re.DOTALL)
_PIPE_USER = re.compile(
    r'<\|user\|>(.*?)(?:<\|assistant\|>|<\|end\|>|$)',
    re.DOTALL,
)

def _is_placeholder(text: str) -> bool:
    stripped = (text or '').strip()
    if not stripped:
        return True
    if stripped in _PLACEHOLDERS:
        return True
    if stripped.startswith('<|BEGIN-') or stripped.startswith('<|begin-'):
        return True
    return False


def _unwrap_user_turn(text: str) -> str:
    """If we were given a packed chat prompt, keep only the last user turn."""
    if not text:
        return text
    if '<|BEGIN-VISIBLE-CHAT|>' in text:
        text = text.split('<|BEGIN-VISIBLE-CHAT|>')[-1]
    if '[INST]' in text:
        last = text.split('[INST]')[-1]
        if '[/INST]' in last:
            last = last.split('[/INST]')[0]
        text = last
    stripped = text.strip()
    if _is_placeholder(stripped):
        return ''
    return stripped


def compact_chat_history(history: dict | None, *, max_turns: int = 6) -> str:
    """
    Previous completed user/assistant turns, excluding the current unfinished turn.
    """
    completed: list[str] = []
    for pair in _pairs(history):
        if not pair or not pair[0]:
            continue
        user = _unwrap_user_turn(str(pair[0]).strip())
        bot = str(pair[1]).strip() if len(pair) > 1 and pair[1] else ''
        if not bot or _is_placeholder(user):
            continue
        completed.append(f'User: {user}\nAssistant: {bot}')
    if not completed:
        return ''
    return '\n\n'.join(completed[-max_turns:])


def compact_chat_history_from_state(state: dict | None, *, max_turns: int = 6) -> str:
    state = state or {}
    from_history = compact_chat_history(state.get('history'), max_turns=max_turns)
    if from_history:
        return from_history
    messages = state.get('messages') or []
    turns: list[str] = []
    pending_user: str | None = None
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = (item.get('content') or '').strip()
        if not content:
            continue
        if role == 'user':
            pending_user = content
        elif role == 'assistant' and pending_user is not None:
            turns.append(f'User: {pending_user}\nAssistant: {content}')
            pending_user = None
    if not turns:
        return ''
    return '\n\n'.join(turns[-max_turns:])


def chat_id_from_state(state: dict | None, fallback: str = 'default') -> str:
    """Currently viewed chat, not the last row of the Past chats Radio."""
    try:
        from modules import chat as ooba_chat

        viewed = getattr(ooba_chat, 'viewing_unique_id', None)
        if viewed:
            return str(viewed)
    except Exception:
        pass
    state = state or {}
    for key in ('unique_id', 'id', 'chat_id'):
        value = state.get(key)
        if isinstance(value, (list, tuple)):
            # A list of past-chat ids. [-1] is the bottom row ('test'). Skip.
            continue
        if value:
            return str(value)
    return fallback


def _pairs(history: dict | None) -> list:
    if not history:
        return []
    return history.get('internal') or history.get('visible') or []
