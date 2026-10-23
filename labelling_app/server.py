#!/usr/bin/env python3
"""Labelling app (Q-06, criterion Q-11): the user labels pairs side by side.

Runs on the host or in the agent container with the standard library plus
PyYAML. It reads a pairs manifest (journal/baseline/bench/validation/pairs.yaml
by default), shows each unlabelled pair's task and both candidates in a
per-pair random display order, and writes the user's label to `labels.yaml`
beside the manifest. `quality.py` reads that file as the pairs' `expected`.

Blinding: the page never receives a pair's source, run ids or kind, and this
module never reads judge verdict files. The optional assistant answers factual
questions about the pair and is told never to say which candidate is better.
Its endpoint is explicit (D-008): --assist-base-url / $ASSIST_BASE_URL and
--assist-model / $ASSIST_MODEL; without them the assistant is off.

    python3 labelling_app/server.py [--pairs PATH] [--host 127.0.0.1] [--port 8766]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DEFAULT_PAIRS = ROOT.parent / 'journal' / 'baseline' / 'bench' / 'validation' / 'pairs.yaml'
LABELS_NAME = 'labels.yaml'
CHOICES = {'left', 'right', 'tie'}
ASSIST_MAX_TOKENS = 1024
ASSIST_TIMEOUT_S = 300

ASSIST_SYSTEM = """\
You help a human who is labelling two responses to the same task. The human \
decides which response is better; you never do.

You may: explain what code or text in either response does, check whether a \
specific requirement of the task is addressed and where, point to the lines \
involved, explain terms, and answer factual questions about the task.

You must not: say or hint which response is better, rank or score them, \
predict the human's label, or summarise them as a comparison of quality. If \
asked for any of that, say you can't help with that part and offer a factual \
check instead.

Refer to the responses only as Left and Right. Be brief and concrete."""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def display_order(pair_id: str, salt: str) -> dict:
    """Which canonical side is shown on the left; stable per pair and salt."""
    digest = hashlib.sha256(f'{salt}:{pair_id}'.encode()).digest()
    return {'left': 'a', 'right': 'b'} if digest[0] % 2 == 0 else {'left': 'b', 'right': 'a'}


def strip_thinking(text: str) -> str:
    return re.sub(r'<think>.*?</think>', '', text or '', flags=re.S).strip()


class Store:
    """The manifest's pairs plus the labels file; every write is atomic."""

    def __init__(self, pairs_path: Path, labels_path: Path | None = None,
                 kinds: tuple[str, ...] = ('real',), salt: str = 'labelling-v1'):
        self.pairs_path = pairs_path
        self.labels_path = labels_path or pairs_path.parent / LABELS_NAME
        self.salt = salt
        self.lock = threading.Lock()
        data = yaml.safe_load(pairs_path.read_text())
        self.pairs = {}
        for raw in data['pairs']:
            if raw.get('kind') not in kinds or raw.get('expected') is not None:
                continue
            pair = dict(raw)
            for side in ('a', 'b'):
                pair[f'{side}_text'] = (pairs_path.parent / raw[side]).read_text()
            self.pairs[pair['pair_id']] = pair
        self.transcripts: dict[str, list[dict]] = {}

    def labels(self) -> dict:
        if not self.labels_path.exists():
            return {}
        return (yaml.safe_load(self.labels_path.read_text()) or {}).get('labels') or {}

    def index(self) -> list[dict]:
        done = self.labels()
        return [{'pair_id': pid, 'done': pid in done} for pid in self.pairs]

    def view(self, pair_id: str) -> dict:
        pair = self.pairs[pair_id]
        order = display_order(pair_id, self.salt)
        saved = self.labels().get(pair_id)
        return {
            'pair_id': pair_id,
            'task': pair['task'],
            'left': pair[f'{order["left"]}_text'],
            'right': pair[f'{order["right"]}_text'],
            'saved': None if saved is None else {
                'choice': next(k for k, v in order.items() if v == saved['label'])
                if saved['label'] in ('a', 'b') else 'tie',
                'note': saved.get('note', '')},
            'transcript': self.transcripts.get(pair_id, []),
        }

    def save(self, pair_id: str, choice: str, note: str, seconds: float | None) -> dict:
        if pair_id not in self.pairs:
            raise KeyError(pair_id)
        if choice not in CHOICES:
            raise ValueError(f'choice must be one of {sorted(CHOICES)}')
        order = display_order(pair_id, self.salt)
        label = 'tie' if choice == 'tie' else order[choice]
        with self.lock:
            labels = self.labels()
            entry = {
                'label': label,
                'shown': order,
                'note': note or '',
                'saved_at': now(),
                'seconds_on_pair': None if seconds is None else round(float(seconds), 1),
                'assistant': list(self.transcripts.get(pair_id, [])),
            }
            previous = labels.get(pair_id)
            if previous is not None:
                history = previous.pop('history', [])
                entry['history'] = history + [previous]
            labels[pair_id] = entry
            body = {
                'version': 1,
                'note': ('The user\'s labels, written by labelling_app/server.py. '
                         'label is the canonical side (a, b) or tie; shown is the '
                         'display order. quality.py reads label as expected.'),
                'pairs': str(self.pairs_path.name),
                'labels': labels,
            }
            tmp = self.labels_path.with_suffix('.yaml.tmp')
            tmp.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))
            os.replace(tmp, self.labels_path)
        return entry


