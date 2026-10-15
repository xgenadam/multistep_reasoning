from oobabooga_extension.chat_adapter import (  # module moved out of the package
    chat_id_from_state,
    compact_chat_history,
)


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


def test_chat_id_does_not_take_last_radio_row():
    state = {'unique_id': ['chat-new', 'chat-old', 'test']}
    assert chat_id_from_state(state) == 'default'
