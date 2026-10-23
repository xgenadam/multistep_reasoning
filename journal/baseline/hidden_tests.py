#!/usr/bin/env python3
"""Phase Q hidden-test runner (Q-02 stage 0; design: journal/design/Q-01-judge.md § 1, P5).

Code prompts are scored by hidden tests: pytest files beside the prompt that
no arm ever sees. This tool pulls a deliverable's files out of an arm's
output, writes them to a fresh temp dir, copies the hidden tests in and runs
pytest there with a hard wall timeout. A test result is objective; no judge
verdict replaces it. It never calls a model.

Usage (from the repo root):
  .venv/bin/python journal/baseline/hidden_tests.py check-bench \\
      --bench journal/baseline/bench/v1
  .venv/bin/python journal/baseline/hidden_tests.py score RUN_FILE \\
      --bench journal/baseline/bench/v1 --jobs 4

Bench layout (BENCH = journal/baseline/bench/v1):
  BENCH/manifest.yaml           prompts: [{id, domain: code|report, files: [...]}, ...]
  BENCH/prompts/<id>.md         the prompt text every arm gets
  BENCH/tests/<id>/test_*.py    hidden tests (plus fixture files), stdlib + pytest
  BENCH/reference/<id>/...      a reference solution, only to validate the tests
  BENCH/reference/<id>/broken/  optional wrong variants: each sub-dir is overlaid
                                on the reference (it need only hold the changed
                                files); a plain file replaces the reference file
                                of the same name. Each must fail >= 1 test.

`check-bench` validates a bench before it is frozen: per code prompt the
reference passes every test, an empty deliverable passes none, every broken
variant fails at least one, and every manifest `files:` path is in the
reference. One line per prompt; exit 1 if any prompt fails.

`score` reads a run file (JSON, `results`: [{prompt_id, arm, run, output:
{text, snapshot | None}, error}, ...]) and scores every result whose prompt
is in the code domain: the snapshot's file parts when there is a snapshot,
else the text, parsed leniently with the manifest's `files:` as the expected
paths. It writes <run file stem>.tests.json beside the run file and prints a
prompt x arm table of passed/total. The denominator is the reference's test
count (an output that fails to import errors once at collection, not once
per test). No Wilson CIs and no pooling across domains: stage 2 does that.

Sandbox: the files go to <tmp>/work, which is pytest's cwd, rootdir, HOME and
only PYTHONPATH entry; the pytest config is a fixed <tmp>/pytest.ini, so a
deliverable's own pytest.ini / pyproject.toml cannot change the options.
Only the hidden test files are passed to pytest, so a deliverable's own
test_*.py is never collected. Plugin autoload is off. When `unshare -rn`
works the run has no network (isolation 'netns'), else 'none'. On timeout
the whole process group is killed. The temp dir is always removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH = Path(__file__).parent / 'bench' / 'v1'
DEFAULT_TIMEOUT_S = 120
OUTPUT_TAIL_BYTES = 2048
BROKEN_DIR = 'broken'
PYTHON_LANGS = {'python', 'py', 'python3', 'py3'}
# Info-string words that name a language or a role, never a file.
_NON_PATH_INFO = {'text', 'txt', 'console', 'shell', 'output', 'plaintext'}


# ---------------------------------------------------------------- paths

class UnsafePath(ValueError):
    pass


def safe_path(raw: str) -> str:
    """Normalise a deliverable path to a relative POSIX path, or raise UnsafePath.

    Rejects absolute paths, drive letters, `..`, `~`, NUL and empty names.
    Backslashes are read as separators and a leading `./` is dropped.
    """
    p = (raw or '').strip().replace('\\', '/')
    if not p or '\0' in p:
        raise UnsafePath(f'empty or NUL path: {raw!r}')
    if re.match(r'^[A-Za-z]:', p):
        raise UnsafePath(f'drive letter: {raw!r}')
    if p.startswith('/'):
        raise UnsafePath(f'absolute path: {raw!r}')
    if p.startswith('~'):
        raise UnsafePath(f'home-relative path: {raw!r}')
    parts = [s for s in p.split('/') if s not in ('', '.')]
    if not parts:
        raise UnsafePath(f'empty path: {raw!r}')
    if any(s == '..' for s in parts):
        raise UnsafePath(f'parent reference: {raw!r}')
    return '/'.join(parts)


def _target(root: Path, rel: str) -> Path:
    """The file under root for a safe relative path; refuses anything outside root."""
    target = (root / safe_path(rel)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise UnsafePath(f'escapes the sandbox: {rel!r}')
    return target


def _map_to_expected(path: str, expected: list[str] | None) -> tuple[str, str | None]:
    """Map a found path onto an expected one: (path, how) with how None if unchanged."""
    if not expected or path in expected:
        return path, None
    # A longer path ending in an expected one (src/pkg/core.py -> pkg/core.py).
    tails = [e for e in expected if path.endswith('/' + e)]
    if len(tails) == 1:
        return tails[0], 'expected_suffix'
    # A bare basename that names exactly one expected path (core.py -> pkg/core.py).
    if '/' not in path:
        same = [e for e in expected if PurePosixPath(e).name == path]
        if len(same) == 1:
            return same[0], 'expected_basename'
    return path, None


# ---------------------------------------------------------------- extraction

def extract_from_snapshot(snapshot: dict,
                          expected_paths: list[str] | None = None) -> tuple[dict[str, str], dict]:
    """File parts of a Document snapshot by path, plus extraction notes."""
    files: dict[str, str] = {}
    notes = _new_notes('snapshot')
    expected = list(expected_paths or [])
    for i, part in enumerate(snapshot.get('parts') or []):
        notes['blocks'] += 1
        if part.get('kind') != 'file':
            continue
        title = part.get('title')
        if not title:
            notes['ignored'].append({'block': i, 'reason': 'file part without a title'})
            continue
        try:
            path = safe_path(title)
        except UnsafePath as e:
            notes['ignored'].append({'block': i, 'reason': 'unsafe path', 'detail': str(e)})
            continue
        path, how = _map_to_expected(path, expected)
        _claim(files, notes, path, part.get('body') or '', i,
               'snapshot_part' + (f'+{how}' if how else ''), title)
    _finish_notes(notes, files, expected)
    return files, notes


def files_from_snapshot(snapshot: dict) -> dict[str, str]:
    """The snapshot's file parts by path (title), later parts winning."""
    return extract_from_snapshot(snapshot)[0]


