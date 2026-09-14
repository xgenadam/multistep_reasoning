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


def last_user_message(history: dict | None, fallback: str = '') -> str:
    pairs = _pairs(history)
    for pair in reversed(pairs):
        if not pair or not pair[0]:
            continue
        text = _unwrap_user_turn(str(pair[0]))
        if text and not _is_placeholder(text):
            return text
    return _unwrap_user_turn(fallback)


def last_unfinished_user_message(history: dict | None) -> str:
    """Current turn if history already has [user, ''] (bot not generated yet)."""
    pairs = _pairs(history)
    if not pairs:
        return ''
    last = pairs[-1]
    if not last or not last[0]:
        return ''
    user = _unwrap_user_turn(str(last[0]))
    bot = str(last[1]).strip() if len(last) > 1 and last[1] else ''
    if user and not _is_placeholder(user) and (not bot or _is_processing_bot(bot)):
        return user
    return ''


def last_user_message_from_state(state: dict | None, fallback: str = '') -> str:
    state = state or {}
    from_history = last_user_message(state.get('history'), '')
    if from_history:
        return from_history
    messages = state.get('messages') or []
    for item in reversed(messages):
        if isinstance(item, dict) and item.get('role') == 'user':
            content = item.get('content')
            if content:
                text = _unwrap_user_turn(str(content))
                if text and not _is_placeholder(text):
                    return text
    textbox = _chat_textbox(state)
    if textbox:
        return textbox
    return _unwrap_user_turn(fallback)


def resolve_current_user_text(
    *,
    question: str = '',
    original_question: str = '',
    state: dict | None = None,
    pending_user_text: str = '',
) -> str:
    text, _source = pick_current_user_text(
        question=question,
        original_question=original_question,
        state=state,
        pending_user_text=pending_user_text,
    )
    return text


def pick_current_user_text(
    *,
    question: str = '',
    original_question: str = '',
    state: dict | None = None,
    pending_user_text: str = '',
) -> tuple[str, str]:
    chosen, source, _debug = select_current_user_turn(
        question=question,
        original_question=original_question,
        state=state,
        pending_user_text=pending_user_text,
    )
    return chosen, source


def select_current_user_turn(
    *,
    question: str = '',
    original_question: str = '',
    state: dict | None = None,
    pending_user_text: str = '',
) -> tuple[str, str, str]:
    """Pick the on-screen turn. Never prefer a leftover Past-chats title.

    Chat input is a persistent Gradio State. After you send 'test' in one
    chat, the next generate can still stash 'test' even though the Chat-tab
    textbox (gathered first) and the rendered prompt hold the real message.
    Score every candidate; a short past-chat title always loses to a longer
    different string.
    """
    state = state or {}
    titles = _past_chat_titles(state)
    last_completed = last_user_message(state.get('history'), '')
    candidates: list[tuple[str, str, int]] = []

    def add(text: str, source: str, rank: int) -> None:
        cleaned = _clean_user_text(text)
        if not cleaned:
            return
        candidates.append((cleaned, source, rank))

    add(pending_user_text, 'stash', 20)
    add(_chat_textbox(state), 'textbox', 100)
    add(_gradio_component_text('textbox'), 'gradio-textbox', 95)
    add(_gradio_component_text('Chat input'), 'gradio-chat-input', 40)
    live_hist = _gradio_component_value('history')
    add(
        last_unfinished_user_message(live_hist if isinstance(live_hist, dict) else None),
        'live-unfinished',
        110,
    )
    add(last_unfinished_user_message(state.get('history')), 'state-unfinished', 30)
    prompt_turns: list[str] = []
    for blob in (original_question, question):
        prompt_turns.extend(extract_all_user_turns(blob or ''))
    for idx, turn in enumerate(prompt_turns):
        add(turn, f'prompt-{idx}', 50)

    debug_lines = [
        f'candidates={len(candidates)} titles={sorted(titles)[:8]!r}',
        f'unique_id={state.get("unique_id")!r}',
        f'last_completed={last_completed[:80]!r}' if last_completed else 'last_completed=',
    ]
    for text, source, rank in candidates:
        debug_lines.append(f'  {source} rank={rank} len={len(text)} {text[:80]!r}')

    if not candidates:
        return '', '', '\n'.join(debug_lines)

    def score(item: tuple[str, str, int]) -> tuple[int, int, int, int, int]:
        text, source, rank = item
        stale = 0
        if text in titles and len(text) < 120:
            stale = -10000
        elif last_completed and text == last_completed and len(text) < 120:
            if any(len(other) > len(text) + 10 for other, _s, _r in candidates):
                stale = -5000
        wrapped = -1 if '<|im_start|>' in text or '<|start_header_id|>' in text else 0
        recency = 0
        if source.startswith('prompt-'):
            try:
                recency = int(source.split('-')[1])
            except ValueError:
                recency = 0
        return (stale, wrapped, rank, recency, len(text))

    chosen, source, rank = max(candidates, key=score)
    debug_lines.append(f'picked source={source} rank={rank} len={len(chosen)}')
    return chosen, source, '\n'.join(debug_lines)


