"""HTTP messages: headers, requests, responses and the request parser."""
import json
import re
from dataclasses import dataclass, field

REASONS = {
    200: 'OK', 201: 'Created', 204: 'No Content', 400: 'Bad Request', 401: 'Unauthorized',
    404: 'Not Found', 405: 'Method Not Allowed', 500: 'Internal Server Error',
}


def reason_for(status: int) -> str:
    return REASONS.get(status, 'Unknown')


class HTTPError(Exception):
    status = 500

    def __init__(self, message: str | None = None):
        self.reason = reason_for(self.status)
        super().__init__(message or f'{self.status} {self.reason}')


class BadRequest(HTTPError):
    status = 400


# ---------------------------------------------------------------- shared helpers

_HEX = set('0123456789abcdefABCDEF')


def percent_decode(text: str, plus_is_space: bool) -> str:
    """Decode %XX escapes (and '+' when asked) as UTF-8; BadRequest when malformed."""
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '%':
            pair = text[i + 1:i + 3]
            if len(pair) != 2 or not set(pair) <= _HEX:
                raise BadRequest(f'bad percent-escape in {text!r}')
            out.append(int(pair, 16))
            i += 3
            continue
        if ch == '+' and plus_is_space:
            out.append(0x20)
        else:
            out.extend(ch.encode('utf-8'))
        i += 1
    try:
        return out.decode('utf-8')
    except UnicodeDecodeError:
        raise BadRequest(f'not UTF-8: {text!r}') from None


def parse_params(pieces, lower_names: bool) -> dict[str, str]:
    """`name=value` pieces as a dict: stripped, quotes removed, first name wins."""
    params: dict[str, str] = {}
    for piece in pieces:
        piece = piece.strip()
        if '=' not in piece:
            continue
        name, value = piece.split('=', 1)
        name, value = name.strip(), value.strip()
        if lower_names:
            name = name.lower()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        params.setdefault(name, value)
    return params


# ---------------------------------------------------------------- headers

class Headers:
    def __init__(self, pairs=()):
        self._items: list[tuple[str, str]] = []
        for name, value in pairs:
            self.add(name, value)

    def add(self, name: str, value: str) -> None:
        self._items.append((name, value))

    def set(self, name: str, value: str) -> None:
        key = name.lower()
        out, placed = [], False
        for n, v in self._items:
            if n.lower() == key:
                if not placed:
                    out.append((name, value))
                    placed = True
            else:
                out.append((n, v))
        if not placed:
            out.append((name, value))
        self._items = out

    def get(self, name: str, default=None):
        key = name.lower()
        for n, v in self._items:
            if n.lower() == key:
                return v
        return default

    def __getitem__(self, name: str) -> str:
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value

    def get_all(self, name: str) -> list[str]:
        key = name.lower()
        return [v for n, v in self._items if n.lower() == key]

    def __contains__(self, name) -> bool:
        return self.get(name) is not None

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> list[tuple[str, str]]:
        return list(self._items)

    def remove(self, name: str) -> None:
        key = name.lower()
        self._items = [(n, v) for n, v in self._items if n.lower() != key]

    def __repr__(self) -> str:
        return f'Headers({self._items!r})'


# ---------------------------------------------------------------- messages

