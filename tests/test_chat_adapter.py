from reasoning_sub_agents.chat_adapter import (
    chat_id_from_state,
    compact_chat_history,
    compact_chat_history_from_state,
    extract_last_user_from_prompt,
    last_user_message,
    last_user_message_from_state,
    pick_current_user_text,
    resolve_current_user_text,
)


def test_skips_oobabooga_begin_visible_chat_sentinel():
    history = {
        'internal': [
            ['<|BEGIN-VISIBLE-CHAT|>', ''],
            ['Write a sonnet about Mars', ''],
        ]
    }
    assert last_user_message(history) == 'Write a sonnet about Mars'


def test_sentinel_only_history_unwraps_packed_fallback():
    packed = (
        '<|BEGIN-VISIBLE-CHAT|>\n[INST]Explain photosynthesis[/INST]'
    )
    history = {'internal': [['<|BEGIN-VISIBLE-CHAT|>', '']]}
    assert last_user_message(history, fallback=packed) == 'Explain photosynthesis'


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


def test_resolve_ignores_completed_history_and_default_tab():
    prompt = (
        '<|im_start|>system\nYou are helpful.<|im_end|>\n'
        '<|im_start|>user\ntest<|im_end|>\n'
        '<|im_start|>assistant\nAcknowledged.<|im_end|>\n'
        '<|im_start|>user\nWrite a detailed chapter about photosynthesis<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    state = {
        'unique_id': 'chat-new',
        'history': {
            'internal': [
                ['<|BEGIN-VISIBLE-CHAT|>', ''],
                ['test', 'Acknowledged.'],
            ]
        },
        'textbox-default': 'test',
        'textbox': {'text': '', 'files': []},
    }
    assert (
        resolve_current_user_text(
            question=prompt,
            original_question=prompt,
            state=state,
        )
        == 'Write a detailed chapter about photosynthesis'
    )


def test_resolve_ignores_default_tab_when_history_is_placeholder():
    prompt = (
        '<|im_start|>user\nExplain mitochondria<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    state = {
        'history': {'internal': [['<|BEGIN-VISIBLE-CHAT|>', '']]},
        'textbox-default': 'test',
    }
    assert (
        resolve_current_user_text(
            question=prompt, original_question=prompt, state=state
        )
        == 'Explain mitochondria'
    )


def test_resolve_pending_beats_unfinished_history_test():
    prompt = (
        '<|im_start|>user\ntest<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    state = {
        'history': {
            'internal': [
                ['test', ''],
            ]
        },
        'textbox-default': 'test',
    }
    assert (
        resolve_current_user_text(
            question=prompt,
            original_question=prompt,
            state=state,
            pending_user_text='Write a detailed chapter about photosynthesis',
        )
        == 'Write a detailed chapter about photosynthesis'
    )


def test_resolve_ignores_unfinished_history_when_prompt_has_real_turn():
    prompt = (
        '<|im_start|>user\nWrite a detailed chapter about photosynthesis<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    state = {
        'history': {'internal': [['test', '']]},
        'textbox-default': 'test',
    }
    assert (
        resolve_current_user_text(
            question=prompt, original_question=prompt, state=state
        )
        == 'Write a detailed chapter about photosynthesis'
    )


def test_resolve_plain_string_without_template():
    assert (
        resolve_current_user_text(
            question='Just a short question',
            original_question='Just a short question',
            state={'textbox-default': 'test'},
        )
        == 'Just a short question'
    )


def test_extract_chatml_last_user():
    prompt = (
        '<|im_start|>user\ntest<|im_end|>\n'
        '<|im_start|>assistant\nok<|im_end|>\n'
        '<|im_start|>user\nreal request<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    assert extract_last_user_from_prompt(prompt) == 'real request'


def test_stale_stash_test_loses_to_real_textbox():
    prompt = (
        '<|im_start|>user\ntest<|im_end|>\n'
        '<|im_start|>assistant\nAcknowledged.<|im_end|>\n'
        '<|im_start|>user\nWrite a detailed chapter about photosynthesis<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    state = {
        'unique_id': 'chat-current',
        'history': {'internal': [['test', 'Acknowledged.']]},
        'textbox': {
            'text': 'Write a detailed chapter about photosynthesis',
            'files': [],
        },
        'textbox-default': 'test',
    }
    text, source = pick_current_user_text(
        question=prompt,
        original_question=prompt,
        state=state,
        pending_user_text='test',
    )
    assert text == 'Write a detailed chapter about photosynthesis'
    assert source in {'textbox', 'prompt-1', 'prompt-0'}


def test_stale_stash_test_loses_to_longer_prompt_turn():
    prompt = (
        '<|im_start|>user\ntest<|im_end|>\n'
        '<|im_start|>assistant\nok<|im_end|>\n'
        '<|im_start|>user\nExplain mitochondria in two paragraphs<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    text, source = pick_current_user_text(
        question=prompt,
        original_question=prompt,
        state={'history': {'internal': [['test', 'ok']]}},
        pending_user_text='test',
    )
    assert text == 'Explain mitochondria in two paragraphs'
    assert source.startswith('prompt')


def test_textbox_wins_over_prompt_that_is_just_test():
    prompt = (
        '<|im_start|>user\ntest<|im_end|>\n'
        '<|im_start|>assistant\n'
    )
    state = {
        'unique_id': 'chat-current',
        'history': {'internal': [['test', 'Acknowledged.']]},
        'textbox': {'text': 'Write a detailed chapter about photosynthesis', 'files': []},
        'textbox-default': 'test',
    }
    text, source = pick_current_user_text(
        question=prompt, original_question=prompt, state=state
    )
    assert text == 'Write a detailed chapter about photosynthesis'
    assert source == 'textbox'


def test_chat_id_does_not_take_last_radio_row():
    state = {'unique_id': ['chat-new', 'chat-old', 'test']}
    assert chat_id_from_state(state) == 'default'


def test_does_not_use_textbox_default_as_current_turn():
    state = {
        'history': {'internal': [['<|BEGIN-VISIBLE-CHAT|>', '']]},
        'textbox-default': 'test',
        'textbox': '',
    }
    assert last_user_message_from_state(state, fallback='') == ''
    assert (
        resolve_current_user_text(question='', original_question='', state=state)
        == ''
    )
