"""labelling_app/server.py: blinding, label mapping, the labels file and quality.py's use of it (Q-06)."""

import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from tests.test_baseline.conftest import load_baseline_module

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER = REPO_ROOT / 'labelling_app' / 'server.py'


@pytest.fixture(scope='module')
def app():
    spec = importlib.util.spec_from_file_location('labelling_server', SERVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def manifest(tmp_path):
    (tmp_path / 'c').mkdir()
    for name in ('r1a', 'r1b', 'r2a', 'r2b', 'wa', 'wb'):
        (tmp_path / 'c' / f'{name}.md').write_text(f'text {name}')
    pairs = {'pairs': [
        {'pair_id': 'R1', 'kind': 'real', 'task': 'task one', 'a': 'c/r1a.md', 'b': 'c/r1b.md',
         'expected': None, 'source': 'run-0 vs run-1 SECRET'},
        {'pair_id': 'R2', 'kind': 'real', 'task': 'task two', 'a': 'c/r2a.md', 'b': 'c/r2b.md',
         'expected': None, 'source': 'SECRET'},
        {'pair_id': 'W1', 'kind': 'damaged', 'task': 't', 'a': 'c/wa.md', 'b': 'c/wb.md',
         'expected': 'a', 'source': 'SECRET'},
    ]}
    path = tmp_path / 'pairs.yaml'
    path.write_text(yaml.safe_dump(pairs))
    return path


def test_display_order_is_stable_and_shuffles(app):
    orders = [app.display_order(f'P{i}', 'salt') for i in range(40)]
    assert app.display_order('P3', 'salt') == orders[3]
    assert {o['left'] for o in orders} == {'a', 'b'}
    assert all({o['left'], o['right']} == {'a', 'b'} for o in orders)


def test_store_lists_only_unlabelled_real_pairs_and_hides_provenance(app, manifest):
    store = app.Store(manifest)
    assert [p['pair_id'] for p in store.index()] == ['R1', 'R2']
    view = store.view('R1')
    assert set(view) == {'pair_id', 'task', 'left', 'right', 'saved', 'transcript'}
    assert 'SECRET' not in json.dumps(view)
    order = app.display_order('R1', store.salt)
    assert view['left'] == f'text r1{order["left"]}'


@pytest.mark.parametrize('choice', ['left', 'right', 'tie'])
def test_save_maps_display_side_to_canonical(app, manifest, choice):
    store = app.Store(manifest)
    order = app.display_order('R1', store.salt)
    store.save('R1', choice, 'because', 12.34)
    entry = yaml.safe_load((manifest.parent / 'labels.yaml').read_text())['labels']['R1']
    assert entry['label'] == ('tie' if choice == 'tie' else order[choice])
    assert entry['shown'] == order and entry['note'] == 'because'
    assert entry['seconds_on_pair'] == 12.3
    assert store.view('R1')['saved'] == {'choice': choice, 'note': 'because'}
    assert store.index()[0]['done'] is True


def test_relabel_keeps_history_and_rejects_bad_input(app, manifest):
    store = app.Store(manifest)
    store.save('R1', 'left', 'first', None)
    store.save('R1', 'tie', 'second', None)
    entry = store.labels()['R1']
    assert entry['label'] == 'tie' and [h['note'] for h in entry['history']] == ['first']
    with pytest.raises(ValueError):
        store.save('R1', 'a', '', None)
    with pytest.raises(KeyError):
        store.save('W1', 'left', '', None)


def test_assistant_prompt_is_blind_and_forbids_verdicts(app, manifest):
    store = app.Store(manifest)
    msgs = app.Assistant('http://x.invalid/v1', 'm').messages(
        store.view('R1'), [{'q': 'q0', 'a': 'a0'}], 'does Left handle errors?')
    text = json.dumps(msgs)
    assert 'never' in msgs[0]['content'] and 'better' in msgs[0]['content']
    assert '<<<LEFT>>>' in text and '<<<RIGHT>>>' in text and 'SECRET' not in text
    assert [m['role'] for m in msgs][-3:] == ['user', 'assistant', 'user']
    assert app.strip_thinking('<think>x</think> answer') == 'answer'


def test_server_never_reads_verdict_files(app):
    assert 'verdicts' not in SERVER.read_text()


def _serve(app, store, assistant):
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(store, assistant))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_address[1]}'


