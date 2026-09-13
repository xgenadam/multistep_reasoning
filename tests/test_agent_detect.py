from reasoning_sub_agents.agent_detect import (
    INNER_SKIP_SENTINEL,
    looks_like_agent_turn,
    should_skip_orchestrator,
)


def test_chat_only_plain_chat_is_not_skipped():
    assert should_skip_orchestrator(
        intercept_mode='chat_only',
        question='Write a short poem about rain.',
        state={'history': {'internal': [['hi', 'hello']]}},
    ) is False


def test_never_always_skips():
    assert should_skip_orchestrator(
        intercept_mode='never',
        question='Write a poem',
    ) is True


def test_always_only_skips_inner_sentinel():
    assert should_skip_orchestrator(
        intercept_mode='always',
        question='Write a poem',
    ) is False
    assert should_skip_orchestrator(
        intercept_mode='always',
        question=f'{INNER_SKIP_SENTINEL} continue',
    ) is True


def test_tools_in_state_are_agent():
    assert looks_like_agent_turn(
        state={'tools': [{'type': 'function', 'function': {'name': 'read_file'}}]},
        question='fix the bug',
    )


def test_cline_xml_in_prompt():
    prompt = 'You are Cline. Use <read_file> and <execute_command> then <attempt_completion>.'
    assert looks_like_agent_turn(question=prompt)


def test_grok_tool_names_in_system():
    assert looks_like_agent_turn(
        state={'system': 'You may call run_terminal_command and search_replace.'},
        question='add a test',
    )


def test_tool_role_messages():
    assert looks_like_agent_turn(
        state={
            'messages': [
                {'role': 'user', 'content': 'edit foo'},
                {'role': 'tool', 'content': 'file contents'},
            ]
        }
    )


def test_inner_sentinel_in_history():
    assert looks_like_agent_turn(
        history={'internal': [[f'{INNER_SKIP_SENTINEL} sys', 'ok']]},
        question='ignored',
    )
