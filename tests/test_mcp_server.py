from unittest.mock import MagicMock

from openai.types.chat import ChatCompletionMessage

from reasoning_sub_agents.document import Document, Part, PartKind
from reasoning_sub_agents.mcp_server import McpHandler, ReasoningSessionStore
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator


def _store(text: str = 'composed document') -> ReasoningSessionStore:
    orch = MagicMock(spec=TaskOrchestrator)
    orch.options.render = 'markdown_with_files'

    def query(prompt, document=None, chat_context=None, **kwargs):
        if document is not None and not document.parts:
            document.parts.append(
                Part(
                    id='out',
                    kind=PartKind.SECTION,
                    title='Out',
                    body=text,
                )
            )
        return ChatCompletionMessage(role='assistant', content=text)

    orch.query.side_effect = query
    return ReasoningSessionStore(orch)


def test_tools_list():
    handler = McpHandler(_store())
    reply = handler.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    names = {tool['name'] for tool in reply['result']['tools']}
    assert names == {'deep_reason', 'reset_session'}


def test_deep_reason_returns_document_text():
    handler = McpHandler(_store('plan goes here'))
    reply = handler.handle(
        {
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/call',
            'params': {
                'name': 'deep_reason',
                'arguments': {'prompt': 'Plan the refactor'},
            },
        }
    )
    assert reply['result']['isError'] is False
    assert reply['result']['content'][0]['text'] == 'plan goes here'


def test_session_id_reuses_document():
    store = _store('v1')
    handler = McpHandler(store)
    handler.handle(
        {
            'jsonrpc': '2.0',
            'id': 3,
            'method': 'tools/call',
            'params': {
                'name': 'deep_reason',
                'arguments': {
                    'prompt': 'first',
                    'session_id': 'chat-1',
                },
            },
        }
    )
    doc = store._sessions['chat-1']
    assert doc.has_part('out')
    handler.handle(
        {
            'jsonrpc': '2.0',
            'id': 4,
            'method': 'tools/call',
            'params': {
                'name': 'reset_session',
                'arguments': {'session_id': 'chat-1'},
            },
        }
    )
    assert 'chat-1' not in store._sessions


def test_missing_prompt_is_error():
    handler = McpHandler(_store())
    reply = handler.handle(
        {
            'jsonrpc': '2.0',
            'id': 5,
            'method': 'tools/call',
            'params': {'name': 'deep_reason', 'arguments': {}},
        }
    )
    assert reply['result']['isError'] is True
