"""OpenAI-shaped client backed by a local generate() callable."""

from collections.abc import Callable, Iterator
from typing import Any

GenerateFn = Callable[..., Any]


class _Delta:
    def __init__(self, content: str | None = None) -> None:
        self.content = content
        self.tool_calls = []


class _Message:
    def __init__(self, content: str, role: str = 'assistant') -> None:
        self.content = content
        self.role = role


class _Choice:
    def __init__(
        self,
        message: _Message | None = None,
        delta: _Delta | None = None,
        finish_reason: str | None = None,
    ) -> None:
        self.message = message
        self.delta = delta
        self.finish_reason = finish_reason


class _ChatCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(message=_Message(content), finish_reason='stop')]


class _ChatCompletionChunk:
    def __init__(self, content: str | None, finish_reason: str | None = None) -> None:
        self.choices = [_Choice(delta=_Delta(content), finish_reason=finish_reason)]


class _Completions:
    def __init__(self, client: 'LocalGenerateClient') -> None:
        self._client = client

    def create(self, **kwargs: Any) -> _ChatCompletion | Iterator[_ChatCompletionChunk]:
        messages = kwargs.get('messages') or []
        stream = bool(kwargs.get('stream', False))
        prompt = messages_to_prompt(messages)
        if stream:
            return self._stream(prompt)
        text = self._client.generate(prompt, stream=False)
        if not isinstance(text, str):
            text = ''.join(str(part) for part in text)
        return _ChatCompletion(text)

    def _stream(self, prompt: str) -> Iterator[_ChatCompletionChunk]:
        produced = False
        for delta in self._client.generate(prompt, stream=True):
            if not delta:
                continue
            produced = True
            yield _ChatCompletionChunk(str(delta))
        yield _ChatCompletionChunk(None, finish_reason='stop' if produced else 'stop')


class _Chat:
    def __init__(self, client: 'LocalGenerateClient') -> None:
        self.completions = _Completions(client)


class LocalGenerateClient:
    """
    Duck-typed OpenAI client.

    `generate(prompt, *, stream=False)` must return a string when stream is
    false, or yield text deltas when stream is true.
    """

    def __init__(self, generate: GenerateFn) -> None:
        self.generate = generate
        self.chat = _Chat(self)
        self.api_key = 'sk-no-key-needed'
        self.base_url = 'http://oobabooga.local/v1'


def messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.get('role', 'user')
        content = message.get('content') or ''
        lines.append(f'{role}: {content}')
    lines.append('assistant:')
    return '\n'.join(lines)