@dataclass
class Request:
    method: str
    target: str
    path: str
    query_string: str
    version: str
    headers: Headers
    body: bytes
    params: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)

    @property
    def query(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for piece in self.query_string.split('&'):
            if not piece:
                continue
            name, _, value = piece.partition('=')
            result.setdefault(percent_decode(name, True), []).append(percent_decode(value, True))
        return result

    @property
    def content_type(self) -> tuple[str, dict[str, str]]:
        raw = self.headers.get('Content-Type')
        if raw is None:
            return '', {}
        pieces = raw.split(';')
        return pieces[0].strip().lower(), parse_params(pieces[1:], lower_names=True)

    def text(self) -> str:
        charset = self.content_type[1].get('charset', 'utf-8')
        return self.body.decode(charset)

    def json(self):
        try:
            return json.loads(self.text())
        except ValueError as e:
            raise BadRequest(f'invalid JSON: {e}') from None


@dataclass
class Response:
    status: int = 200
    headers: Headers = field(default_factory=Headers)
    body: bytes = b''

    def __post_init__(self):
        if self.headers is None:
            self.headers = Headers()

    @classmethod
    def text(cls, s: str, status: int = 200) -> 'Response':
        return cls(status, Headers([('Content-Type', 'text/plain; charset=utf-8')]),
                   s.encode('utf-8'))

    @classmethod
    def json(cls, obj, status: int = 200) -> 'Response':
        body = json.dumps(obj, separators=(',', ':'), sort_keys=True).encode('utf-8')
        return cls(status, Headers([('Content-Type', 'application/json')]), body)

    def to_bytes(self) -> bytes:
        lines = [f'HTTP/1.1 {self.status} {reason_for(self.status)}']
        for name, value in self.headers.items():
            if name.lower() != 'content-length':
                lines.append(f'{name}: {value}')
        lines.append(f'Content-Length: {len(self.body)}')
        head = '\r\n'.join(lines) + '\r\n\r\n'
        return head.encode('latin-1') + self.body


# ---------------------------------------------------------------- parsing

_METHOD = re.compile(r'[A-Z]+')
_TOKEN = re.compile(r"[A-Za-z0-9!#$%&'*+\-.^_`|~]+")
_HEXSIZE = re.compile(r'[0-9A-Fa-f]+')


def _parse_chunked(data: bytes) -> bytes:
    body = bytearray()
    pos = 0
    while True:
        end = data.find(b'\r\n', pos)
        if end < 0:
            raise BadRequest('unterminated chunk size')
        size_text = data[pos:end].strip().decode('latin-1')
        if not _HEXSIZE.fullmatch(size_text):
            raise BadRequest(f'bad chunk size {size_text!r}')
        size = int(size_text, 16)
        pos = end + 2
        if size == 0:
            break
        chunk = data[pos:pos + size]
        if len(chunk) != size or data[pos + size:pos + size + 2] != b'\r\n':
            raise BadRequest('truncated chunk')
        body += chunk
        pos += size + 2
    while True:  # trailers, up to an empty line
        end = data.find(b'\r\n', pos)
        if end < 0:
            raise BadRequest('unterminated trailers')
        line = data[pos:end]
        pos = end + 2
        if not line:
            break
    if pos != len(data):
        raise BadRequest('bytes after the chunked body')
    return bytes(body)


def parse_request(data: bytes) -> Request:
    split = data.find(b'\r\n\r\n')
    if split < 0:
        raise BadRequest('no end of head')
    lines = data[:split].decode('latin-1').split('\r\n')
    rest = data[split + 4:]
    parts = lines[0].split(' ')
    if len(parts) != 3:
        raise BadRequest('bad request line')
    method, target, version = parts
    if not _METHOD.fullmatch(method) or not target.startswith('/') \
            or version not in ('HTTP/1.1', 'HTTP/1.0'):
        raise BadRequest('bad request line')
    headers = Headers()
    for line in lines[1:]:
        if line[:1] in (' ', '\t'):
            raise BadRequest('obsolete line folding')
        name, sep, value = line.partition(':')
        if not sep or not _TOKEN.fullmatch(name):
            raise BadRequest(f'bad header line {line!r}')
        headers.add(name, value.strip(' \t'))
    if version == 'HTTP/1.1' and 'Host' not in headers:
        raise BadRequest('missing Host')
    te = headers.get_all('Transfer-Encoding')
    lengths = headers.get_all('Content-Length')
    if te:
        if lengths or len(te) != 1 or te[0].lower() != 'chunked':
            raise BadRequest('unsupported transfer encoding')
        body = _parse_chunked(rest)
    elif lengths:
        if any(not v.isascii() or not v.isdigit() for v in lengths) or len(set(lengths)) != 1:
            raise BadRequest('bad Content-Length')
        n = int(lengths[0])
        if len(rest) < n:
            raise BadRequest('body shorter than Content-Length')
        if len(rest) > n:
            raise BadRequest('bytes after the body')
        body = rest
    else:
        if rest:
            raise BadRequest('bytes after the head')
        body = b''
    path, _, query_string = target.partition('?')
    return Request(method, target, path, query_string, version, headers, body)