_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
_PATH_TOKEN = r'[A-Za-z0-9_.][\w.\-]*(?:[/\\][\w.\-]+)*\.[A-Za-z0-9]+'
_PATH_RE = re.compile(rf'^{_PATH_TOKEN}$')
_KEY_PATH = re.compile(r'(?:title|file|filename|path|name)\s*=\s*["\']?([^"\'\s}]+)', re.I)
_LABEL_PREFIX = re.compile(r'^(?:file\s*name|filename|file|path)\s*[:\-]\s*', re.I)
_COMMENT_PATH = re.compile(
    rf'^\s*(?:#|//|--|;|/\*|<!--)\s*(?:(?:file\s*name|filename|file|path)\s*:\s*)?'
    rf'({_PATH_TOKEN})\s*(?:\*/|-->)?\s*$', re.I)
_MENTION = re.compile(rf'`({_PATH_TOKEN})`|\*\*({_PATH_TOKEN})\*\*|__({_PATH_TOKEN})__')


def _new_notes(source: str) -> dict:
    return {'source': source, 'blocks': 0, 'files': {}, 'duplicates': [],
            'unlabelled': [], 'ignored': [], 'missing': [], 'unclosed_fence': False}


def _finish_notes(notes: dict, files: dict, expected: list[str]) -> None:
    notes['missing'] = [p for p in expected if p not in files]
    notes['extracted'] = sorted(files)


def _claim(files: dict, notes: dict, path: str, body: str, block: int,
           rule: str, raw: str) -> None:
    if path in files:
        notes['duplicates'].append({'path': path, 'replaced_block': notes['files'][path]['block'],
                                    'by_block': block})
    files[path] = body
    notes['files'][path] = {'rule': rule, 'block': block, 'raw': raw}


