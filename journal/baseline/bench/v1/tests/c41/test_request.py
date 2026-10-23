import pytest

from web import BadRequest, Headers, HTTPError, Request, Response, parse_request


def req(head: str, body: bytes = b'') -> Request:
    return parse_request(head.encode('latin-1') + b'\r\n\r\n' + body)


def test_headers_case_insensitive_multimap():
    h = Headers([('Content-Type', 'text/plain'), ('X-Tag', 'a')])
    h.add('x-tag', 'b')
    assert h.get('content-type') == 'text/plain' and h['CONTENT-TYPE'] == 'text/plain'
    assert h.get_all('X-TAG') == ['a', 'b'] and h.get_all('nope') == []
    assert 'x-Tag' in h and 'nope' not in h and h.get('nope', 7) == 7
    assert len(h) == 3
    assert h.items() == [('Content-Type', 'text/plain'), ('X-Tag', 'a'), ('x-tag', 'b')]
    with pytest.raises(KeyError):
        h['nope']
    h.set('X-TAG', 'c')
    h.set('New', 'n')
    assert h.items() == [('Content-Type', 'text/plain'), ('X-TAG', 'c'), ('New', 'n')]


def test_parse_simple_get():
    r = req('GET /a/b%20c?x=1 HTTP/1.1\r\nHost: example.test\r\nAccept:  */*\t')
    assert (r.method, r.target, r.path, r.query_string, r.version) == \
        ('GET', '/a/b%20c?x=1', '/a/b%20c', 'x=1', 'HTTP/1.1')
    assert r.headers.items() == [('Host', 'example.test'), ('Accept', '*/*')]
    assert r.body == b'' and r.params == {} and r.state == {}


def test_query_decoding():
    r = req('GET /?a=1&b=x+y&a=%E2%82%AC&flag&&c=&k=p=q&sp%61ce=%2B HTTP/1.0')
    assert r.query == {'a': ['1', '€'], 'b': ['x y'], 'flag': [''], 'c': [''],
                       'k': ['p=q'], 'space': ['+']}
    assert req('GET /p HTTP/1.0').query == {}


@pytest.mark.parametrize('qs', ['a=%', 'a=%4', 'b%zz=1', 'a=%FF'])
def test_query_bad_escape_raises(qs):
    with pytest.raises(BadRequest):
        req(f'GET /?{qs} HTTP/1.0').query


def test_content_type_text_and_json():
    r = req('POST /x HTTP/1.0\r\nContent-Type: Text/Plain ; Charset="latin-1"; q; charset=utf-8'
            '\r\nContent-Length: 3', 'é!x'.encode('latin-1'))
    assert r.content_type == ('text/plain', {'charset': 'latin-1'})
    assert r.text() == 'é!x'
    assert req('GET / HTTP/1.0').content_type == ('', {})
    j = req('POST /x HTTP/1.0\r\nContent-Length: 13', b'{"a": [1, 2]}')
    assert j.json() == {'a': [1, 2]}
    bad = req('POST /x HTTP/1.0\r\nContent-Length: 4', b'{"a"')
    with pytest.raises(BadRequest):
        bad.json()


def test_content_length_body_and_repeated_equal_lengths():
    r = req('POST /x HTTP/1.1\r\nHost: h\r\nContent-Length: 5\r\ncontent-length: 5', b'he\r\nl')
    assert r.body == b'he\r\nl'


def test_chunked_body_with_extension_and_trailers():
    body = b'4\r\nWiki\r\n6;name=v\r\npedia \r\nE\r\nin \r\n\r\nchunks.\r\n0\r\nX-Trailer: t\r\n\r\n'
    r = req('POST /x HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: Chunked', body)
    assert r.body == b'Wikipedia in \r\n\r\nchunks.'
    empty = req('POST /x HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked', b'0\r\n\r\n')
    assert empty.body == b''


def test_http10_needs_no_host():
    assert req('GET / HTTP/1.0').version == 'HTTP/1.0'


BAD = {
    'request-line': [
        b'GET / HTTP/1.1\r\nHost: h\r\n',                                # no blank line
        b'get / HTTP/1.1\r\nHost: h\r\n\r\n',                            # lower-case method
        b'GET  / HTTP/1.1\r\nHost: h\r\n\r\n',                           # two spaces
        b'GET x HTTP/1.1\r\nHost: h\r\n\r\n',                            # target without /
        b'GET / HTTP/2.0\r\nHost: h\r\n\r\n',                            # version
    ],
    'header-lines': [
        b'GET / HTTP/1.1\r\nAccept: x\r\n\r\n',                          # no Host
        b'GET / HTTP/1.1\r\nHost: h\r\n folded\r\n\r\n',                 # obsolete folding
        b'GET / HTTP/1.1\r\nHost : h\r\n\r\n',                           # space before colon
        b'GET / HTTP/1.1\r\nHost: h\r\nNo-Colon\r\n\r\n',
    ],
    'transfer-encoding': [
        b'POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: gzip\r\n\r\n',
        b'POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\nContent-Length: 1'
        b'\r\n\r\n0\r\n\r\n',
    ],
    'chunks': [
        b'POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\nZ\r\nabc\r\n0\r\n\r\n',
        b'POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nabc\r\n0\r\n\r\n',
        b'POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nextra',
    ],
    'content-length': [
        b'POST / HTTP/1.1\r\nHost: h\r\nContent-Length: +3\r\n\r\nabc',
        b'POST / HTTP/1.1\r\nHost: h\r\nContent-Length: 3\r\nContent-Length: 4\r\n\r\nabcd',
        b'POST / HTTP/1.1\r\nHost: h\r\nContent-Length: 5\r\n\r\nabc',   # short body
        b'POST / HTTP/1.1\r\nHost: h\r\nContent-Length: 2\r\n\r\nabc',   # bytes left over
        b'GET / HTTP/1.1\r\nHost: h\r\n\r\nleftover',
    ],
}


@pytest.mark.parametrize('group', sorted(BAD))
def test_bad_requests(group):
    for raw in BAD[group]:
        with pytest.raises(BadRequest) as exc:
            parse_request(raw)
        assert exc.value.status == 400 and exc.value.reason == 'Bad Request', raw
        assert isinstance(exc.value, HTTPError)


def test_response_to_bytes():
    r = Response(201, Headers([('X-A', '1'), ('content-length', '99'), ('X-B', '2')]), b'hi')
    assert r.to_bytes() == (b'HTTP/1.1 201 Created\r\nX-A: 1\r\nX-B: 2\r\n'
                            b'Content-Length: 2\r\n\r\nhi')
    assert Response(299).to_bytes() == b'HTTP/1.1 299 Unknown\r\nContent-Length: 0\r\n\r\n'
    assert len(Response().headers) == 0


def test_response_text_and_json():
    t = Response.text('héllo', status=404)
    assert (t.status, t.body) == (404, 'héllo'.encode())
    assert t.headers.items() == [('Content-Type', 'text/plain; charset=utf-8')]
    j = Response.json({'b': 1, 'a': [1, 'é']})
    assert j.status == 200 and j.body == b'{"a":[1,"\\u00e9"],"b":1}'
    assert j.headers['content-type'] == 'application/json'
