"""decomposer: meta (the user, 2026-10-25; journal/design/meta-prompts.md): the model writes the
planner's instructions, frozen (from a file) or dynamic (per request); only the frame is fixed."""

from unittest.mock import patch

import pytest

from reasoning_sub_agents.config.registry import BuildContext, REGISTRY
from reasoning_sub_agents.config.schema import OptionsConfig
from reasoning_sub_agents.schemas import DecomposeSubTask
from reasoning_sub_agents.task_decomposition import meta_decomposition as M
from tests.mock_openai import MockOpenAI

MOD = 'reasoning_sub_agents.task_decomposition.meta_decomposition'
INSTRUCTIONS = 'You are the planner. Make one sub-task per file, each delivering the whole file, ' \
               'with its exact interface copied from the request into its context.'
TASK = DecomposeSubTask(meta_type='sub_task_detail', name='Write wordcount.py', type='code',
                        description='d', context='c', complexity=2, objective='o')


def _decompose(decomposer, request='Write wordcount.py'):
    with patch(f'{MOD}.get_streamed_json_response', return_value=[TASK]) as sent:
        tasks = decomposer.generate_sub_tasks(request)
    return tasks, sent.call_args.kwargs['llm_input'].messages[-1].content


def test_frozen_puts_the_files_instructions_between_the_request_and_the_schema(tmp_path):
    f = tmp_path / 'decompose.gemma.txt'
    f.write_text(INSTRUCTIONS + '\n')
    tasks, prompt = _decompose(M.MetaPromptDecomposer(MockOpenAI(), mode='frozen', instructions_file=str(f)))
    assert [t.decomposed_sub_task.name for t in tasks] == ['Write wordcount.py']
    assert prompt.index('Write wordcount.py') < prompt.index('one sub-task per file') < prompt.index('Output JSON in this schema')
    assert 'Use 2-5 sub-tasks' not in prompt  # the hand-written rules are not in the frame


def test_dynamic_writes_instructions_for_this_request_and_logs_them():
    written = []

    def reply(**kwargs):
        written.append(kwargs['llm_input'].messages[-1].content)
        return 'stream'
    d = M.MetaPromptDecomposer(MockOpenAI(), mode='dynamic')
    with patch(f'{MOD}.stream_conversation', side_effect=reply), patch(f'{MOD}.extract_content', return_value=INSTRUCTIONS):
        _, prompt = _decompose(d, 'Write csv2json.py')
    assert 'Write csv2json.py' in written[0] and 'How the pipeline works' in written[0]
    assert INSTRUCTIONS in prompt
    assert d.history['meta_prompt']['mode'] == 'dynamic' and d.history['meta_prompt']['instructions'] == INSTRUCTIONS


def test_unusable_instructions_are_asked_again_then_refused():
    d = M.MetaPromptDecomposer(MockOpenAI(), mode='dynamic')
    with patch(f'{MOD}.stream_conversation', return_value='s'), \
            patch(f'{MOD}.extract_content', side_effect=['too short', INSTRUCTIONS]):
        _, prompt = _decompose(d)
    assert [a['problem'] for a in d.history['meta_prompt']['attempts']] == ['too short (9 characters)', None]
    with patch(f'{MOD}.stream_conversation', return_value='s'), patch(f'{MOD}.extract_content', return_value='no'):
        with pytest.raises(ValueError, match='unusable after 2 attempts'):
            M.write_instructions(MockOpenAI(), 'x')


def test_braces_in_instructions_reach_the_planner_unchanged(tmp_path):
    f = tmp_path / 'i.txt'
    f.write_text(INSTRUCTIONS + ' Example item: {"name": "Write a.py"}')
    _, prompt = _decompose(M.MetaPromptDecomposer(MockOpenAI(), instructions_file=str(f)))
    assert '{"name": "Write a.py"}' in prompt


def test_frozen_needs_a_usable_file_and_the_registry_builds_it(tmp_path):
    with pytest.raises(ValueError, match='meta_prompt_file'):
        M.MetaPromptDecomposer(MockOpenAI(), mode='frozen')
    bad = tmp_path / 'bad.txt'
    bad.write_text('short')
    with pytest.raises(ValueError, match='too short'):
        M.MetaPromptDecomposer(MockOpenAI(), instructions_file=str(bad))
    good = tmp_path / 'good.txt'
    good.write_text(INSTRUCTIONS)
    built = REGISTRY['decomposer']['meta'].factory(BuildContext(
        llm_client=MockOpenAI(), options=OptionsConfig(meta_prompt='frozen', meta_prompt_file=str(good))))
    assert isinstance(built, M.MetaPromptDecomposer) and built.frozen == INSTRUCTIONS


def test_the_meta_prompt_states_the_workflow_and_what_is_fixed():
    frozen, dynamic = M.meta_prompt(None), M.meta_prompt('Write x.py')
    for p in (frozen, dynamic):
        assert 'How the pipeline works' in p and 'sub_task_detail' in p and '"$defs"' in p
    assert 'used unchanged for every request' in frozen and 'Write x.py' in dynamic
