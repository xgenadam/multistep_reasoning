"""
stdio MCP server exposing deep_reason.

Run:  python -m reasoning_sub_agents.mcp_server

Logs go to stderr. Stdout is JSON-RPC only.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessage

from .document import Document
from .task_orchestrator import TaskOrchestrator

PROTOCOL_VERSION = '2024-11-05'
SERVER_NAME = 'multistep-reasoning'
SERVER_VERSION = '0.1.0'

logger = logging.getLogger('multistep_reasoning.mcp')


class ReasoningSessionStore:
    def __init__(self, orchestrator: TaskOrchestrator) -> None:
        self.orchestrator = orchestrator
        self._sessions: dict[str, Document] = {}

    def deep_reason(
        self,
        prompt: str,
        session_id: str | None = None,
        chat_context: str | None = None,
    ) -> str:
        document = None
        if session_id:
            document = self._sessions.get(session_id)
            if document is None:
                document = Document.empty(
                    render_mode=self.orchestrator.options.render
                )
                self._sessions[session_id] = document
        response = self.orchestrator.query(
            prompt,
            document=document,
            chat_context=chat_context or None,
        )
        if isinstance(response, tuple):
            message = response[0]
        else:
            message = response
        if isinstance(message, ChatCompletionMessage):
            return message.content or ''
        return str(message)

    def reset_session(self, session_id: str) -> str:
        self._sessions.pop(session_id, None)
        return f'reset {session_id}'


def default_orchestrator() -> TaskOrchestrator:
    yaml_path = os.environ.get('MULTISTEP_ORCHESTRATOR_YAML')
    if yaml_path and Path(yaml_path).is_file():
        return TaskOrchestrator.from_yaml(yaml_path)
    here = Path(__file__).resolve().parent.parent
    candidate = here / 'orchestrator.yaml'
    if candidate.is_file():
        return TaskOrchestrator.from_yaml(candidate)
    raise SystemExit(
        'No orchestrator.yaml found. Set MULTISTEP_ORCHESTRATOR_YAML '
        'or run from the repo root.'
    )


class McpHandler:
    def __init__(self, store: ReasoningSessionStore) -> None:
        self.store = store

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
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
        name = params.get('name')
        arguments = params.get('arguments') or {}
        try:
            if name == 'deep_reason':
                prompt = arguments.get('prompt') or arguments.get('question') or ''
                if not str(prompt).strip():
                    raise ValueError('prompt is required')
                text = self.store.deep_reason(
                    str(prompt),
                    session_id=arguments.get('session_id'),
                    chat_context=arguments.get('chat_context'),
                )
                return _tool_result(msg_id, text)
            if name == 'reset_session':
                session_id = arguments.get('session_id')
                if not session_id:
                    raise ValueError('session_id is required')
                return _tool_result(msg_id, self.store.reset_session(str(session_id)))
            raise ValueError(f'unknown tool: {name}')
        except Exception as exc:
            logger.exception('tool %s failed', name)
            return _tool_result(msg_id, f'Error: {exc}', is_error=True)


def _tool_defs() -> list[dict[str, Any]]:
    return [
        {
            'name': 'deep_reason',
            'description': (
                'Run multi-step decompose/execute/compose on a question and '
                'return a markdown document (plan, analysis, or draft). '
                'Then apply the result with your own file/shell tools. '
                'Do not use this for ordinary short replies.'
            ),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'prompt': {
                        'type': 'string',
                        'description': 'The question or task to reason about.',
                    },
                    'session_id': {
                        'type': 'string',
                        'description': 'Reuse a Document across calls in the same chat.',
                    },
                    'chat_context': {
                        'type': 'string',
                        'description': 'Optional compact prior user/assistant turns.',
                    },
                },
                'required': ['prompt'],
            },
        },
        {
            'name': 'reset_session',
            'description': 'Drop a stored Document for session_id.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'session_id': {'type': 'string'},
                },
                'required': ['session_id'],
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


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    store = ReasoningSessionStore(default_orchestrator())
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