def _unwrap_markdown(text: str) -> tuple[str, bool]:
    """Strip one fence around the whole answer when it is a markdown wrapper
    (```markdown or ```md first, a bare closing fence last). Models do this,
    and the wrapper would otherwise swallow or split the inner code blocks."""
    lines = text.splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
    if first is None or last is None or last <= first:
        return text, False
    m = _FENCE.match(lines[first])
    if m is None or m.group(2).strip().lower() not in ('markdown', 'md'):
        return text, False
    close = lines[last].strip()
    if not (set(close) == {m.group(1)[0]} and len(close) >= 3):
        return text, False
    return '\n'.join(lines[first + 1:last]), True


def _blocks(text: str) -> tuple[list[dict], bool]:
    """CommonMark-style fenced blocks: info, body, the label line before, line numbers."""
    lines = text.splitlines()
    blocks: list[dict] = []
    i, prev_end, unclosed = 0, 0, False
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m or (m.group(1)[0] == '`' and '`' in m.group(2)):
            i += 1
            continue
        fence, info = m.group(1), m.group(2).strip()
        label = next((lines[k].strip() for k in range(i - 1, prev_end - 1, -1)
                      if lines[k].strip()), None)
        close = re.compile(rf'^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*$')
        j = i + 1
        while j < len(lines) and not close.match(lines[j]):
            j += 1
        if j >= len(lines):
            unclosed = True
        blocks.append({'info': info, 'body': '\n'.join(lines[i + 1:j]), 'label': label,
                       'line': i + 1})
        prev_end = j + 1
        i = j + 1
    return blocks, unclosed


def _info_path(info: str) -> tuple[str | None, str]:
    """(path, lang) from a fence info string."""
    if not info:
        return None, ''
    m = _KEY_PATH.search(info)
    tokens = info.replace('{', ' ').replace('}', ' ').split()
    first = tokens[0].lstrip('.') if tokens else ''
    lang = first.split(':', 1)[0].lower()
    if m:
        return m.group(1), lang
    if ':' in first and _PATH_RE.match(first.split(':', 1)[1]):
        return first.split(':', 1)[1], lang
    for t in tokens[1:]:
        if _PATH_RE.match(t.strip('"\'')):
            return t.strip('"\''), lang
    if _PATH_RE.match(first) and lang not in PYTHON_LANGS:
        return first, PurePosixPath(first).suffix.lstrip('.').lower()
    return None, lang


def _label_path(label: str | None, expected: list[str]) -> tuple[str | None, str | None]:
    """(path, rule) from the line before a fence: a bare path, else one mentioned path."""
    if not label:
        return None, None
    s = re.sub(r'^#+\s*', '', label)                 # markdown heading
    s = re.sub(r'^(?:[-*+]|\d+[.)])\s+', '', s)       # list marker
    s = s.strip().rstrip(':').strip()
    s = re.sub(r'^(\*\*|__|\*|_|`)(.*)\1$', r'\2', s).strip()
    s = _LABEL_PREFIX.sub('', s).strip()
    s = re.sub(r'^(\*\*|__|\*|_|`)(.*)\1$', r'\2', s).strip().rstrip(':').strip()
    s = s.strip('`*_').strip()
    if _PATH_RE.match(s) or s in expected:
        return s, 'label_line'
    # "## wordcount.py (CLI)" or "Here is `wordcount.py`:" - one path named on the line.
    found = {next(g for g in m.groups() if g) for m in _MENTION.finditer(label)}
    if not found:
        head = re.match(rf'^#+\s*({_PATH_TOKEN})\b', label.strip())
        if head:
            found = {head.group(1)}
    if not found and expected:
        found = {e for e in expected if re.search(rf'(?<![\w/.]){re.escape(e)}(?![\w/])', label)}
    if len(found) == 1:
        return found.pop(), 'label_mention'
    return None, None


def _comment_path(body: str) -> str | None:
    lines = body.splitlines()
    if lines and lines[0].startswith('#!'):
        lines = lines[1:]
    if not lines:
        return None
    m = _COMMENT_PATH.match(lines[0])
    return m.group(1) if m else None


def _looks_python(lang: str, body: str) -> bool:
    if lang in PYTHON_LANGS:
        return True
    if lang or '>>>' in body:
        return False
    return bool(re.search(r'^(?:def |class |import |from \S+ import )', body, re.M))


