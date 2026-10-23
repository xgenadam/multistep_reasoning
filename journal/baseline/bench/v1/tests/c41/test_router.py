import pytest

from web import BadRequest, MethodNotAllowed, NotFound, Response, Router, parse_request


def get(path, method='GET'):
    return parse_request(f'{method} {path} HTTP/1.0\r\n\r\n'.encode())


def echo(tag):
    return lambda request: Response.json({'tag': tag, 'params': request.params})


def test_literals_params_and_int():
    r = Router()
    r.add('GET', '/', echo('root'))
    r.add('GET', '/users/{uid:int}/posts/{slug}', echo('post'))
    h, params = r.resolve('GET', '/users/42/posts/hello')
    assert params == {'uid': 42, 'slug': 'hello'} and isinstance(params['uid'], int)
    assert r.resolve('GET', '/')[1] == {}
    resp = r.dispatch(get('/users/7/posts/x'))
    assert resp.body == b'{"params":{"slug":"x","uid":7},"tag":"post"}'


def test_non_matching_paths_are_404():
    r = Router()
    r.add('GET', '/users/{uid:int}/posts/{slug}', echo('post'))
    for path in ['/users/4a/posts/x', '/users/-1/posts/x', '/users/%C2%B2/posts/x',
                 '/users/1/posts', '/users/1/posts/x/y', '/users//posts/x', '/users/1/posts/']:
        with pytest.raises(NotFound) as exc:
            r.resolve('GET', path)
        assert exc.value.status == 404 and exc.value.reason == 'Not Found', path


def test_path_converter_and_decoding():
    r = Router()
    r.add('GET', '/files/{rest:path}', echo('f'))
    r.add('GET', '/café/{name}', echo('c'))
    assert r.resolve('GET', '/files/a/b%20c/d.txt')[1] == {'rest': 'a/b c/d.txt'}
    with pytest.raises(NotFound):
        r.resolve('GET', '/files')
    with pytest.raises(NotFound):
        r.resolve('GET', '/files/')
    assert r.resolve('GET', '/caf%C3%A9/a%2Fb')[1] == {'name': 'a/b'}  # %2F stays inside
    assert r.resolve('GET', '/caf%C3%A9/a+b')[1] == {'name': 'a+b'}    # + is not a space
    with pytest.raises(BadRequest):
        r.resolve('GET', '/caf%C3%A9/%zz')


def test_trailing_slash_matters():
    r = Router()
    r.add('GET', '/users', echo('list'))
    r.add('GET', '/teams/', echo('teams'))
    with pytest.raises(NotFound):
        r.resolve('GET', '/users/')
    with pytest.raises(NotFound):
        r.resolve('GET', '/teams')
    assert r.resolve('GET', '/teams/')[1] == {}


def test_first_registered_wins():
    r = Router()
    r.add('GET', '/a/{x}', echo('param'))
    r.add('GET', '/a/b', echo('literal'))
    assert r.dispatch(get('/a/b')).body == b'{"params":{"x":"b"},"tag":"param"}'


def test_405_lists_allowed_methods_with_head():
    r = Router()
    r.add('POST', '/items/{id}', echo('p'))
    r.add('GET', '/items/{name}', echo('g'))
    r.add('DELETE', '/other', echo('d'))
    with pytest.raises(MethodNotAllowed) as exc:
        r.resolve('PUT', '/items/3')
    assert exc.value.allowed == ['GET', 'HEAD', 'POST']
    assert exc.value.status == 405 and exc.value.reason == 'Method Not Allowed'
    with pytest.raises(NotFound):
        r.resolve('PUT', '/nothing')


def test_head_uses_get_and_drops_body():
    r = Router()

    @r.route('/page', methods=('GET', 'POST'))
    def page(request):
        resp = Response.text('hello')
        resp.headers.add('X-Seen', request.method)
        return resp

    assert page.__name__ == 'page'
    resp = r.dispatch(get('/page', 'HEAD'))
    assert resp.body == b'' and resp.headers['X-Seen'] == 'HEAD'
    assert resp.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert r.dispatch(get('/page', 'POST')).body == b'hello'
    r.add('HEAD', '/own', lambda req: Response.text('kept'))
    assert r.dispatch(get('/own', 'HEAD')).body == b'kept'


@pytest.mark.parametrize('pattern', ['users', '/a/{x}/{x}', '/a/{x:float}', '/a/{p:path}/b'])
def test_bad_patterns(pattern):
    with pytest.raises(ValueError):
        Router().add('GET', pattern, echo('x'))


def test_duplicate_route_rejected_but_other_method_ok():
    r = Router()
    r.add('GET', '/x', echo('a'))
    r.add('POST', '/x', echo('b'))
    with pytest.raises(ValueError):
        r.add('GET', '/x', echo('c'))