def _clean_user_text(text: str | None) -> str:
    if text is None:
        return ''
    if isinstance(text, dict):
        text = text.get('text') or ''
    stripped = str(text).strip()
    if not stripped or _is_placeholder(stripped):
        return ''
    return stripped


def extract_all_user_turns(text: str) -> list[str]:
    """Every user turn found in a rendered prompt, oldest first."""
    if not text:
        return []
    if '<|BEGIN-VISIBLE-CHAT|>' in text:
        text = text.split('<|BEGIN-VISIBLE-CHAT|>')[-1]
    if '<|begin-visible-chat|>' in text:
        text = text.split('<|begin-visible-chat|>')[-1]
    found: list[str] = []
    seen: set[str] = set()
    for pattern in (
        _CHATML_USER,
        _LLAMA3_USER,
        _GEMMA_USER,
        _INST_USER,
        _PIPE_USER,
    ):
        for match in pattern.findall(text):
            candidate = match.strip()
            if not candidate or _is_placeholder(candidate) or candidate in seen:
                continue
            seen.add(candidate)
            found.append(candidate)
    if found:
        return found
    stripped = text.strip()
    if stripped and not _is_placeholder(stripped) and not any(
        marker in stripped for marker in _PROMPT_MARKERS
    ):
        return [stripped]
    return []


def extract_last_user_from_prompt(text: str) -> str:
    """Last user turn from a rendered chat prompt, or a plain user string."""
    turns = extract_all_user_turns(text)
    return turns[-1] if turns else ''


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


def _past_chat_titles(state: dict | None) -> set[str]:
    titles: set[str] = set()
    try:
        from modules import chat as ooba_chat

        pairs = ooba_chat.find_all_histories_with_first_prompts(state or {})
        for first_prompt, _uid in pairs or []:
            label = str(first_prompt).strip()
            if label:
                titles.add(label)
    except Exception:
        pass
    return titles


def _gradio_component_value(name: str):
    try:
        from modules import shared

        comp = (getattr(shared, 'gradio', None) or {}).get(name)
        if comp is None:
            return None
        for attr in ('value', '_value'):
            if hasattr(comp, attr):
                return getattr(comp, attr)
    except Exception:
        return None
    return None


def _gradio_component_text(name: str) -> str:
    return _clean_user_text(_gradio_component_value(name))


def _is_processing_bot(text: str) -> bool:
    lowered = (text or '').strip().lower()
    if not lowered:
        return True
    return any(
        marker in lowered
        for marker in ('typing', 'processing', 'generating', 'thinking', '⏳')
    )


def _is_other_chat_title(text: str, state: dict) -> bool:
    """True when `text` is only the first-prompt label of a different saved chat."""
    label = (text or '').strip()
    if not label:
        return False
    try:
        from modules import chat as ooba_chat

        pairs = ooba_chat.find_all_histories_with_first_prompts(state)
    except Exception:
        return False
    viewed = ''
    try:
        from modules import chat as ooba_chat

        viewed = str(getattr(ooba_chat, 'viewing_unique_id', None) or '')
    except Exception:
        viewed = str(state.get('unique_id') or '')
    for first_prompt, uid in pairs or []:
        if str(first_prompt).strip() != label:
            continue
        if viewed and str(uid) == viewed:
            return False
        return True
    return False


def _chat_textbox(state: dict) -> str:
    """Chat-tab input only. Never textbox-default (Default/Notebook tab)."""
    value = state.get('textbox')
    if isinstance(value, dict):
        value = value.get('text') or ''
    if isinstance(value, str):
        text = value.strip()
        if text and not _is_placeholder(text):
            return text
    return ''


def _pairs(history: dict | None) -> list:
    if not history:
        return []
    return history.get('internal') or history.get('visible') or []
