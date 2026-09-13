"""Helpers for turning oobabooga / Open WebUI chat state into orchestrator inputs."""


def last_user_message(history: dict | None, fallback: str = '') -> str:
    pairs = _pairs(history)
    if pairs and pairs[-1] and pairs[-1][0]:
        return str(pairs[-1][0])
    return fallback


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
                return str(content)
    return fallback


def compact_chat_history(history: dict | None, *, max_turns: int = 6) -> str:
    """
    Previous completed user/assistant turns, excluding the current unfinished turn.
    """
    completed: list[str] = []
    for pair in _pairs(history):
        if not pair or not pair[0]:
            continue
        user = str(pair[0]).strip()
        bot = str(pair[1]).strip() if len(pair) > 1 and pair[1] else ''
        if not bot:
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
    state = state or {}
    for key in ('unique_id', 'id', 'chat_id'):
        value = state.get(key)
        if value:
            return str(value)
    return fallback


def _pairs(history: dict | None) -> list:
    if not history:
        return []
    return history.get('internal') or history.get('visible') or []
