"""The application: middleware chain, error responses and built-in middleware."""
import base64
import binascii

from .request import HTTPError, BadRequest, Response, parse_params, parse_request
from .router import MethodNotAllowed


def error_response(exc: Exception) -> Response:
    if isinstance(exc, HTTPError):
        resp = Response.text(f'{exc.status} {exc.reason}', status=exc.status)
        if isinstance(exc, MethodNotAllowed):
            resp.headers.add('Allow', ', '.join(exc.allowed))
        return resp
    return Response.text('500 Internal Server Error', status=500)


class App:
    def __init__(self, router, middleware=()):
        self.router = router
        self.middleware = list(middleware)

    def use(self, mw) -> None:
        self.middleware.append(mw)

    def _innermost(self, request) -> Response:
        try:
            return self.router.dispatch(request)
        except Exception as exc:  # every error becomes a response here
            return error_response(exc)

    def handle(self, request) -> Response:
        call = self._innermost
        for mw in reversed(self.middleware):
            call = (lambda m, nxt: (lambda req: m(req, nxt)))(mw, call)
        try:
            return call(request)
        except Exception as exc:
            return error_response(exc)

    def handle_bytes(self, data: bytes) -> bytes:
        try:
            request = parse_request(data)
        except BadRequest as exc:
            return error_response(exc).to_bytes()
        return self.handle(request).to_bytes()


def logger(lines: list):
    def mw(request, call_next):
        response = call_next(request)
        lines.append(f'{request.method} {request.path} {response.status}')
        return response
    return mw


def cookies():
    def mw(request, call_next):
        raw = request.headers.get('Cookie')
        request.state['cookies'] = {} if raw is None else parse_params(raw.split(';'),
                                                                       lower_names=False)
        return call_next(request)
    return mw


def basic_auth(users: dict[str, str], realm: str = 'app'):
    def deny() -> Response:
        resp = Response.text('401 Unauthorized', status=401)
        resp.headers.add('WWW-Authenticate', f'Basic realm="{realm}"')
        return resp

    def mw(request, call_next):
        raw = request.headers.get('Authorization', '')
        if not raw.startswith('Basic '):
            return deny()
        try:
            decoded = base64.b64decode(raw[6:].strip(), validate=True).decode('utf-8')
        except (binascii.Error, UnicodeDecodeError):
            return deny()
        user, sep, password = decoded.partition(':')
        if not sep or users.get(user) != password:
            return deny()
        request.state['user'] = user
        return call_next(request)
    return mw
