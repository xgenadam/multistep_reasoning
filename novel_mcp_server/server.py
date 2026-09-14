"""
stdio MCP server for longform workspaces.

Grok Build / OpenCode / Cline is the client. This process exposes tools that
run TaskOrchestrator and, for bound works, write chapter files the TUI can open.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessage

from reasoning_sub_agents.document import Document, Part, PartKind
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

from .config import NovelConfig
from .conversation_log import ConversationLog
from .workspace import Workspace

PROTOCOL_VERSION = '2024-11-05'
SERVER_NAME = 'novel-mcp'
SERVER_VERSION = '0.1.0'

logger = logging.getLogger('novel_mcp_server')


class NovelStore:
    """Session documents, disk workspace, and conversation log behind MCP tools."""

    def __init__(
        self,
        orchestrator: TaskOrchestrator,
        config: NovelConfig,
        config_path: Path,
    ) -> None:
        self.orchestrator = orchestrator
        self.config = config
        options = config.options
        root = config.storage_root(config_path)
        self.workspace = Workspace(root)
        self.conversation = ConversationLog(root)
        self.conversation_search = options.conversation_search
        self.to_client = options.output.to_client
        self.to_files_unbound = options.output.to_files
        self._documents: dict[str, Document] = {}

    def _document(self, session_id: str | None) -> Document | None:
        """In-memory Document for this session; None if the caller omitted session_id."""
        if not session_id:
            return None
        document = self._documents.get(session_id)
        if document is None:
            document = Document.empty(
                render_mode=self.orchestrator.options.render
            )
            self._documents[session_id] = document
        return document

    def bind_work(
        self, session_id: str, universe: str, series: str, work: str
    ) -> str:
        """Attach a session to a work on disk; hydrate existing files or flush in-memory parts."""
        existing = self._documents.get(session_id)
        binding = self.workspace.bind(session_id, universe, series, work)
        if existing is not None and existing.parts:
            self._persist(session_id, existing, existing.render())
        else:
            self._documents[session_id] = self._hydrate(session_id)
        directory = self.workspace.documents_dir(session_id)
        return (
            f'bound {session_id} -> {binding.universe}/{binding.series}/'
            f'{binding.work} documents_dir={directory}'
        )

    def _writes_files(self, session_id: str | None) -> bool:
        """Bound sessions always persist; unbound only if output.to_files is true."""
        if not session_id:
            return False
        if self.workspace.binding(session_id) is not None:
            return True
        return self.to_files_unbound

    def reset_session(self, session_id: str) -> str:
        """Drop in-memory state, unbind, and delete the conversation log. Files on disk stay."""
        self._documents.pop(session_id, None)
        self.workspace.unbind(session_id)
        self.conversation.clear(session_id)
        return f'reset {session_id}'

    def deep_reason(
        self,
        prompt: str,
        session_id: str | None = None,
        chat_context: str | None = None,
    ) -> str:
        """Run decompose/execute/compose; write files if bound; return markdown plus paths."""
        if (
            self.to_files_unbound
            and session_id
            and self.workspace.binding(session_id) is None
        ):
            self.workspace.bind(
                session_id,
                self.config.options.storage.universe or 'default',
                'default',
                session_id,
            )
        document = self._document(session_id)
        response = self.orchestrator.query(
            prompt,
            document=document,
            chat_context=chat_context or None,
        )
        message = response[0] if isinstance(response, tuple) else response
        if isinstance(message, ChatCompletionMessage):
            text = message.content or ''
        else:
            text = str(message)

        if self.conversation_search and session_id:
            self.conversation.append(session_id, 'user', prompt)
            self.conversation.append(session_id, 'assistant', text)

        paths: list[str] = []
        if self._writes_files(session_id):
            paths = self._persist(session_id, document, text)

        if not self.to_client:
            if paths:
                return 'Wrote:\n' + '\n'.join(paths)
            return 'to_client is false; nothing returned to the client.'

        if paths:
            return text.rstrip() + '\n\nWrote:\n' + '\n'.join(paths)
        return text

    def list_documents(self, session_id: str) -> str:
        """JSON outline of disk files when bound, else in-memory parts."""
        if self.workspace.binding(session_id):
            return json.dumps(self.workspace.list_documents(session_id), indent=2)
        document = self._documents.get(session_id)
        if document is None:
            return json.dumps([])
        return json.dumps(
            [
                {
                    'id': part.id,
                    'title': part.title,
                    'kind': part.kind,
                    'chars': len(part.body),
                }
                for part in document.parts
            ],
            indent=2,
        )

    def read_document(self, session_id: str, doc_id: str) -> str:
        """Load one chapter/part for the TUI or a follow-up edit."""
        if self.workspace.binding(session_id):
            return self.workspace.read_document(session_id, doc_id)
        document = self._documents.get(session_id)
        if document is None or not document.has_part(doc_id):
            raise FileNotFoundError(f'no document {doc_id!r}')
        return document.get_part(doc_id).body

    def search_workspace(self, session_id: str, query: str) -> str:
        """Keyword search over the bound work (plot/detail lookup without dumping the book)."""
        if self.workspace.binding(session_id):
            return json.dumps(
                self.workspace.search_workspace(session_id, query), indent=2
            )
        document = self._documents.get(session_id)
        if document is None:
            return json.dumps([])
        needle = query.lower()
        hits = []
        for part in document.parts:
            index = part.body.lower().find(needle)
            if index < 0:
                continue
            hits.append(
                {
                    'id': part.id,
                    'index': index,
                    'excerpt': part.body[max(0, index - 80) : index + 80],
                }
            )
        return json.dumps(hits, indent=2)

    def append_conversation(
        self, session_id: str, role: str, text: str, summary: str | None = None
    ) -> str:
        """Record a turn for later search_conversation (also called from deep_reason)."""
        if not self.conversation_search:
            return 'conversation_search is disabled'
        self.conversation.append(session_id, role, text, summary)
        return 'appended'

    def search_conversation(self, session_id: str, query: str) -> str:
        """Find older turns without putting the full chat into the model context."""
        if not self.conversation_search:
            return json.dumps([])
        return json.dumps(
            self.conversation.search(session_id, query), indent=2
        )

    def _persist(
        self, session_id: str, document: Document | None, fallback: str
    ) -> list[str]:
        """Write parts, _index.md, and _latest.md; return paths for the tool result."""
        paths: list[str] = []
        if document is not None and document.parts:
            for part in document.parts:
                heading = f'# {part.title}\n\n' if part.title else ''
                path = self.workspace.write_document(
                    session_id, part.id, heading + part.body
                )
                paths.append(str(path))
            index = self.workspace.write_document(
                session_id,
                '_index',
                '# Index\n\n'
                + '\n'.join(f'- {part.id}: {part.title}' for part in document.parts),
            )
            paths.append(str(index))
            latest = document.parts[-1]
            latest_heading = f'# {latest.title}\n\n' if latest.title else ''
            paths.append(
                str(
                    self.workspace.write_document(
                        session_id, '_latest', latest_heading + latest.body
                    )
                )
            )
        else:
            path = self.workspace.write_document(
                session_id, 'main', fallback or ''
            )
            paths.append(str(path))
            paths.append(
                str(self.workspace.write_document(session_id, '_latest', fallback or ''))
            )
        return paths

    def _hydrate(self, session_id: str) -> Document:
        """Rebuild an in-memory Document from existing markdown after bind_work."""
        document = Document.empty(render_mode=self.orchestrator.options.render)
        if self.workspace.binding(session_id) is None:
            return document
        for item in self.workspace.list_documents(session_id):
            if item['id'].startswith('_'):
                continue
            raw = Path(item['path']).read_text(encoding='utf-8')
            title = item['id']
            body = raw
            if raw.startswith('# '):
                first, _, rest = raw.partition('\n')
                title = first[2:].strip() or title
                body = rest.lstrip('\n')
            document.parts.append(
                Part(
                    id=item['id'],
                    kind=PartKind.SECTION,
                    title=title,
                    body=body,
                )
            )
        return document


class McpHandler:
    """JSON-RPC methods initialize / tools/list / tools/call over stdio."""

    def __init__(self, store: NovelStore) -> None:
        self.store = store

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch one MCP request; notifications (no id) return None."""
        if 'method' not in message:
            return _error(message.get('id'), -32600, 'Invalid Request')
        method = message['method']
        msg_id = message.get('id')
        params = message.get('params') or {}
        if msg_id is None:
            return None
        if method == 'initialize':
            return _result(
                msg_id,
                {
                    'protocolVersion': PROTOCOL_VERSION,
                    'capabilities': {'tools': {}},
                    'serverInfo': {
                        'name': SERVER_NAME,
                        'version': SERVER_VERSION,
                    },
                },
            )
        if method == 'ping':
            return _result(msg_id, {})
        if method == 'tools/list':
            return _result(msg_id, {'tools': _tool_defs()})
        if method == 'tools/call':
            return self._call_tool(msg_id, params)
        return _error(msg_id, -32601, f'Method not found: {method}')

    def _call_tool(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Run a named tool and wrap the string result as MCP content."""
        name = params.get('name')
        arguments = params.get('arguments') or {}
        try:
            text = self._dispatch(name, arguments)
            return _tool_result(msg_id, text)
        except Exception as exc:
            logger.exception('tool %s failed', name)
            return _tool_result(msg_id, f'Error: {exc}', is_error=True)

    def _dispatch(self, name: str | None, arguments: dict[str, Any]) -> str:
        """Map tool name → NovelStore method."""
        if name == 'deep_reason':
            prompt = arguments.get('prompt') or arguments.get('question') or ''
            if not str(prompt).strip():
                raise ValueError('prompt is required')
            return self.store.deep_reason(
                str(prompt),
                session_id=arguments.get('session_id'),
                chat_context=arguments.get('chat_context'),
            )
        if name == 'reset_session':
            session_id = _require(arguments, 'session_id')
            return self.store.reset_session(session_id)
        if name == 'bind_work':
            return self.store.bind_work(
                _require(arguments, 'session_id'),
                _require(arguments, 'universe'),
                _require(arguments, 'series'),
                _require(arguments, 'work'),
            )
        if name == 'list_documents':
            return self.store.list_documents(_require(arguments, 'session_id'))
        if name == 'read_document':
            return self.store.read_document(
                _require(arguments, 'session_id'),
                _require(arguments, 'doc_id'),
            )
        if name == 'search_workspace':
            return self.store.search_workspace(
                _require(arguments, 'session_id'),
                _require(arguments, 'query'),
            )
        if name == 'search_conversation':
            return self.store.search_conversation(
                _require(arguments, 'session_id'),
                _require(arguments, 'query'),
            )
        if name == 'append_conversation':
            return self.store.append_conversation(
                _require(arguments, 'session_id'),
                arguments.get('role') or 'user',
                _require(arguments, 'text'),
                arguments.get('summary'),
            )
        raise ValueError(f'unknown tool: {name}')


def _require(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if value is None or str(value).strip() == '':
        raise ValueError(f'{key} is required')
    return str(value)


def _tool_defs() -> list[dict[str, Any]]:
    """MCP tools/list payload."""
    session = {'type': 'string', 'description': 'Chat/session id.'}
    return [
        {
            'name': 'deep_reason',
            'description': (
                'Multi-step decompose/execute/compose. Returns markdown. '
                'If files are enabled, also writes the bound work and lists paths.'
            ),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'prompt': {'type': 'string'},
                    'session_id': session,
                    'chat_context': {'type': 'string'},
                },
                'required': ['prompt'],
            },
        },
        {
            'name': 'reset_session',
            'description': 'Drop in-memory document, work bind, and conversation log.',
            'inputSchema': {
                'type': 'object',
                'properties': {'session_id': session},
                'required': ['session_id'],
            },
        },
        {
            'name': 'bind_work',
            'description': (
                'Attach session_id to universe/series/work. Creates document '
                'directories when file storage is on.'
            ),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'session_id': session,
                    'universe': {'type': 'string'},
                    'series': {'type': 'string'},
                    'work': {'type': 'string'},
                },
                'required': ['session_id', 'universe', 'series', 'work'],
            },
        },
        {
            'name': 'list_documents',
            'description': 'List documents in the bound work or in-memory session.',
            'inputSchema': {
                'type': 'object',
                'properties': {'session_id': session},
                'required': ['session_id'],
            },
        },
        {
            'name': 'read_document',
            'description': 'Read one document/part by id.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'session_id': session,
                    'doc_id': {'type': 'string'},
                },
                'required': ['session_id', 'doc_id'],
            },
        },
        {
            'name': 'search_workspace',
            'description': 'Keyword search over the bound work or in-memory parts.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'session_id': session,
                    'query': {'type': 'string'},
                },
                'required': ['session_id', 'query'],
            },
        },
        {
            'name': 'search_conversation',
            'description': 'Keyword search over summarised/full stored turns.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'session_id': session,
                    'query': {'type': 'string'},
                },
                'required': ['session_id', 'query'],
            },
        },
        {
            'name': 'append_conversation',
            'description': 'Store a user/assistant turn for later search_conversation.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'session_id': session,
                    'role': {'type': 'string'},
                    'text': {'type': 'string'},
                    'summary': {'type': 'string'},
                },
                'required': ['session_id', 'text'],
            },
        },
    ]


def _result(msg_id: Any, result: Any) -> dict[str, Any]:
    return {'jsonrpc': '2.0', 'id': msg_id, 'result': result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        'jsonrpc': '2.0',
        'id': msg_id,
        'error': {'code': code, 'message': message},
    }


def _tool_result(msg_id: Any, text: str, is_error: bool = False) -> dict[str, Any]:
    return _result(
        msg_id,
        {
            'content': [{'type': 'text', 'text': text}],
            'isError': is_error,
        },
    )


def _read_message(buf) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = buf.readline()
        if not line:
            return None
        if line in (b'\r\n', b'\n'):
            break
        decoded = line.decode('utf-8').rstrip('\r\n')
        if ':' not in decoded:
            continue
        key, value = decoded.split(':', 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get('content-length', '0'))
    body = buf.read(length)
    if not body:
        return None
    return json.loads(body.decode('utf-8'))


def _write_message(buf, message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False).encode('utf-8')
    header = f'Content-Length: {len(payload)}\r\n\r\n'.encode('ascii')
    buf.write(header)
    buf.write(payload)
    buf.flush()


def load_runtime(config_path: Path | None = None) -> tuple[NovelStore, Path]:
    """Load YAML and build TaskOrchestrator + NovelStore (NOVEL_MCP_CONFIG or package config.yaml)."""
    env = os.environ.get('NOVEL_MCP_CONFIG')
    if config_path is None:
        if env:
            config_path = Path(env)
        else:
            config_path = Path(__file__).resolve().parent / 'config.yaml'
    config = NovelConfig.load(config_path)
    orch_path = config.orchestrator_path(config_path)
    if not orch_path.is_file():
        raise SystemExit(f'orchestrator yaml not found: {orch_path}')
    orchestrator = TaskOrchestrator.from_yaml(orch_path)
    return NovelStore(orchestrator, config, config_path), config_path


def main() -> None:
    """stdio loop: read Content-Length frames, write JSON-RPC replies."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    store, _ = load_runtime()
    handler = McpHandler(store)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        try:
            incoming = _read_message(stdin)
        except Exception:
            logger.exception('failed to read MCP message')
            break
        if incoming is None:
            break
        reply = handler.handle(incoming)
        if reply is not None:
            _write_message(stdout, reply)


if __name__ == '__main__':
    main()