def extract_files(text: str,
                  expected_paths: list[str] | None = None) -> tuple[dict[str, str], dict]:
    """Lenient parse of free markdown into {path: content}, plus extraction notes.

    A block's path comes from, in order: the fence info string
    (```python wordcount.py, ```python title="x.py", ```python:x.py), the line
    before the fence when it is a bare path (wordcount.py, **x.py**, `x.py`,
    ### x.py, File: x.py, - x.py:), a first-line comment inside the block
    (# x.py, # file: pkg/core.py, // x.js; after a shebang), or one path
    mentioned on the line before (Here is `x.py`:). Found paths are mapped
    onto `expected_paths` by suffix or unique basename. A lone unlabelled
    python block goes to the single expected .py path nobody claimed. When
    two blocks claim a path the later wins (recorded in notes['duplicates']).

    Notes: files (path -> rule, block, raw path), duplicates, unlabelled
    (blocks with no path that were not mapped), ignored (unsafe paths,
    ambiguous blocks), missing (expected paths not found), extracted,
    unclosed_fence.
    """
    expected = list(expected_paths or [])
    files: dict[str, str] = {}
    notes = _new_notes('text')
    text, notes['unwrapped_markdown'] = _unwrap_markdown(text or '')
    blocks, notes['unclosed_fence'] = _blocks(text)
    notes['blocks'] = len(blocks)
    unlabelled: list[tuple[int, dict, str]] = []
    for idx, b in enumerate(blocks):
        info_p, lang = _info_path(b['info'])
        label_p, label_rule = _label_path(b['label'], expected)
        comment_p = _comment_path(b['body'])
        candidates = [(info_p, 'info_string'),
                      (label_p if label_rule == 'label_line' else None, 'label_line'),
                      (comment_p, 'first_line_comment'),
                      (label_p if label_rule == 'label_mention' else None, 'label_mention')]
        raw, rule = next(((p, r) for p, r in candidates if p), (None, None))
        if rule == 'label_mention' and not _lang_fits(lang, raw):
            raw = rule = None  # "Run `python x.py`:" before a bash block names no file
        if raw is None:
            unlabelled.append((idx, b, lang))
            continue
        try:
            path = safe_path(raw)
        except UnsafePath as e:
            notes['ignored'].append({'block': idx, 'line': b['line'], 'reason': 'unsafe path',
                                     'detail': str(e)})
            continue
        path, how = _map_to_expected(path, expected)
        if rule == 'label_mention' and path in files:
            notes['ignored'].append({'block': idx, 'line': b['line'], 'path': path,
                                     'reason': 'mention would replace a labelled file'})
            continue
        others = {safe_path(p) for p, _ in candidates if p and p != raw and _safe(p)}
        if others - {path, raw}:
            notes.setdefault('conflicts', []).append(
                {'block': idx, 'chosen': path, 'other': sorted(others - {path, raw})})
        _claim(files, notes, path, b['body'], idx, rule + (f'+{how}' if how else ''), raw)

    open_py = [e for e in expected if e.endswith('.py') and e not in files]
    py_blocks = [(idx, b) for idx, b, lang in unlabelled if _looks_python(lang, b['body'])]
    mapped = None
    if len(open_py) == 1 and len(py_blocks) == 1:
        mapped = py_blocks[0][0]
        _claim(files, notes, open_py[0], py_blocks[0][1]['body'], mapped,
               'lone_python_block', '')
    elif len(open_py) == 1 and len(py_blocks) > 1:
        # Code plus usage examples: the block with the most def/class lines
        # (then the longest, then the last) is taken as the file. It is a
        # guess, so the rule name says so and stage 2 can count it.
        def weight(item):
            idx, b = item
            lines = b['body'].splitlines()
            defs = sum(ln.lstrip().startswith(('def ', 'class ', 'async def ')) for ln in lines)
            return defs, len(lines), idx
        mapped, block = max(py_blocks, key=weight)
        _claim(files, notes, open_py[0], block['body'], mapped, 'largest_python_block_guess', '')
    for idx, b, lang in unlabelled:
        if idx == mapped:
            continue
        first = next((ln.strip() for ln in b['body'].splitlines() if ln.strip()), '')
        entry = {'block': idx, 'line': b['line'], 'lang': lang, 'first_line': first[:80]}
        if open_py and len(py_blocks) > 1 and any(idx == i for i, _ in py_blocks):
            entry['reason'] = 'several unlabelled python blocks'
        notes['unlabelled'].append(entry)
    _finish_notes(notes, files, expected)
    return files, notes


