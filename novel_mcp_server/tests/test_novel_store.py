import json
from pathlib import Path
from unittest.mock import MagicMock

from openai.types.chat import ChatCompletionMessage

from novel_mcp_server.config import NovelConfig
from novel_mcp_server.server import McpHandler, NovelStore
from reasoning_sub_agents.document import Part, PartKind
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator


def _store(tmp_path: Path, *, to_files: bool = True, longform: bool = True) -> NovelStore:
    orch = MagicMock(spec=TaskOrchestrator)
    orch.options.render = 'markdown_with_files'

    def query(prompt, document=None, chat_context=None, **kwargs):
        if document is not None:
            document.parts.append(
                Part(
                    id='chapter-1',
                    kind=PartKind.SECTION,
                    title='Chapter 1',
                    body='The oak wand hummed.',
                )
            )
        return ChatCompletionMessage(
            role='assistant', content='# Chapter 1\n\nThe oak wand hummed.'
        )

    orch.query.side_effect = query
    config = NovelConfig.model_validate(
        {
            'orchestrator_yaml': '../orchestrator.yaml',
            'options': {
                'conversation_search': True,
                'longform_storage': longform,
                'storage': {
                    'backend': 'filesystem',
                    'root': str(tmp_path / 'workspaces'),
                },
                'output': {'to_client': True, 'to_files': to_files},
            },
        }
    )
    return NovelStore(orch, config, tmp_path / 'config.yaml')


def test_bind_list_read_search_files(tmp_path: Path):
    store = _store(tmp_path)
    store.bind_work('s1', 'Cosmere', 'Mistborn', 'The Final Empire')
    store.deep_reason('Write chapter 1', session_id='s1')
    listed = json.loads(store.list_documents('s1'))
    ids = {item['id'] for item in listed}
    assert 'chapter-1' in ids
    body = store.read_document('s1', 'chapter-1')
    assert 'oak wand' in body
    hits = json.loads(store.search_workspace('s1', 'oak wand'))
    assert hits[0]['id'] == 'chapter-1'


def test_deep_reason_mentions_written_paths(tmp_path: Path):
    store = _store(tmp_path)
    store.bind_work('s1', '40k', 'Eisenhorn', 'Xenos')
    text = store.deep_reason('Write', session_id='s1')
    assert 'Wrote:' in text
    assert 'chapter-1.md' in text


def test_conversation_search(tmp_path: Path):
    store = _store(tmp_path, to_files=False, longform=False)
    store.append_conversation('s1', 'user', 'What wand does she have?')
    store.append_conversation(
        's1', 'assistant', 'Vine wood, later changed to oak.'
    )
    hits = json.loads(store.search_conversation('s1', 'oak'))
    assert hits
    assert 'oak' in hits[0]['excerpt'].lower()


def test_unbound_deep_reason_does_not_write_files(tmp_path: Path):
    store = _store(tmp_path, to_files=False, longform=False)
    store.deep_reason('Write a scene', session_id='s1')
    root = tmp_path / 'workspaces'
    written = list(root.rglob('*.md')) if root.exists() else []
    assert written == []


def test_bind_work_persists_even_when_to_files_false(tmp_path: Path):
    store = _store(tmp_path, to_files=False, longform=False)
    store.bind_work('s1', 'U', 'S', 'W')
    store.deep_reason('Write', session_id='s1')
    latest = (
        tmp_path
        / 'workspaces'
        / 'universes'
        / 'u'
        / 'series'
        / 's'
        / 'works'
        / 'w'
        / 'documents'
        / '_latest.md'
    )
    assert latest.is_file()
    assert 'oak wand' in latest.read_text()


def test_bind_hydrates_existing_files(tmp_path: Path):
    store = _store(tmp_path, to_files=False, longform=False)
    store.bind_work('s1', 'U', 'S', 'W')
    store.deep_reason('Write', session_id='s1')
    other = _store(tmp_path, to_files=False, longform=False)
    other.bind_work('s2', 'U', 'S', 'W')
    assert other._documents['s2'].has_part('chapter-1')
    assert 'oak wand' in other._documents['s2'].get_part('chapter-1').body


def test_mcp_tools_list(tmp_path: Path):
    handler = McpHandler(_store(tmp_path))
    reply = handler.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    names = {tool['name'] for tool in reply['result']['tools']}
    assert 'bind_work' in names
    assert 'search_conversation' in names
    assert 'deep_reason' in names
