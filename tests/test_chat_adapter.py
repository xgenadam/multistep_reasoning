from reasoning_sub_agents.chat_adapter import (
    chat_id_from_state,
    compact_chat_history,
    compact_chat_history_from_state,
    last_user_message,
    last_user_message_from_state,
)


def test_last_user_message_from_internal_history():
    history = {
        'internal': [
            ['hello', 'hi'],
            ['write chapter 2', ''],
        ]
    }
    assert last_user_message(history) == 'write chapter 2'


def test_compact_history_skips_unfinished_turn():
    history = {
        'internal': [
            ['hello', 'Hi there.'],
            ['write a book', 'Once upon a time...'],
            ['make chapter 3 darker', ''],
        ]
    }
    compact = compact_chat_history(history)
    assert 'hello' in compact
    assert 'Once upon a time' in compact
    assert 'make chapter 3 darker' not in compact


def test_compact_history_limits_turns():
    history = {
        'internal': [[f'u{i}', f'a{i}'] for i in range(10)]
    }
    compact = compact_chat_history(history, max_turns=2)
    assert 'u8' in compact
    assert 'u9' in compact
    assert 'u0' not in compact


def test_state_helpers_prefer_history_then_messages():
    state = {
        'unique_id': 'chat-123',
        'history': {'internal': [['from history', 'reply']]},
        'messages': [{'role': 'user', 'content': 'from messages'}],
    }
    assert last_user_message_from_state(state) == 'from history'
    assert chat_id_from_state(state) == 'chat-123'
    assert 'from history' in compact_chat_history_from_state(state)


def test_state_helpers_fall_back_to_messages():
    state = {
        'messages': [
            {'role': 'user', 'content': 'first'},
            {'role': 'assistant', 'content': 'answer'},
            {'role': 'user', 'content': 'second'},
        ]
    }
    assert last_user_message_from_state(state) == 'second'
    compact = compact_chat_history_from_state(state)
    assert 'first' in compact
    assert 'answer' in compact
    assert 'second' not in compact
