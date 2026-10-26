"""Logging proxy for an OpenAI-compatible model server (external-harness comparison,
journal/design/lead-worker.md). Standard library only.

    python3 llm_proxy.py --listen 0.0.0.0:9000 --upstream http://host.containers.internal:8090 --log-dir /logs

A client is pointed at http://<proxy>:9000/<label>/v1 . The first path segment is
the label (one per run of an external harness, e.g. b_c13_r0); the rest is
forwarded unchanged. Every request and its reply go to <log-dir>/<label>.jsonl,
one line per call:
  {index, label, path, started, seconds, status, request, response}
For streamed calls the reply is rebuilt from the chunks (content, reasoning,
tool calls, finish reason, usage), and `stream_options.include_usage` is added
to the request so token counts arrive. Anything else is passed through as is.
"""

from __future__ import annotations

import argparse
import http.client
import itertools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

COUNTER = itertools.count()
LOCK = threading.Lock()


def rebuild_stream(lines: list[str]) -> dict:
    """The reply a streamed chat completion adds up to."""
    content, reasoning, finish, usage, model = [], [], None, None, None
    tools: dict[int, dict] = {}
    for line in lines:
        if not line.startswith('data:'):
            continue
        data = line[5:].strip()
        if not data or data == '[DONE]':
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        model = chunk.get('model', model)
        usage = chunk.get('usage') or usage
        for choice in chunk.get('choices') or []:
            delta = choice.get('delta') or {}
            content.append(delta.get('content') or '')
            reasoning.append(delta.get('reasoning_content') or delta.get('reasoning') or '')
            for tc in delta.get('tool_calls') or []:
                slot = tools.setdefault(tc.get('index', 0), {'id': None, 'name': '', 'arguments': ''})
                slot['id'] = tc.get('id') or slot['id']
                fn = tc.get('function') or {}
                slot['name'] += fn.get('name') or ''
                slot['arguments'] += fn.get('arguments') or ''
            finish = choice.get('finish_reason') or finish
    return {'model': model, 'content': ''.join(content), 'reasoning': ''.join(reasoning),
            'tool_calls': [tools[i] for i in sorted(tools)], 'finish_reason': finish, 'usage': usage}


class Handler(BaseHTTPRequestHandler):
    upstream = None
    log_dir = None
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):  # quiet
        pass

    def _split(self):
        parts = self.path.lstrip('/').split('/', 1)
        if len(parts) == 2 and parts[1].startswith('v1'):
            return parts[0], '/' + parts[1]
        return 'unlabelled', self.path

    def _forward(self, method):
        label, path = self._split()
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0)) if method == 'POST' else None
        request = None
        if body:
            try:
                request = json.loads(body)
                if request.get('stream'):
                    request.setdefault('stream_options', {})['include_usage'] = True
                    body = json.dumps(request).encode()
            except json.JSONDecodeError:
                request = None
        up = urlsplit(self.upstream)
        conn = http.client.HTTPConnection(up.hostname, up.port or 80, timeout=7200)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length', 'accept-encoding')}
        if body is not None:
            headers['Content-Length'] = str(len(body))
        index, t0 = next(COUNTER), time.time()
        conn.request(method, (up.path.rstrip('/') + path), body=body, headers=headers)
        resp = conn.getresponse()
        self.send_response(resp.status)
        streamed = 'text/event-stream' in (resp.getheader('Content-Type') or '')
        for k, v in resp.getheaders():
            if k.lower() not in ('transfer-encoding', 'content-length', 'connection'):
                self.send_header(k, v)
        lines: list[str] = []
        if streamed:
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            buf = b''
            while True:
                piece = resp.read1(65536)
                if not piece:
                    break
                buf += piece
                *done, buf = buf.split(b'\n')
                lines += [d.decode('utf-8', 'replace') for d in done]
                self.wfile.write(b'%x\r\n%s\r\n' % (len(piece), piece))
                self.wfile.flush()
            if buf:
                lines.append(buf.decode('utf-8', 'replace'))
            self.wfile.write(b'0\r\n\r\n')
            response = rebuild_stream(lines)
        else:
            data = resp.read()
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            try:
                response = json.loads(data)
            except json.JSONDecodeError:
                response = {'raw': data[:2000].decode('utf-8', 'replace')}
        conn.close()
        if path.endswith('/chat/completions') or request is not None:
            row = {'index': index, 'label': label, 'path': path, 'started': t0, 'seconds': round(time.time() - t0, 3),
                   'status': resp.status, 'stream': streamed, 'request': request, 'response': response}
            with LOCK, open(Path(self.log_dir) / f'{label}.jsonl', 'a') as f:
                f.write(json.dumps(row) + '\n')

    def do_GET(self):
        self._forward('GET')

    def do_POST(self):
        self._forward('POST')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--listen', default='0.0.0.0:9000')
    ap.add_argument('--upstream', required=True)
    ap.add_argument('--log-dir', required=True)
    args = ap.parse_args(argv)
    Path(args.log_dir).mkdir(parents=True, exist_ok=True)
    Handler.upstream, Handler.log_dir = args.upstream, args.log_dir
    host, port = args.listen.rsplit(':', 1)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