def _req(url, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_http_flow_with_and_without_assistant(app, manifest, monkeypatch):
    store = app.Store(manifest)
    off, url = _serve(app, store, app.Assistant(None, None))
    try:
        status, page = _req(url + '/')
        assert status == 200 and b'Pair labelling' in page
        status, body = _req(url + '/api/pairs')
        assert status == 200 and json.loads(body)['assistant'] is False
        status, body = _req(url + '/api/pair/R2')
        assert status == 200 and b'SECRET' not in body
        assert _req(url + '/api/pair/W1')[0] == 404
        assert _req(url + '/api/ask', {'pair_id': 'R1', 'question': 'q'})[0] == 503
        assert _req(url + '/api/label', {'pair_id': 'R1', 'choice': 'nope'})[0] == 400
    finally:
        off.shutdown()

    assistant = app.Assistant('http://x.invalid/v1', 'm')
    monkeypatch.setattr(assistant, 'ask', lambda messages: 'Left exits 1 on line 9.')
    on, url = _serve(app, store, assistant)
    try:
        status, body = _req(url + '/api/ask', {'pair_id': 'R1', 'question': 'exit code?'})
        assert status == 200 and json.loads(body)['answer'] == 'Left exits 1 on line 9.'
        assert _req(url + '/api/label', {'pair_id': 'R1', 'choice': 'right', 'seconds': 5})[0] == 200
    finally:
        on.shutdown()
    entry = store.labels()['R1']
    assert entry['assistant'][0]['q'] == 'exit code?'


def test_quality_reads_labels_and_report_rescores(app, manifest, tmp_path, capsys, monkeypatch):
    quality = load_baseline_module('quality')
    store = app.Store(manifest)
    store.save('R1', 'tie', '', None)
    pairs = {p['pair_id']: p for p in quality.load_pairs(manifest)}
    assert pairs['R1']['expected'] == 'tie' and pairs['R2']['expected'] is None

    calls = [{'pair_id': 'R1', 'order': order, 'repeat': 0, 'side': None, 'winner': 'tie',
              'verdict': {}, 'attempts': [], 'seconds': 1.0, 'prompt_tokens': 1,
              'completion_tokens': 1} for order in ('ab', 'ba')]
    for c in calls:
        c['side'] = 'tie'
    verdicts = tmp_path / 'v.json'
    verdicts.write_text(json.dumps({
        'judge_model': 'm', 'judge_backend': 'b', 'rubric': 'r', 'commit': 'abcdef0', 'dirty': False,
        'calls': calls, 'summary': quality.summarise(
            [dict(pairs['R1'], expected=None)], calls)}))
    monkeypatch.setattr('sys.argv', ['quality.py', 'report', str(verdicts), '--pairs', str(manifest)])
    assert quality.main() == 0
    out = capsys.readouterr().out
    assert 'R1    real     tie' in out

    labels = yaml.safe_load((manifest.parent / 'labels.yaml').read_text())
    labels['labels']['W1'] = {'label': 'b'}
    (manifest.parent / 'labels.yaml').write_text(yaml.safe_dump(labels))
    with pytest.raises(ValueError, match='contradicts'):
        quality.load_pairs(manifest)


def test_real_validation_manifest_offers_r1_to_r5(app):
    store = app.Store(app.DEFAULT_PAIRS, labels_path=Path('/nonexistent/labels.yaml'))
    assert [p['pair_id'] for p in store.index()] == ['R1', 'R2', 'R3', 'R4', 'R5']
