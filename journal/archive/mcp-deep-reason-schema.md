# MCP `deep_reason` tool (archived, O-02)

Phase H reference. From `mcp_server/mcp_server.py` at commit 236d168 before `git rm`: the session store (lines 30-64) and the tool schema (lines 138-178). The server was retired in S-002 and unimportable since 9c4fce5.

## `ReasoningSessionStore`

```python
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
```

## Tool schema

```python
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
```
