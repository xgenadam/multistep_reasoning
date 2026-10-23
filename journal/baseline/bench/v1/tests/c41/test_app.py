import base64

from web import App, BadRequest, Response, Router, basic_auth, cookies, logger, parse_request


def make_router():
    r = Router()
    r.add('GET', '/hello/{name}', lambda req: Response.text(f'hi {req.params["name"]}'))
    r.add('POST', '/echo', lambda req: Response.json(req.json()))
    r.add('GET', '/boom', lambda req: 1 / 0)
    r.add('GET', '/state', lambda req: Response.json(req.state))
    return r


def raw(method, path, headers=(), body=b''):
    head = f'{method} {path} HTTP/1.1\r\nHost: t\r\n'
    head += ''.join(f'{k}: {v}\r\n' for k, v in headers)
    return head.encode('latin-1') + b'\r\n' + body


def test_round_trip_bytes():
    app = App(make_router())
    out = app.handle_bytes(raw('GET', '/hello/b%C3%B6b'))
    assert out == ('HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n'
                   'Content-Length: 7\r\n\r\nhi böb').encode()


def test_chunked_post_echo():
    body = b'3\r\n{"a\r\n5\r\n":[1]\r\n1\r\n}\r\n0\r\n\r\n'
    out = App(make_router()).handle_bytes(raw('POST', '/echo', [('Transfer-Encoding', 'chunked')],
                                              body))
    assert out.endswith(b'\r\n\r\n{"a":[1]}') and out.startswith(b'HTTP/1.1 200 OK\r\n')


def test_middleware_order_first_is_outermost():
    seen = []

    def mw(tag):
        def m(request, call_next):
            seen.append(f'{tag} in')
            resp = call_next(request)
            seen.append(f'{tag} out')
            resp.headers.add('X-Via', tag)
            return resp
        return m

    app = App(make_router(), [mw('a')])
    app.use(mw('b'))
    resp = app.handle(parse_request(raw('GET', '/hello/x')))
    assert seen == ['a in', 'b in', 'b out', 'a out']
    assert resp.headers.get_all('X-Via') == ['b', 'a']


def test_errors_reach_middleware_as_responses():
    lines = []
    app = App(make_router(), [logger(lines)])
    nf = app.handle(parse_request(raw('GET', '/missing')))
    assert (nf.status, nf.body) == (404, b'404 Not Found')
    na = app.handle(parse_request(raw('DELETE', '/hello/x')))
    assert na.status == 405 and na.headers['Allow'] == 'GET, HEAD'
    assert na.body == b'405 Method Not Allowed'
    boom = app.handle(parse_request(raw('GET', '/boom')))
    assert (boom.status, boom.body) == (500, b'500 Internal Server Error')
    bad = app.handle(parse_request(raw('POST', '/echo', [('Content-Length', '3')], b'{{{')))
    assert (bad.status, bad.body) == (400, b'400 Bad Request')
    assert lines == ['GET /missing 404', 'DELETE /hello/x 405', 'GET /boom 500', 'POST /echo 400']


def test_parse_error_skips_middleware():
    lines = []
    out = App(make_router(), [logger(lines)]).handle_bytes(b'BROKEN\r\n\r\n')
    assert out == (b'HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain; charset=utf-8\r\n'
                   b'Content-Length: 15\r\n\r\n400 Bad Request')
    assert lines == []


def test_exception_in_middleware_becomes_500():
    def bad(request, call_next):
        raise RuntimeError('nope')

    def http_bad(request, call_next):
        raise BadRequest('no')

    assert App(make_router(), [bad]).handle(parse_request(raw('GET', '/hello/x'))).status == 500
    assert App(make_router(), [http_bad]).handle(parse_request(raw('GET', '/x'))).status == 400


def test_cookies_middleware():
    app = App(make_router(), [cookies()])
    resp = app.handle(parse_request(raw('GET', '/state', [
        ('Cookie', 'Session="abc=1"; theme=dark ; junk; theme=light;Empty=')])))
    assert resp.body == b'{"cookies":{"Empty":"","Session":"abc=1","theme":"dark"}}'
    none = app.handle(parse_request(raw('GET', '/state')))
    assert none.body == b'{"cookies":{}}'


def auth(user, pw):
    return 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode()


def test_basic_auth():
    reached = []
    r = make_router()
    r.add('GET', '/secret', lambda req: reached.append(1) or Response.json(req.state))
    app = App(r, [basic_auth({'ann': 'p:ss', 'bob': 'x'}, realm='staff')])
    ok = app.handle(parse_request(raw('GET', '/secret', [('Authorization', auth('ann', 'p:ss'))])))
    assert ok.status == 200 and ok.body == b'{"user":"ann"}'
    for headers in ([], [('Authorization', auth('ann', 'wrong'))],
                    [('Authorization', auth('eve', 'x'))],
                    [('Authorization', 'Bearer abc')], [('Authorization', 'Basic !!!')]):
        resp = app.handle(parse_request(raw('GET', '/secret', headers)))
        assert resp.status == 401 and resp.body == b'401 Unauthorized'
        assert resp.headers['WWW-Authenticate'] == 'Basic realm="staff"'
    assert reached == [1]