_SHELL_LANGS = {'bash', 'sh', 'shell', 'zsh', 'console', 'shell-session', 'pycon',
                'text', 'txt', 'plaintext', 'output', 'none'}


def _lang_fits(lang: str, path: str) -> bool:
    """False when a shell/console/output block is claimed for a non-shell file."""
    ext = PurePosixPath(path).suffix.lstrip('.').lower()
    if lang in _SHELL_LANGS:
        return ext in {'sh', 'bash', 'txt', 'text', 'out', 'log'}
    if lang in PYTHON_LANGS:
        return ext in {'py', 'pyi'}
    return True


def _safe(p: str) -> bool:
    try:
        safe_path(p)
        return True
    except UnsafePath:
        return False


def files_from_text(text: str, expected_paths: list[str] | None = None) -> dict[str, str]:
    """{path: content} from free markdown; extract_files() also returns the notes."""
    return extract_files(text, expected_paths)[0]


def extract_output(output: dict | None,
                   expected_paths: list[str] | None = None) -> tuple[dict[str, str], dict]:
    """A run-file output: the snapshot's file parts if there is a snapshot, else the text."""
    output = output or {}
    if output.get('snapshot'):
        return extract_from_snapshot(output['snapshot'], expected_paths)
    if output.get('text'):
        return extract_files(output['text'], expected_paths)
    notes = _new_notes('none')
    _finish_notes(notes, {}, list(expected_paths or []))
    return {}, notes


# ---------------------------------------------------------------- running

_ISOLATION: str | None = None
_ISOLATION_LOCK = threading.Lock()


def isolation() -> str:
    """'netns' when `unshare -rn` works here (detected once), else 'none'."""
    global _ISOLATION
    with _ISOLATION_LOCK:
        if _ISOLATION is None:
            try:
                ok = subprocess.run(['unshare', '-rn', 'true'], capture_output=True,
                                    timeout=10).returncode == 0
            except (OSError, subprocess.SubprocessError):
                ok = False
            _ISOLATION = 'netns' if ok else 'none'
        return _ISOLATION


def _test_files(tests_dir: Path) -> list[str]:
    return sorted(p.relative_to(tests_dir).as_posix() for p in tests_dir.rglob('*.py')
                  if '__pycache__' not in p.parts
                  and (p.name.startswith('test_') or p.name.endswith('_test.py')))


def _parse_junit(path: Path) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    if not path.exists():
        return outcomes
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return outcomes
    for case in root.iter('testcase'):
        name = '::'.join(x for x in (case.get('classname'), case.get('name')) if x)
        tags = {child.tag for child in case}
        if 'failure' in tags:
            outcome = 'failed'
        elif 'error' in tags:
            outcome = 'error'
        elif 'skipped' in tags:
            outcome = 'skipped'
        else:
            outcome = 'passed'
        if any(c.tag == 'error' and 'collection failure' in (c.get('message') or '')
               for c in case):
            outcome = 'collection_error'
        outcomes[name] = outcome
    return outcomes


