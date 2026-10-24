"""ifeval_score.py over the vendored IFEval checker (Q-02 bias guard 4.1).

The checker's packages live only in .venv-ifeval (`make venv-ifeval`), so the
scorer runs there in a subprocess; the test skips when that venv is absent.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PY = REPO / '.venv-ifeval' / 'bin' / 'python'
SCORER = REPO / 'journal' / 'baseline' / 'ifeval_score.py'

pytestmark = pytest.mark.skipif(not PY.exists(), reason='no .venv-ifeval (make venv-ifeval)')

# sr01: "might" at least 6 times, all lowercase, 3 paragraphs separated by ***.
FOLLOWS = ('you might think this is fine. it might not be. you might regret it.\n'
           '***\n'
           'i might forgive you. i might not.\n'
           '***\n'
           'the empire might yet survive this.')


def _run_file(tmp_path, results):
    path = tmp_path / 'run.json'
    path.write_text(json.dumps({'generator': 'flash-next', 'results': results}))
    return path


def _row(pid, arm, text, error=None):
    return {'prompt_id': pid, 'arm': arm, 'run': 0, 'error': error, 'output': {'text': text}}


def test_scores_strict_and_loose_per_arm(tmp_path):
    path = _run_file(tmp_path, [
        _row('sr01', 'b', FOLLOWS),
        _row('sr01', 'a2', FOLLOWS.upper()),           # breaks lowercase only
        _row('sr01', 'a', '', error='boom'),           # an error follows nothing
        _row('r01', 'b', 'not an IFEval prompt'),      # ignored
    ])
    proc = subprocess.run([str(PY), str(SCORER), str(path)], capture_output=True, text=True,
                          cwd=REPO, timeout=120)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(path.with_suffix('.ifeval.json').read_text())
    by_arm = {r['arm']: r for r in report['results']}
    assert set(by_arm) == {'b', 'a2', 'a'}
    assert by_arm['b']['strict'] == {'all': True, 'per_instruction': {
        'keywords:frequency': True, 'change_case:english_lowercase': True,
        'length_constraints:number_paragraphs': True}}
    a2 = by_arm['a2']['strict']['per_instruction']
    assert a2['change_case:english_lowercase'] is False
    assert a2['length_constraints:number_paragraphs'] is True
    assert by_arm['a']['strict']['all'] is False and by_arm['a']['loose']['all'] is False
    s = report['summary']
    assert s['b']['prompt_level_strict'] == 1.0 and s['a']['instruction_level_loose'] == 0.0
    assert s['a2']['instruction_level_strict'] == pytest.approx(2 / 3, abs=1e-4)


def test_project_venv_refuses_cleanly():
    """The project's .venv has no checker packages: a clear exit, not a traceback."""
    proc = subprocess.run([str(REPO / '.venv' / 'bin' / 'python'), str(SCORER), 'x.json'],
                          capture_output=True, text=True, cwd=REPO, timeout=60)
    assert proc.returncode != 0 and '.venv-ifeval' in proc.stderr
