from collections import deque
from collections.abc import Iterable


# Minimal mock objects that mimic the structure used in most codebases
class MockDelta:
    def __init__(self, content: str | None = None, tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls or []


class MockMessage:
    def __init__(self, content: str, role: str = 'assistant'):
        self.content = content
        self.role = role


class MockChoice:
    def __init__(
        self,
        message: MockMessage | None = None,
        delta: MockDelta | None = None,
        finish_reason: str | None = None,
    ):
        self.message = message
        self.delta = delta
        self.finish_reason = finish_reason


class MockChatCompletion:
    def __init__(self, choices: list[MockChoice]):
        self.choices = choices
        # Optional: add common attributes if your code accesses them
        # self.model = "gpt-4o-mock"
        # self.id = "mock-id"
        # self.created = 0


class MockChatCompletionChunk:
    def __init__(self, choices: list[MockChoice]):
        self.choices = choices


class MockCompletions:
    def __init__(self, mock_client):
        self._mock_client = mock_client

    def create(
        self, **kwargs
    ) -> MockChatCompletion | Iterable[MockChatCompletionChunk]:
        stream = kwargs.get('stream', False)

        if not self._mock_client._responses:
            raise RuntimeError(
                'No more mock responses available. Did you forget to call set_return_values?'
            )

        response_data = self._mock_client._responses.popleft()

        if isinstance(response_data, Exception):
            raise response_data

        if stream:
            return self._create_streaming(response_data)
        else:
            return self._create_non_streaming(response_data)

    def _create_streaming(self, response_data):
        # Handle different ways to specify streaming data
        if isinstance(response_data, str):
            # Auto-split a full string into rough token-like chunks (10 chars each)
            chunk_size = 10
            chunks = [
                response_data[i : i + chunk_size]
                for i in range(0, len(response_data), chunk_size)
            ]
            for i, text in enumerate(chunks):
                finish = 'stop' if i == len(chunks) - 1 else None
                yield MockChatCompletionChunk(
                    choices=[
                        MockChoice(delta=MockDelta(content=text), finish_reason=finish)
                    ]
                )
        elif isinstance(response_data, list | tuple):
            # Check if this is a list of strings or a list of MockChatCompletionChunk objects
            if len(response_data) > 0 and isinstance(response_data[0], str):
                # List of strings → each string is one chunk's content
                for i, text in enumerate(response_data):
                    finish = 'stop' if i == len(response_data) - 1 else None
                    yield MockChatCompletionChunk(
                        choices=[
                            MockChoice(
                                delta=MockDelta(content=text), finish_reason=finish
                            )
                        ]
                    )
            else:
                # List of MockChatCompletionChunk objects
                for chunk in response_data:
                    yield chunk
        else:
            # Assume user provided an iterable of pre-built MockChatCompletionChunk objects
            for chunk in response_data:
                yield chunk

    def _create_non_streaming(self, response_data):
        # Non-streaming case
        if isinstance(response_data, str):
            return MockChatCompletion(
                choices=[
                    MockChoice(
                        message=MockMessage(content=response_data), finish_reason='stop'
                    )
                ]
            )
        else:
            # Assume user provided a pre-built MockChatCompletion object
            return response_data


class MockChat:
    def __init__(self, mock_client):
        self.completions = MockCompletions(mock_client)


class MockOpenAI:
    """
    A simple injectable mock for the official OpenAI client.
    Only implements client.chat.completions.create() – sufficient for most chat-based tests.

    Usage in tests:
        mock_client = MockOpenAI()
        mock_client.set_return_values("Hello, world!")  # non-streaming
        # or
        mock_client.set_return_values(["Hello, ", "world!"])  # streaming chunks

        # Inject into code under test
        result = mock_client.chat.completions.create(messages=[...], stream=True)
    """

    def __init__(self):
        self._responses = deque()
        self.chat = MockChat(self)

    def set_return_values(
        self,
        *values: str
        | list[str]
        | MockChatCompletion
        | Iterable[MockChatCompletionChunk]
        | Exception,
    ):
        """
        Set the responses for successive calls to create().

        Each value can be:
        - str: full assistant message content (auto-split for streaming)
        - list[str]: individual chunk contents for streaming
        - MockChatCompletion: custom non-streaming response
        - iterable of MockChatCompletionChunk: custom streaming response
        - Exception: will be raised on that call

        Examples:
            mock.set_return_values("Full response")  # non-streaming
            mock.set_return_values(["chunk1", "chunk2"])  # streaming
            mock.set_return_values(ValueError("API error"))  # raise error
        """
        self._responses.extend(values)