def run_tests(files: dict[str, str], tests_dir: str | Path,
              timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
    """Write files to a fresh temp dir, copy the hidden tests in, run pytest there.

    Returns passed, failed, errors, skipped, total (from the junit XML),
    collection_error, timed_out, seconds, exit_code, outcomes (name ->
    passed|failed|error|skipped|collection_error), overridden (deliverable
    files replaced by a hidden-test file), rejected (unsafe paths, not
    written), isolation and output_tail (the last ~2 KB of pytest's output).
    """
    tests_dir = Path(tests_dir)
    iso = isolation()
    tmp = Path(tempfile.mkdtemp(prefix='hidden-tests-'))
    try:
        work = tmp / 'work'
        work.mkdir()
        rejected, written = [], set()
        for rel, body in files.items():
            try:
                target = _target(work, rel)
            except UnsafePath as e:
                rejected.append(str(e))
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body if body.endswith('\n') or not body else body + '\n')
            except OSError as e:  # a file where a dir must go, or the reverse
                rejected.append(f'{rel!r}: {e}')
                continue
            written.add(target.relative_to(work.resolve()).as_posix())
        overridden = []
        for src in sorted(tests_dir.rglob('*')):
            if src.is_dir() or '__pycache__' in src.parts:
                continue
            rel = src.relative_to(tests_dir).as_posix()
            if rel in written:
                overridden.append(rel)
            dest = work / rel
            if dest.is_dir():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        (tmp / 'pytest.ini').write_text('[pytest]\n')
        junit = tmp / 'junit.xml'
        cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               f'--junitxml={junit}', '-c', str(tmp / 'pytest.ini'), '--rootdir', str(work),
               *_test_files(tests_dir)]
        if iso == 'netns':
            cmd = ['unshare', '-rn', *cmd]
        env = {'HOME': str(work), 'PYTHONPATH': str(work), 'PYTHONDONTWRITEBYTECODE': '1',
               'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PATH': '/usr/local/bin:/usr/bin:/bin',
               'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TMPDIR': str(tmp)}
        out_path = tmp / 'output.txt'
        timed_out = False
        start = time.monotonic()
        with open(out_path, 'wb') as out:
            proc = subprocess.Popen(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                exit_code = proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                exit_code = proc.wait()
        seconds = round(time.monotonic() - start, 3)
        tail = out_path.read_bytes()[-OUTPUT_TAIL_BYTES:].decode('utf-8', 'replace')
        outcomes = {} if timed_out else _parse_junit(junit)
        counts = {k: sum(1 for o in outcomes.values() if o == k)
                  for k in ('passed', 'failed', 'skipped')}
        counts['errors'] = sum(1 for o in outcomes.values() if o in ('error', 'collection_error'))
        collection_error = (any(o == 'collection_error' for o in outcomes.values())
                            or (exit_code == 2 and 'during collection' in tail))
        return {**counts, 'total': len(outcomes), 'collection_error': collection_error,
                'timed_out': timed_out, 'seconds': seconds, 'exit_code': exit_code,
                'outcomes': outcomes, 'overridden': overridden, 'rejected': rejected,
                'isolation': iso, 'output_tail': tail}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- bench

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_commit() -> dict:
    """Same shape as quality.git_commit (not imported: that pulls in openai)."""
    def git(*args: str) -> str:
        return subprocess.run(['git', *args], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=False).stdout.strip()
    return {'commit': git('rev-parse', 'HEAD'),
            'dirty': bool(git('status', '--porcelain', '--untracked-files=no'))}


def load_manifest(bench: Path) -> dict[str, dict]:
    data = yaml.safe_load((Path(bench) / 'manifest.yaml').read_text()) or {}
    prompts = data.get('prompts') or []
    return {str(p['id']): p for p in prompts}


def read_tree(root: Path, skip: tuple[str, ...] = ()) -> dict[str, str]:
    """Every file under root as {relative posix path: text}, skipping top-level names."""
    files: dict[str, str] = {}
    for p in sorted(Path(root).rglob('*')):
        rel = p.relative_to(root)
        if p.is_dir() or rel.parts[0] in skip or '__pycache__' in rel.parts:
            continue
        files[rel.as_posix()] = p.read_text()
    return files


def broken_variants(ref_dir: Path) -> dict[str, dict[str, str]]:
    """Each broken/ entry overlaid on the reference: {variant name: files}."""
    broken = Path(ref_dir) / BROKEN_DIR
    if not broken.is_dir():
        return {}
    reference = read_tree(ref_dir, skip=(BROKEN_DIR,))
    variants = {}
    for entry in sorted(broken.iterdir()):
        if entry.name == '__pycache__':
            continue
        overlay = read_tree(entry) if entry.is_dir() else {entry.name: entry.read_text()}
        variants[entry.name] = {**reference, **overlay}
    return variants


def check_prompt(bench: Path, entry: dict, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
    """check-bench for one code prompt: {'id', 'ok', 'problems', 'summary'}."""
    pid = str(entry['id'])
    tests_dir = bench / 'tests' / pid
    ref_dir = bench / 'reference' / pid
    problems: list[str] = []
    summary: dict = {}
    if not (bench / 'prompts' / f'{pid}.md').is_file():
        problems.append('no prompt file')
    if not tests_dir.is_dir() or not _test_files(tests_dir):
        problems.append('no hidden test files')
    if not ref_dir.is_dir():
        problems.append('no reference')
    expected = entry.get('files') or []
    if not expected:
        problems.append('manifest entry has no files:')
    if problems:
        return {'id': pid, 'ok': False, 'problems': problems, 'summary': summary}
    reference = read_tree(ref_dir, skip=(BROKEN_DIR,))
    missing = [p for p in expected if p not in reference]
    if missing:
        problems.append(f'files: not in reference: {missing}')
    ref = run_tests(reference, tests_dir, timeout_s)
    summary['reference'] = f"{ref['passed']}/{ref['total']}"
    if ref['total'] == 0 or ref['passed'] != ref['total'] or ref['timed_out']:
        bad = sorted(n for n, o in ref['outcomes'].items() if o != 'passed')
        problems.append(f"reference {summary['reference']}"
                        + (' (timed out)' if ref['timed_out'] else '')
                        + (f' not passing: {bad}' if bad else ''))
    empty = run_tests({}, tests_dir, timeout_s)
    summary['empty'] = f"{empty['passed']}/{ref['total']}"
    if empty['passed']:
        good = sorted(n for n, o in empty['outcomes'].items() if o == 'passed')
        problems.append(f'empty deliverable passes: {good}')
    variants = broken_variants(ref_dir)
    caught = 0
    for name, files in variants.items():
        res = run_tests(files, tests_dir, timeout_s)
        if res['total'] and res['passed'] < res['total'] or res['timed_out']:
            caught += 1
        else:
            problems.append(f'broken variant {name!r} passes every test')
    if variants:
        summary['broken'] = f'{caught}/{len(variants)} caught'
    return {'id': pid, 'ok': not problems, 'problems': problems, 'summary': summary}


def cmd_check_bench(args) -> int:
    bench = Path(args.bench)
    manifest = load_manifest(bench)
    entries = [e for e in manifest.values() if e.get('domain') == 'code'
               and (not args.prompt or str(e['id']) in args.prompt)]
    # A draft entry (bench README) has only a brief; it is checked once written.
    drafts = [] if args.include_drafts else [e for e in entries if e.get('status') == 'draft']
    entries = [e for e in entries if e not in drafts]
    if drafts:
        print(f'{len(drafts)} draft code prompt(s) skipped')
    if not entries:
        print('no code prompts to check')
        return 1
    print(f'isolation: {isolation()}')
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(lambda e: check_prompt(bench, e, args.timeout), entries))
    width = max(len(r['id']) for r in results)
    for r in results:
        summ = '  '.join(f'{k} {v}' for k, v in r['summary'].items())
        line = f"{r['id']:<{width}}  {'OK  ' if r['ok'] else 'FAIL'}  {summ}"
        if r['problems']:
            line += '  | ' + '; '.join(r['problems'])
        print(line.rstrip())
    failed = sum(not r['ok'] for r in results)
    print(f'{len(results) - failed}/{len(results)} code prompts OK')
    return 1 if failed else 0


# ---------------------------------------------------------------- score

def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def score_run(run_file: Path, bench: Path, jobs: int = 3,
              timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
    """Score every code-domain result of a run file; returns the .tests.json payload."""
    run_file, bench = Path(run_file), Path(bench)
    data = json.loads(run_file.read_text())
    manifest = load_manifest(bench)
    code = {pid: e for pid, e in manifest.items() if e.get('domain') == 'code'}
    results = data.get('results') or []
    todo = [r for r in results if str(r.get('prompt_id')) in code]
    unknown = sorted({str(r.get('prompt_id')) for r in results} - set(manifest))

    def reference(pid: str) -> dict:
        ref_dir = bench / 'reference' / pid
        if not ref_dir.is_dir():
            return {'n_tests': None, 'passed': None, 'source': 'none'}
        res = run_tests(read_tree(ref_dir, skip=(BROKEN_DIR,)), bench / 'tests' / pid, timeout_s)
        return {'n_tests': res['total'], 'passed': res['passed'], 'source': 'reference'}

    def one(r: dict) -> dict:
        pid = str(r['prompt_id'])
        files, notes = extract_output(r.get('output'), code[pid].get('files'))
        tests = run_tests(files, bench / 'tests' / pid, timeout_s)
        return {'prompt_id': pid, 'arm': r.get('arm'), 'run': r.get('run'),
                'run_error': r.get('error'), 'extraction': notes,
                'extraction_ok': bool(files) and not notes['missing'], 'tests': tests}

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        refs = dict(zip(sorted({str(r['prompt_id']) for r in todo}),
                        pool.map(reference, sorted({str(r['prompt_id']) for r in todo}))))
        scored = list(pool.map(one, todo))
    for s in scored:
        ref = refs[s['prompt_id']]
        n = ref['n_tests'] if ref['n_tests'] else s['tests']['total']
        s['n_tests'] = n
        s['pass_rate'] = round(s['tests']['passed'] / n, 4) if n else 0.0
    return {'run_file': _rel(run_file), 'run_file_sha256': sha256_file(run_file),
            'bench': _rel(bench), 'manifest_sha256': sha256_file(bench / 'manifest.yaml'),
            **git_commit(), 'isolation': isolation(), 'timeout_s': timeout_s,
            'scored_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'references': refs, 'skipped_unknown_prompts': unknown, 'results': scored}


def print_table(payload: dict) -> None:
    cells: dict[tuple[str, str], list[str]] = {}
    for s in payload['results']:
        mark = '' if s['extraction_ok'] else '*'
        if s['tests']['timed_out']:
            mark += 'T'
        cells.setdefault((s['prompt_id'], str(s['arm'])), []).append(
            f"{s['tests']['passed']}/{s['n_tests']}{mark}")
    prompts = sorted({p for p, _ in cells})
    arms = sorted({a for _, a in cells})
    if not prompts:
        print('no code-domain results')
        return
    cols = {a: max(len(a), *(len(' '.join(cells.get((p, a), ['-']))) for p in prompts))
            for a in arms}
    pw = max(len('prompt'), *(len(p) for p in prompts))
    print('  '.join(['prompt'.ljust(pw), *(a.ljust(cols[a]) for a in arms)]).rstrip())
    for p in prompts:
        print('  '.join([p.ljust(pw), *(' '.join(cells.get((p, a), ['-'])).ljust(cols[a])
                                        for a in arms)]).rstrip())
    print('passed/n_tests per run; * extraction incomplete, T timed out')


def cmd_score(args) -> int:
    run_file = Path(args.run_file)
    payload = score_run(run_file, Path(args.bench), args.jobs, args.timeout)
    out = run_file.with_name(f'{run_file.stem}.tests.json')
    out.write_text(json.dumps(payload, indent=2) + '\n')
    print(f"isolation: {payload['isolation']}  results: {len(payload['results'])}")
    if payload['skipped_unknown_prompts']:
        print(f"not in the manifest: {payload['skipped_unknown_prompts']}")
    print_table(payload)
    print(f'wrote {_rel(out)}')
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Phase Q hidden-test runner (Q-02)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('score', help='score the code results of a run file')
    s.add_argument('run_file')
    c = sub.add_parser('check-bench', help='validate the hidden tests of a bench')
    c.add_argument('--prompt', action='append', default=None, help='prompt id (repeatable)')
    c.add_argument('--include-drafts', action='store_true',
                   help='also check entries still marked draft (while writing them)')
    for p in (s, c):
        p.add_argument('--bench', default=str(DEFAULT_BENCH))
        p.add_argument('--jobs', type=int, default=3)
        p.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_S,
                       help='hard wall timeout per pytest run, seconds')
    args = ap.parse_args(argv)
    return cmd_score(args) if args.cmd == 'score' else cmd_check_bench(args)


if __name__ == '__main__':
    sys.exit(main())