class Assistant:
    def __init__(self, base_url: str | None, model: str | None):
        self.base_url = (base_url or '').rstrip('/') or None
        self.model = model or None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def messages(self, pair_view: dict, history: list[dict], question: str) -> list[dict]:
        context = (f'<<<TASK>>>\n{pair_view["task"]}\n<<<END TASK>>>\n\n'
                   f'<<<LEFT>>>\n{pair_view["left"]}\n<<<END LEFT>>>\n\n'
                   f'<<<RIGHT>>>\n{pair_view["right"]}\n<<<END RIGHT>>>')
        msgs = [{'role': 'system', 'content': ASSIST_SYSTEM},
                {'role': 'user', 'content': context},
                {'role': 'assistant', 'content': 'I have read the task and both responses.'}]
        for turn in history:
            msgs += [{'role': 'user', 'content': turn['q']},
                     {'role': 'assistant', 'content': turn['a']}]
        msgs.append({'role': 'user', 'content': question})
        return msgs

    def ask(self, messages: list[dict]) -> str:
        body = json.dumps({
            'model': self.model, 'messages': messages, 'temperature': 0,
            'max_tokens': ASSIST_MAX_TOKENS,
            'chat_template_kwargs': {'enable_thinking': False},
        }).encode()
        req = urllib.request.Request(f'{self.base_url}/chat/completions', data=body,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=ASSIST_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
        return strip_thinking(data['choices'][0]['message'].get('content'))


def make_handler(store: Store, assistant: Assistant):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter than the default
            sys.stderr.write(f'{self.address_string()} {fmt % args}\n')

        def send(self, status: int, payload, content_type='application/json'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def body(self) -> dict:
            length = int(self.headers.get('Content-Length') or 0)
            return json.loads(self.rfile.read(length) or b'{}')

        def do_GET(self):
            if self.path in ('/', '/index.html'):
                return self.send(200, (ROOT / 'static' / 'index.html').read_bytes(),
                                 'text/html; charset=utf-8')
            if self.path == '/api/pairs':
                return self.send(200, {'pairs': store.index(),
                                       'assistant': assistant.enabled,
                                       'labels_file': str(store.labels_path)})
            m = re.fullmatch(r'/api/pair/([\w.-]+)', self.path)
            if m and m.group(1) in store.pairs:
                return self.send(200, store.view(m.group(1)))
            self.send(404, {'error': 'not found'})

        def do_POST(self):
            try:
                data = self.body()
            except (ValueError, json.JSONDecodeError):
                return self.send(400, {'error': 'bad JSON'})
            if self.path == '/api/label':
                try:
                    entry = store.save(data.get('pair_id', ''), data.get('choice', ''),
                                       data.get('note', ''), data.get('seconds'))
                except KeyError:
                    return self.send(404, {'error': 'unknown pair'})
                except ValueError as exc:
                    return self.send(400, {'error': str(exc)})
                return self.send(200, {'saved': entry['saved_at']})
            if self.path == '/api/ask':
                pid, question = data.get('pair_id', ''), (data.get('question') or '').strip()
                if pid not in store.pairs or not question:
                    return self.send(400, {'error': 'pair_id and question are required'})
                if not assistant.enabled:
                    return self.send(503, {'error': 'assistant is off: set --assist-base-url and --assist-model'})
                history = store.transcripts.setdefault(pid, [])
                try:
                    answer = assistant.ask(assistant.messages(store.view(pid), history, question))
                except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
                    return self.send(502, {'error': f'assistant call failed: {exc}'})
                history.append({'q': question, 'a': answer, 'at': now()})
                return self.send(200, {'answer': answer})
            self.send(404, {'error': 'not found'})

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Labelling app (Q-06)')
    ap.add_argument('--pairs', default=str(DEFAULT_PAIRS), help='pairs manifest (YAML)')
    ap.add_argument('--labels', default=None, help='labels file (default: labels.yaml beside --pairs)')
    ap.add_argument('--kind', action='append', default=None,
                    help='pair kinds to label (repeatable; default: real)')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8766)
    ap.add_argument('--assist-base-url', default=os.environ.get('ASSIST_BASE_URL'),
                    help='OpenAI-compatible base URL ending in /v1 (default: $ASSIST_BASE_URL; off if unset)')
    ap.add_argument('--assist-model', default=os.environ.get('ASSIST_MODEL'),
                    help='assistant model name (default: $ASSIST_MODEL; off if unset)')
    args = ap.parse_args(argv)
    store = Store(Path(args.pairs), Path(args.labels) if args.labels else None,
                  tuple(args.kind or ['real']))
    assistant = Assistant(args.assist_base_url, args.assist_model)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, assistant))
    print(f'labelling {len(store.pairs)} pairs from {args.pairs}')
    print(f'labels -> {store.labels_path}')
    print(f'assistant: {"on, " + assistant.model + " at " + assistant.base_url if assistant.enabled else "off"}')
    print(f'open http://{args.host}:{args.port}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
