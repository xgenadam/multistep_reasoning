"""Path patterns, method dispatch, 404 and 405."""
import re

from .request import HTTPError, Request, Response, percent_decode


class NotFound(HTTPError):
    status = 404


class MethodNotAllowed(HTTPError):
    status = 405

    def __init__(self, allowed, message: str | None = None):
        self.allowed = sorted(allowed)
        super().__init__(message)


_PARAM = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)(?::([a-z]+))?\}')
_CONVERTERS = ('str', 'int', 'path')


class _Pattern:
    def __init__(self, text: str):
        if not text.startswith('/'):
            raise ValueError(f'pattern must start with /: {text!r}')
        self.text = text
        raw = text[1:].split('/') if text != '/' else ['']
        self.segments: list[tuple[str, str]] = []  # (kind, literal-or-name)
        names = set()
        for i, seg in enumerate(raw):
            m = _PARAM.fullmatch(seg)
            if not m:
                self.segments.append(('lit', seg))
                continue
            name, conv = m.group(1), m.group(2) or 'str'
            if conv not in _CONVERTERS:
                raise ValueError(f'unknown converter {conv!r}')
            if name in names:
                raise ValueError(f'duplicate parameter {name!r}')
            if conv == 'path' and i != len(raw) - 1:
                raise ValueError('a path parameter must be last')
            names.add(name)
            self.segments.append((conv, name))

    def match(self, segments: list[str]) -> dict | None:
        params: dict = {}
        for i, (kind, value) in enumerate(self.segments):
            if kind == 'path':
                rest = segments[i:]
                if not rest or any(s == '' for s in rest):
                    return None
                params[value] = '/'.join(rest)
                return params
            if i >= len(segments):
                return None
            seg = segments[i]
            if kind == 'lit':
                if seg != value:
                    return None
            elif seg == '':
                return None
            elif kind == 'int':
                if not (seg.isascii() and seg.isdigit()):
                    return None
                params[value] = int(seg)
            else:
                params[value] = seg
        if len(segments) != len(self.segments):
            return None
        return params


def split_path(path: str) -> list[str]:
    """The decoded segments of a request path (an encoded '/' stays inside its segment)."""
    return [percent_decode(seg, True) for seg in path[1:].split('/')]


class Router:
    def __init__(self):
        self._routes: list[tuple[str, _Pattern, object]] = []

    def add(self, method: str, pattern: str, handler) -> None:
        if any(m == method and p.text == pattern for m, p, _ in self._routes):
            raise ValueError(f'{method} {pattern} is already registered')
        self._routes.append((method, _Pattern(pattern), handler))

    def route(self, pattern: str, methods=('GET',)):
        def decorator(func):
            for method in methods:
                self.add(method, pattern, func)
            return func
        return decorator

    def resolve(self, method: str, path: str):
        segments = split_path(path)
        allowed = set()
        get_match = None
        for m, pattern, handler in self._routes:
            params = pattern.match(segments)
            if params is None:
                continue
            if m == method:
                return handler, params
            allowed.add(m)
            if m == 'GET':
                allowed.add('HEAD')
                if get_match is None:
                    get_match = (handler, params)
        if method == 'HEAD' and get_match is not None:
            return get_match
        if not allowed:
            raise NotFound()
        raise MethodNotAllowed(allowed)

    def _has_handler(self, method: str, path: str) -> bool:
        segments = split_path(path)
        return any(m == method and p.match(segments) is not None for m, p, _ in self._routes)

    def dispatch(self, request: Request) -> Response:
        handler, params = self.resolve(request.method, request.path)
        request.params = params
        response = handler(request)
        if request.method == 'HEAD' and not self._has_handler('HEAD', request.path):
            response.body = b''
        return response
