#!/usr/bin/env python3
"""Q-E1's pre-registered analysis (Q-02 stage 2; the pre-registration in Q-02
Notes, 2026-10-23, as amended 2026-10-24 by the delegated review, D-026).

One command turns the committed run files, hidden-test and IFEval scores and
verdict files into the verdict: one JSON report and a short markdown summary.
It never calls a model. Every threshold below is pre-registered and is a
constant here, not an option, so this is the only analysis.

Usage (from the repo root):
  .venv/bin/python journal/baseline/qe1_analysis.py report --spec SPEC.yaml \\
      [--out runs/qe1-analysis]
writes OUT/qe1_analysis.json and OUT/qe1_analysis.md and prints the markdown.

The spec lists the inputs (paths are relative to the repo root):

  bench: journal/baseline/bench/v1            # default
  std_bench: journal/baseline/bench/v1-std    # default
  conditions:
    judge_labels: pending   # D-021: flash-next on the R1-R5 labels (Q-06): pass | fail | pending
    spot_check: pending     # § 4.4, the user's blind spot check: done | pending
  generators:
    flash-next:             # one block per generator (arms.GENERATORS)
      runs: [the campaign's arms run files on bench v1, every arm; pilots never]
      verdicts:             # quality.py verdict files, built by qe1_pairs.py
        b:a2: {record: FILE, concurrence: FILE}   # the claims; Devstral concurs
        b:a: {record: FILE}
        b:a1: {record: FILE}
        c:b: {record: FILE}                       # qe1_pairs --subset overlap
      aa:                   # § 4.3, flash-next: g3 run again for b and a2
        runs: [the repeat run file(s)]
        verdicts: {b: FILE, a2: FILE}             # qe1_pairs --pair X:X --repeat
      std:                  # § 4.1, bench v1-std, b and a2
        runs: [run files]
        verdicts: {b:a2: {record: FILE}}          # the code half's test ties
A verdict entry may be a list of files (one judging split over windows).
Code results need `<run stem>.tests.json` beside the run file (hidden_tests.py
score); v1-std report results need `<run stem>.ifeval.json` (ifeval_score.py).
Each verdict file's pairs manifest (its `pairs_path`) must be on disk with the
sha256 the verdict file recorded: it is what fixes which arm is side a. It is
deterministic, so qe1_pairs.py with the same arguments rebuilds it.

Per-prompt outcome (qe1_pairs.outcome_rule): a side that errored or (code)
delivered nothing extractable loses; code with different hidden-test
pass-rates is decided by the tests; everything else goes to the judge, both
orders, decisive only when both agree (quality.pair_outcome; a pair with no
parseable verdict is left out of the decisive count, as in quality.py).

The Test, per generator x domain claim of (b) over (a''), on decisive pairs:
  gain                 Wilson 95 % lower bound > 0.5, point >= 0.70 and the
                       concurrence judge's decisive rate on the same pairs
                       > 0.5 (code: the rule re-run with Devstral breaking the
                       test ties; test- and failure-decided prompts count
                       identically for both judges)
  better               lower bound > 0.5 without the rest ("better, below the
                       pre-registered effect"; uncorrected, no Holm)
  worse                upper bound < 0.5; in a cell where (a'') is
                       over-resourced (Q-7: its median completion tokens
                       above 1.25x the harness's) it reads "not better at r x
                       compute" (`not_better_at_compute`)
  inconclusive         otherwise
A cell with any missing or inconsistent input gets no verdict (`withheld`),
with the reasons. The re-plan trigger is a gain in at least one cell.

Also reported: the roots-only sensitivity (prompts without `follows`), the
long/short split (descriptive), the secondary pairings (b vs a, b vs a1,
c vs b on the overlap subset) as plain statistics, Q-7 per generator x
domain x stratum, the v1-std table beside v1's short strata, the A/A noise
floor, and the exact-binomial power of the gain bar at each cell's n.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

import arms  # noqa: E402
import qe1_pairs  # noqa: E402
import quality  # noqa: E402
from harness import CONSOLIDATION_SUMMARY_PHASE  # noqa: E402

# ---------------------------------------------------------------------------
# Pre-registered constants (Q-02 Notes; PLAN Q-6, Q-7; D-019, D-021, D-026)
# ---------------------------------------------------------------------------

VERSION = 'qe1-analysis-v1'
EFFECT = Fraction(7, 10)          # the gain bar's point estimate
NULL = 0.5
Z = 1.96                          # Wilson 95 %
Q7_MIN, Q7_OVER = 0.75, 1.25      # PLAN Q-7, one-sided, with the over-resourced label
PRIMARY = ('b', 'a2')
SECONDARY = {'b:a': None, 'b:a1': None, 'c:b': 'overlap'}   # pairing -> subset
AA_ARMS = ('b', 'a2')
AA_SUBSET = 'g3'
STD_PAIR = ('b', 'a2')
RUBRIC = 'pairwise_v1'
JUDGE_MARKS = {'flash-next': 'flash-next', 'devstral': 'devstral'}   # substring of judge_model
POWER_AT = (0.70, 0.75, 0.80)
DEFAULT_STD_BENCH = Path(__file__).parent / 'bench' / 'v1-std'
DEFAULT_OUT = REPO_ROOT / 'runs' / 'qe1-analysis'


# ---------------------------------------------------------------------------
# Statistics (pure)
# ---------------------------------------------------------------------------


def tally(outcomes: list[str | None]) -> dict:
    """Counts and rates from side x's view. Each outcome is 'win', 'loss',
    'tie' or 'no_verdict' (left out of every rate, as in quality.py)."""
    wins, losses = outcomes.count('win'), outcomes.count('loss')
    ties, no_verdict = outcomes.count('tie'), outcomes.count('no_verdict')
    decisive, n = wins + losses, wins + losses + ties
    ci = quality.wilson(wins, decisive, Z)
    return {'n': n, 'decisive': decisive, 'wins': wins, 'losses': losses, 'ties': ties,
            'no_verdict': no_verdict,
            'decisive_rate': wins / decisive if decisive else None,
            'wilson95': list(ci) if ci else None,
            'tie_rate': ties / n if n else None,
            'all_pairs_rate': (wins + 0.5 * ties) / n if n else None}


def meets_effect(wins: int, decisive: int) -> bool:
    """Point estimate at or above 0.70, in exact arithmetic (35/50 counts)."""
    return decisive > 0 and Fraction(wins, decisive) >= EFFECT


def bar_passes(k: int, n: int, gain: bool = True) -> bool:
    """The record judge's half of the Test for k wins in n decisive pairs:
    the Wilson lower bound above 0.5, plus (gain) the point at the effect."""
    ci = quality.wilson(k, n, Z)
    return ci is not None and ci[0] > NULL and (not gain or meets_effect(k, n))


def power(n: int, p: float, gain: bool = True) -> float:
    """Exact-binomial probability that the bar passes at a true rate p."""
    return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k)
               for k in range(n + 1) if bar_passes(k, n, gain))


def power_note(n: int) -> dict:
    """The gain bar's power at the observed n (the record judge's half; the
    concurrence condition can only lower it), and the false-pass rates."""
    if n <= 0:
        return {'n': n}
    return {'n': n,
            'gain_bar': {f'{p:.2f}': power(n, p) for p in POWER_AT},
            'better': {f'{p:.2f}': power(n, p, gain=False) for p in POWER_AT},
            'null_gain_bar': power(n, NULL), 'null_better': power(n, NULL, gain=False)}


def _direction(rate: float | None) -> int | None:
    if rate is None:
        return None
    return 0 if rate == NULL else (1 if rate > NULL else -1)


def classify(rec: dict, conc: dict, q7_ratio: float | None) -> dict:
    """The amended Test for one claim: verdict code, label, and whether it
    counts for the re-plan trigger. `rec` and `conc` are tally() results on
    the same prompts; `q7_ratio` is (a'')'s median completion tokens over the
    harness's in the cell (None when it cannot be computed)."""
    lo, hi = rec['wilson95'] or (None, None)
    better = lo is not None and lo > NULL
    worse = hi is not None and hi < NULL
    point = meets_effect(rec['wins'], rec['decisive'])
    conc_rate = conc['decisive_rate']
    conc_ok = conc_rate is not None and conc_rate > NULL
    conditions = {'lower_bound_above_0.5': better, 'point_at_least_0.70': point,
                  'concurrence_above_0.5': conc_ok}
    if better and point and conc_ok:
        code, label = 'gain', 'gain (the pre-registered effect)'
    elif better:
        code = 'better'
        if not point:
            label = 'better, below the pre-registered effect'
        else:
            label = 'better, not a gain: the concurrence judge does not favour (b)'
        if not point and not conc_ok:
            label += '; the concurrence judge does not favour (b) either'
        label += ' (uncorrected)'
    elif worse:
        code, label = 'worse', 'worse'
    else:
        code, label = 'inconclusive', 'inconclusive'
    over = q7_ratio is not None and q7_ratio > Q7_OVER
    under = q7_ratio is None or q7_ratio < Q7_MIN
    if over:
        if code == 'worse':
            code, label = 'not_better_at_compute', f'not better at {q7_ratio:.2f}x compute'
        label += f" (a'' over-resourced, {q7_ratio:.2f}x)"
    counts = code == 'gain' and not under
    if code == 'gain' and under:
        label += ("; Q-7 not met (a'' at "
                  + (f'{q7_ratio:.2f}x' if q7_ratio is not None else 'an unknown ratio')
                  + ' of the harness): not compute-matched, so it does not trigger')
    rd, cd = _direction(rec['decisive_rate']), _direction(conc_rate)
    return {'verdict': code, 'label': label, 'conditions': conditions,
            'counts_for_trigger': counts,
            'judges_disagree': rd is not None and cd is not None and rd != cd}


def distribution(values: list[float]) -> dict | None:
    if not values:
        return None
    v = sorted(values)
    q = statistics.quantiles(v, n=4, method='inclusive') if len(v) > 1 else [v[0]] * 3
    return {'n': len(v), 'min': v[0], 'p25': q[0], 'median': q[1], 'p75': q[2], 'max': v[-1]}


# ---------------------------------------------------------------------------
# Verdict files
# ---------------------------------------------------------------------------


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def _paths(entry) -> list[Path]:
    if entry is None:
        return []
    return [_resolve(p) for p in (entry if isinstance(entry, list) else [entry])]


def judge_outcomes(calls: list[dict]) -> tuple[dict[str, str], list[str]]:
    """pair_id -> 'a' / 'b' / 'tie' / 'no_verdict' over both orders of
    repeat 0, and the pair ids judged in one order only."""
    sides: dict[str, dict[str, str | None]] = {}
    for c in calls:
        if c.get('repeat', 0) == 0:
            sides.setdefault(c['pair_id'], {})[c['order']] = c.get('side')
    out, half = {}, []
    for pid, by_order in sides.items():
        if all(o in by_order for o in quality.ORDERS):
            out[pid] = quality.pair_outcome(by_order['ab'], by_order['ba'])
        else:
            half.append(pid)
    return out, sorted(half)


def load_verdicts(paths: list[Path], judge: str, inputs: dict) -> dict:
    """One judge's verdicts for one pairing: outcomes, the manifest they
    judged and the problems found (each one withholds what depends on it)."""
    problems, calls, shas, pairs_paths, models = [], [], set(), set(), set()
    if not paths:
        return {'missing': True, 'problems': [f'no {judge} verdict file'], 'outcomes': {}}
    for path in paths:
        if not path.exists():
            problems.append(f'verdict file {path} does not exist')
            continue
        inputs[str(path)] = _sha_file(path)
        data = json.loads(path.read_text())
        if data.get('rubric') != RUBRIC:
            problems.append(f'{path.name}: rubric {data.get("rubric")!r}, not {RUBRIC}')
        if (data.get('settings') or {}).get('max_tokens') != quality.VERDICT_MAX_TOKENS:
            problems.append(f'{path.name}: verdict max_tokens '
                            f'{(data.get("settings") or {}).get("max_tokens")}, '
                            f'not {quality.VERDICT_MAX_TOKENS}')
        models.add(str(data.get('judge_model')))
        shas.add(data.get('pairs_sha256'))
        pairs_paths.add(data.get('pairs_path'))
        calls += data.get('calls') or []
    if problems and not calls:
        return {'missing': True, 'problems': problems, 'outcomes': {}}
    if not all(JUDGE_MARKS[judge] in m.lower() for m in models):
        problems.append(f'judge model(s) {sorted(models)} are not {judge}')
    if len(shas) != 1:
        problems.append('the verdict files judged different pairs manifests')
    keys = [(c['pair_id'], c['order'], c.get('repeat', 0)) for c in calls]
    if len(keys) != len(set(keys)):
        problems.append('a pair-order is judged twice across the verdict files')
    outcomes, half = judge_outcomes(calls)
    if half:
        problems.append(f'{len(half)} pair(s) judged in one order only: {", ".join(half[:8])}')
    return {'missing': False, 'files': [str(p) for p in paths], 'models': sorted(models),
            'pairs_sha256': shas.pop() if len(shas) == 1 else None,
            'pairs_path': pairs_paths.pop() if len(pairs_paths) == 1 else None,
            # The pre-registration judges once; later repeats are not read.
            'ignored_repeats': sum(c.get('repeat', 0) != 0 for c in calls),
            'outcomes': outcomes, 'problems': problems}


def check_manifest(verdicts: dict, built: dict, x: str, y: str, run_hashes: set[str],
                   repeat_hashes: set[str] | None, inputs: dict) -> list[str]:
    """The judged manifest is the one these run files give: same sha256 as
    the verdict file recorded, the same orientation, its run files among
    ours, and the same judge pairs on the prompts analysed."""
    if verdicts.get('missing') or not verdicts.get('pairs_path'):
        return []
    path = _resolve(verdicts['pairs_path'])
    if not path.exists():
        return [f'pairs manifest {verdicts["pairs_path"]} is not on disk: rebuild it with '
                'qe1_pairs.py (same arguments) so its orientation can be checked']
    text = path.read_text()
    inputs[str(path)] = _sha_file(path)
    problems = []
    if quality.sha256(text) != verdicts['pairs_sha256']:
        problems.append(f'{path}: sha256 differs from the one the verdict file judged')
    manifest = yaml.safe_load(text)
    if manifest.get('arms') != {'a': x, 'b': y}:
        problems.append(f'{path}: arms {manifest.get("arms")}, expected a = {x}, b = {y}')
    if not set((manifest.get('run_files') or {}).values()) <= run_hashes:
        problems.append(f'{path}: built from run files that are not in the spec (or changed)')
    if repeat_hashes is not None and \
            not set((manifest.get('repeat_run_files') or {}).values()) <= repeat_hashes:
        problems.append(f'{path}: built from repeat run files that are not in the spec')
    ours = {p['pair_id'] for p in built['pairs']}
    theirs = {p['pair_id'] for p in manifest.get('pairs') or []}
    scope = {d['prompt_id'] for d in built['decided']} | ours
    if theirs & scope != ours:
        diff = sorted((theirs & scope) ^ ours)
        problems.append(f'{path}: judge pairs differ from the run files\' ({", ".join(diff[:8])})')
    return problems


# ---------------------------------------------------------------------------
# Run files
# ---------------------------------------------------------------------------


def check_runs(paths: list[Path], generator: str, bench: dict, inputs: dict) -> list[dict]:
    """Problems with a generator's run files, each tagged with the domain it
    withholds (None: every domain)."""
    problems = []
    for path in paths:
        if not path.exists():
            problems.append({'domain': None, 'what': f'run file {path} does not exist'})
            continue
        inputs[str(path)] = _sha_file(path)
        data = json.loads(path.read_text())
        name = path.name
        if data.get('kind') != 'q-e1-arms':
            problems.append({'domain': None, 'what': f'{name}: not an arms.py run file'})
        if data.get('generator') != generator:
            problems.append({'domain': None,
                             'what': f'{name}: generator {data.get("generator")}, not {generator}'})
        if data.get('manifest_sha256') != bench['sha256']:
            problems.append({'domain': None, 'what': f'{name}: ran on another bench manifest '
                             f'than {bench["path"]}'})
        if not data.get('bench_frozen'):
            problems.append({'domain': None, 'what': f'{name}: the bench was not frozen'})
        if 'pilot' in str(data.get('label') or ''):
            problems.append({'domain': None,
                             'what': f'{name}: a pilot run (pilot outputs are excluded)'})
        code = [r for r in data.get('results') or []
                if bench['prompts'].get(r['prompt_id'], {}).get('domain') == 'code']
        if code:
            side = path.with_suffix('.tests.json')
            if not side.exists():
                problems.append({'domain': 'code', 'what': f'{name}: no hidden-test scores '
                                 f'({side.name}; hidden_tests.py score)'})
            else:
                inputs[str(side)] = _sha_file(side)
                scored = json.loads(side.read_text())
                if scored.get('run_file_sha256') not in (None, inputs[str(path)]):
                    problems.append({'domain': 'code', 'what': f'{side.name} scored another '
                                     'version of its run file'})
    return problems


def load_all(paths: list[Path]) -> tuple[dict, dict, list[str]]:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return {}, {}, []
    try:
        results, tests, _ = qe1_pairs.load_results(existing)
    except SystemExit as exc:
        return {}, {}, [str(exc)]
    return results, tests, []


def completeness(prompts: dict, ids: list[str], rx: dict, x: str, ry: dict, y: str) -> list[str]:
    """Prompts with no result row for an arm: the campaign is not complete
    there (an errored row is a result and counts as a loss; a missing one
    is not a result)."""
    out = []
    for arm, results in ((x, rx), (y, ry)):
        missing = [pid for pid in ids if (pid, arm, 0) not in results]
        if missing:
            out.append(f'arm {arm} has no result on {len(missing)} prompt(s): '
                       + ', '.join(missing[:8]) + (' ...' if len(missing) > 8 else ''))
    return out


def outcome_rows(built: dict, judged: dict[str, dict], prompts: dict, x_name: str,
                 y_name: str) -> list[dict]:
    """One row per prompt: how it was decided and the outcome from side a's
    view under each judge (test- and failure-decided rows are the same for
    every judge; a judge pair with no verdict yet is None)."""
    to_x = {x_name: 'win', y_name: 'loss', 'tie': 'tie'}
    from_judge = {'a': 'win', 'b': 'loss', 'tie': 'tie', 'no_verdict': 'no_verdict'}
    rows = []
    for d in built['decided']:
        o = to_x[d['winner']]
        rows.append({'prompt_id': d['prompt_id'], 'by': d['by'],
                     **{j: o for j in judged}})
    for p in built['pairs']:
        rows.append({'prompt_id': p['pair_id'], 'by': 'judge',
                     **{j: from_judge.get(v['outcomes'].get(p['pair_id']))
                        for j, v in judged.items()}})
    for r in rows:
        e = prompts[r['prompt_id']]
        r.update(domain=e['domain'], long=bool(e.get('long')), root=e.get('follows') is None)
    return sorted(rows, key=lambda r: r['prompt_id'])


def pairing(gen: str, x: str, y: str, run_files: list[Path], bench_dir: Path, bench: dict,
            verdict_paths: dict[str, list[Path]], inputs: dict, run_problems: list[dict],
            results: dict, subset: str | None = None,
            repeat_files: list[Path] | None = None, repeat_results: dict | None = None) -> dict:
    """Per domain: the outcome rows of x against y and the problems that
    withhold each judge's statistics (key None: the data itself)."""
    prompts = bench['prompts']
    run_hashes = {inputs[str(p)] for p in run_files if str(p) in inputs}
    repeat_hashes = {inputs[str(p)] for p in repeat_files if str(p) in inputs} \
        if repeat_files else None
    out = {}
    verdicts = {j: load_verdicts(paths, j, inputs) for j, paths in verdict_paths.items()}
    for domain in arms.DOMAINS:
        ids = arms.select(prompts, subset, None, domain)
        data_problems = [p['what'] for p in run_problems if p['domain'] in (None, domain)]
        if results:  # with no run files at all, that is the one reason
            data_problems += completeness(prompts, ids, results, x,
                                          repeat_results if repeat_files else results, y)
        cell = {'prompts': len(ids), 'problems': {None: data_problems}, 'rows': None}
        out[domain] = cell
        if data_problems:
            continue
        try:
            built = qe1_pairs.build(run_files, x, y, bench_dir, 0, repeat_files=repeat_files,
                                    subset=subset, domain=domain)
        except SystemExit as exc:
            data_problems.append(str(exc))
            continue
        judged = {}
        for j, v in verdicts.items():
            probs = list(v['problems'])
            probs += check_manifest(v, built, x, y, run_hashes, repeat_hashes, inputs)
            unjudged = [p['pair_id'] for p in built['pairs'] if p['pair_id'] not in v['outcomes']]
            if unjudged and not v.get('missing'):
                probs.append(f'{len(unjudged)} judge pair(s) without a verdict: '
                             + ', '.join(unjudged[:8]))
            cell['problems'][j] = probs
            judged[j] = v
        names = ('a', 'b') if repeat_files else (x, y)
        cell['rows'] = outcome_rows(built, judged, prompts, *names)
        cell['judged_pairs'] = len(built['pairs'])
        cell['decided_by'] = {by: sum(r['by'] == by for r in cell['rows'])
                              for by in ('tests', 'failure', 'judge')}
    return out


def stats_for(cell: dict, judge: str, keep=lambda r: True) -> dict | None:
    """tally() of one judge's outcomes, or None when its inputs are incomplete."""
    if cell['rows'] is None or cell['problems'].get(None) or cell['problems'].get(judge) \
            or judge not in cell['problems']:
        return None
    return tally([r[judge] for r in cell['rows'] if keep(r)])


def withheld_reasons(cell: dict, judges: tuple[str, ...]) -> list[str]:
    out = list(cell['problems'].get(None) or [])
    for j in judges:
        if cell['rows'] is not None and j not in cell['problems']:
            out.append(f'no {j} verdict file')
        out += [f'{j}: {p}' for p in cell['problems'].get(j) or []]
    return out


def agreement(cell: dict, a: str, b: str) -> dict | None:
    """How often the two judges give the same outcome on the judge pairs."""
    if cell['rows'] is None:
        return None
    both = [r for r in cell['rows'] if r['by'] == 'judge'
            and r.get(a) not in (None, 'no_verdict') and r.get(b) not in (None, 'no_verdict')]
    same = sum(r[a] == r[b] for r in both)
    return {'pairs': len(both), 'same': same, 'rate': same / len(both) if both else None}


# ---------------------------------------------------------------------------
# Q-7, v1-std, consolidation
# ---------------------------------------------------------------------------


def q7_report(run_files: list[Path], prompts: dict, results: dict, gen: str) -> dict:
    """(a'')'s median completion tokens over the harness's per domain and
    stratum (arms.match_report), the per-prompt ratio distribution (both
    error-free), and the labels Q-7 sets."""
    strata = {pid: arms.stratum(e) for pid, e in prompts.items()}
    match = arms.match_report([p for p in run_files if p.exists()], strata=strata)
    out = {}
    for level in list(arms.DOMAINS) + list(arms.STRATA):
        entry = match.get(f'{gen}/{level}') or {}
        keys = [k for k in (entry.get('ratio_to_b') or {}) if k.startswith('a2@')]
        row = {'b_median': (entry.get('completion_p50') or {}).get('b'), 'a2_arm': None,
               'ratio_of_medians': None, 'q7_met': None, 'over_resourced': None}
        if len(keys) == 1:
            k = keys[0]
            # Unrounded (match_report rounds to 3 places, which could turn
            # 0.7496 into a met Q-7); the bounds are PLAN Q-7's.
            ratio = entry['completion_p50'][k] / entry['completion_p50']['b']
            row.update(a2_arm=k, a2_median=entry['completion_p50'][k],
                       ratio_of_medians=ratio, q7_met=ratio >= Q7_MIN,
                       over_resourced=ratio > Q7_OVER)
        elif len(keys) > 1:
            row['problem'] = f'more than one a2 rule in the run files: {keys}'
        ratios = []
        for pid, e in prompts.items():
            if level not in (e['domain'], strata[pid]):
                continue
            rb, ra = results.get((pid, 'b', 0)), results.get((pid, 'a2', 0))
            if rb and ra and rb['error'] is None and ra['error'] is None \
                    and rb['llm']['completion_tokens']:
                ratios.append(ra['llm']['completion_tokens'] / rb['llm']['completion_tokens'])
        row['per_prompt_ratio'] = distribution(ratios)
        out[level] = row
    return out


def budget_checks(run_files: list[Path], inputs: dict) -> list[str]:
    """Each a2 run file took its per-prompt budgets from a b run file in the
    spec (the amended compute-matching rule)."""
    out = []
    b_hashes = set()
    datas = []
    for p in run_files:
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        datas.append((p, data))
        if any(r['arm'] == 'b' for r in data['results']):
            b_hashes.add(inputs.get(str(p)))
    for p, data in datas:
        if not any(r['arm'] == 'a2' for r in data['results']):
            continue
        rb = data.get('refine_budget') or {}
        if rb.get('source') != 'run-file':
            out.append(f'{p.name}: a2 budgets are not per prompt from a b run file '
                       f'(source {rb.get("source")!r})')
        elif rb.get('sha256') not in b_hashes:
            out.append(f'{p.name}: a2 budgets came from a b run file not in the spec '
                       f'({rb.get("path")})')
    return out


def consolidation_counts(results: dict, ids: list[str]) -> dict:
    """(c)'s turns with a consolidate call, and those it changed (the summary
    call after consolidation runs only when ops applied)."""
    rows = [results[(pid, 'c', 0)] for pid in ids if (pid, 'c', 0) in results]
    ok = [r for r in rows if r['error'] is None]
    called = [r for r in ok if ((r['llm'].get('by_kind') or {}).get('consolidate') or {})
              .get('count')]
    changed = [r for r in ok if CONSOLIDATION_SUMMARY_PHASE in (r['llm'].get('by_phase') or {})]
    return {'turns': len(rows), 'error_free': len(ok), 'consolidate_called': len(called),
            'changed': len(changed)}


def task_pass(tests: dict, ids: list[str], arm: str) -> dict:
    """BigCodeBench's task-level pass: every test passes, no collection error."""
    rows = [tests.get((pid, arm, 0)) for pid in ids]
    k = sum(bool(t) and bool(t.get('n_tests')) and not (t.get('tests') or {}).get(
        'collection_error') and (t.get('tests') or {}).get('passed') == t['n_tests']
        for t in rows)
    n = len(ids)
    ci = quality.wilson(k, n, Z)
    return {'n': n, 'passed': k, 'rate': k / n if n else None, 'wilson95': list(ci) if ci else None}


def ifeval_outcomes(run_files: list[Path], results: dict, ids: list[str], x: str,
                    y: str) -> tuple[list[dict] | None, list[str], dict]:
    """v1-std's IFEval half: a failed side loses (both: a tie); otherwise
    the side that follows strictly more instructions (strict mode) wins."""
    strict: dict[tuple[str, str], int] = {}
    problems, summary = [], {}
    for p in run_files:
        side = p.with_suffix('.ifeval.json')
        data = json.loads(p.read_text()) if p.exists() else {'results': []}
        if not any(r['prompt_id'] in ids for r in data['results']):
            continue
        if not side.exists():
            problems.append(f'{p.name}: no IFEval scores ({side.name}; ifeval_score.py)')
            continue
        scored = json.loads(side.read_text())
        summary.update(scored.get('summary') or {})
        for s in scored['results']:
            if s.get('run', 0) == 0:
                strict[(s['prompt_id'], s['arm'])] = sum(
                    bool(v) for v in s['strict']['per_instruction'].values())
    if problems:
        return None, problems, summary
    rows = []
    for pid in ids:
        sides = []
        for arm in (x, y):
            r = results[(pid, arm, 0)]
            text = (r.get('output') or {}).get('text') or ''
            ok = r['error'] is None and bool(text.strip())
            if ok and (pid, arm) not in strict:
                problems.append(f'{pid} {arm}: no IFEval score')
            sides.append({'ok': ok, 'n': strict.get((pid, arm), 0)})
        sx, sy = sides
        if not sx['ok'] or not sy['ok']:
            o, by = ('tie' if not sx['ok'] and not sy['ok'] else
                     ('win' if sx['ok'] else 'loss')), 'failure'
        else:
            o, by = ('win' if sx['n'] > sy['n'] else 'loss' if sx['n'] < sy['n'] else 'tie'), \
                'ifeval'
        rows.append({'prompt_id': pid, 'by': by, 'outcome': o,
                     'strict_followed': {x: sx['n'], y: sy['n']}})
    return (None if problems else rows), problems, summary


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def analyse(spec: dict) -> dict:
    inputs: dict[str, str] = {}
    bench_dir = _resolve(spec.get('bench') or arms.DEFAULT_BENCH)
    std_dir = _resolve(spec.get('std_bench') or DEFAULT_STD_BENCH)
    bench = arms.load_bench(bench_dir)
    prompts = bench['prompts']
    cond = spec.get('conditions') or {}
    labels = cond.get('judge_labels') or 'pending'
    spot = cond.get('spot_check') or 'pending'
    provisional = []
    if labels != 'pass':
        provisional.append(f'D-021: flash-next is judge of record on condition it passes the '
                           f'R1-R5 labels (Q-06); status: {labels}')
    if spot != 'done':
        provisional.append("§ 4.4: the user's blind spot check of 12 (b) vs (a'') report pairs "
                           f'per generator is not done (status: {spot})')
    # D-021: if flash-next fails the labels, Devstral becomes judge of record
    # and flash-next the concurrence judge.
    record, concur = ('devstral', 'flash-next') if labels == 'fail' else ('flash-next', 'devstral')
    gens = spec.get('generators') or {}
    unknown = sorted(set(gens) - set(arms.GENERATORS))
    if unknown:
        raise SystemExit(f'unknown generator(s) in the spec: {unknown}')

    report = {'kind': 'q-e1-analysis', 'version': VERSION,
              'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
              **quality.git_commit(),
              'pre_registered': {
                  'effect': float(EFFECT), 'wilson_z': Z, 'q7_min': Q7_MIN, 'q7_over': Q7_OVER,
                  'primary': 'b vs a2', 'judge_of_record': record, 'concurrence_judge': concur,
                  'rubric': RUBRIC, 'multiplicity': 'none (amendment 2026-10-24)'},
              'conditions': {'judge_labels': labels, 'spot_check': spot,
                             'provisional': provisional},
              'bench': {'path': str(bench['path']), 'version': bench['version'],
                        'sha256': bench['sha256']},
              'claims': [], 'roots_only': [], 'long_short': [], 'secondary': [],
              'q7': {}, 'std': {}, 'aa': {}, 'arms_summary': {}, 'inputs': inputs}

    for gen in arms.GENERATORS:
        g = gens.get(gen) or {}
        runs = [_resolve(p) for p in g.get('runs') or []]
        run_problems = check_runs(runs, gen, bench, inputs) if runs else \
            [{'domain': None, 'what': 'no run files'}]
        results, _, load_problems = load_all(runs)
        run_problems += [{'domain': None, 'what': p} for p in load_problems]
        verdicts = g.get('verdicts') or {}

        # Q-7 first: the claims' labels need it.
        q7 = q7_report(runs, prompts, results, gen) if results else {}
        if results:
            q7['budget_problems'] = budget_checks(runs, inputs)
            report['arms_summary'][gen] = arms.summarise(
                [r for r in results.values() if r['run'] == 0])
        report['q7'][gen] = q7

        # The six claims.
        pv = verdicts.get('b:a2') or {}
        spec_roles = {'flash-next': _paths(pv.get('record')),
                      'devstral': _paths(pv.get('concurrence'))}
        cells = pairing(gen, *PRIMARY, runs, bench_dir, bench, spec_roles, inputs,
                        run_problems, results)
        for domain in arms.DOMAINS:
            cell = cells[domain]
            reasons = withheld_reasons(cell, (record, concur))
            rec, conc = stats_for(cell, record), stats_for(cell, concur)
            ratio = (q7.get(domain) or {}).get('ratio_of_medians')
            claim = {'generator': gen, 'domain': domain, 'prompts': cell['prompts'],
                     'decided_by': cell.get('decided_by'), 'record': rec, 'concurrence': conc,
                     'judges_agreement': agreement(cell, record, concur),
                     'q7_ratio': ratio,
                     'power': power_note(rec['decisive']) if rec else None,
                     'provisional': provisional,
                     # Deviations from the compute-matching rule: reported, not blocking.
                     'caveats': list(q7.get('budget_problems') or [])}
            if reasons:
                claim.update(status='withheld', verdict=None, label='no verdict: inputs missing',
                             counts_for_trigger=False, withheld_because=reasons)
            else:
                claim.update(status='verdict', **classify(rec, conc, ratio))
            claim['rows'] = cell['rows']
            report['claims'].append(claim)

            # Roots-only sensitivity (the same Test on prompts without `follows`).
            root = lambda r: r['root']  # noqa: E731
            rrec, rconc = stats_for(cell, record, root), stats_for(cell, concur, root)
            ro = {'generator': gen, 'domain': domain, 'record': rrec, 'concurrence': rconc}
            if reasons:
                ro.update(verdict=None, label='no verdict: inputs missing')
            else:
                c = classify(rrec, rconc, ratio)
                ro.update(verdict=c['verdict'], label=c['label'],
                          agrees_with_full=c['verdict'] == claim['verdict'])
            report['roots_only'].append(ro)

            # Long/short split (descriptive, § 4.2): the record judge.
            lng = stats_for(cell, record, lambda r: r['long'])
            sht = stats_for(cell, record, lambda r: not r['long'])
            report['long_short'].append({
                'generator': gen, 'domain': domain, 'long': lng, 'short': sht,
                'long_higher': (lng['decisive_rate'] > sht['decisive_rate'])
                if lng and sht and lng['decisive_rate'] is not None
                and sht['decisive_rate'] is not None else None})

        # Secondary pairings: descriptive statistics, the record judge only.
        for key, subset in SECONDARY.items():
            x, y = key.split(':')
            spec_v = verdicts.get(key) or {}
            # flash-next's verdicts; if it failed the labels they need Devstral (D-021).
            sec = pairing(gen, x, y, runs, bench_dir, bench,
                          {'flash-next': _paths(spec_v.get('record'))}, inputs,
                          run_problems, results, subset=subset)
            for domain in arms.DOMAINS:
                cell = sec[domain]
                entry = {'generator': gen, 'pairing': f'{x} vs {y}', 'domain': domain,
                         'subset': subset or 'all', 'prompts': cell['prompts'],
                         'record': stats_for(cell, 'flash-next'),
                         'missing': withheld_reasons(cell, ('flash-next',)) or None}
                if labels == 'fail':
                    entry['caveat'] = ('flash-next failed the R1-R5 labels: these need '
                                       'Devstral re-judging (D-021)')
                if x == 'c':
                    entry['consolidation'] = consolidation_counts(
                        results, arms.select(prompts, subset, None, domain))
                report['secondary'].append(entry)

        # § 4.3, the A/A control.
        aa = g.get('aa')
        if aa:
            aa_runs = [_resolve(p) for p in aa.get('runs') or []]
            aa_problems = check_runs(aa_runs, gen, bench, inputs) if aa_runs else \
                [{'domain': None, 'what': 'no A/A repeat run files'}]
            aa_results, _, lp = load_all(aa_runs)
            aa_problems += [{'domain': None, 'what': p} for p in lp]
            out = {}
            for arm in AA_ARMS:
                cellset = pairing(gen, arm, arm, runs, bench_dir, bench,
                                  {'flash-next': _paths((aa.get('verdicts') or {}).get(arm))},
                                  inputs, run_problems + aa_problems, results, subset=AA_SUBSET,
                                  repeat_files=aa_runs, repeat_results=aa_results)
                out[arm] = {d: {'prompts': c['prompts'], 'stats': stats_for(c, 'flash-next'),
                                'missing': withheld_reasons(c, ('flash-next',)) or None}
                            for d, c in cellset.items()}
            report['aa'][gen] = out

        # § 4.1, the standard slice.
        std = g.get('std')
        if std:
            report['std'][gen] = analyse_std(gen, std, std_dir, inputs, report['claims'], record)
    report['replan_trigger'] = replan(report['claims'])
    return report


def analyse_std(gen: str, std: dict, std_dir: Path, inputs: dict, claims: list[dict],
                record: str) -> dict:
    sbench = arms.load_bench(std_dir)
    sprompts = sbench['prompts']
    sruns = [_resolve(p) for p in std.get('runs') or []]
    problems = check_runs(sruns, gen, sbench, inputs) if sruns else \
        [{'domain': None, 'what': 'no v1-std run files'}]
    sresults, stests, lp = load_all(sruns)
    problems += [{'domain': None, 'what': p} for p in lp]
    x, y = STD_PAIR
    out = {'bench': {'version': sbench['version'], 'sha256': sbench['sha256']}}
    # Code half: the v1 rule, the record judge on test ties; task-level pass beside.
    cells = pairing(gen, x, y, sruns, std_dir, sbench,
                    {'flash-next': _paths(((std.get('verdicts') or {}).get('b:a2') or {})
                                          .get('record'))},
                    inputs, [p for p in problems if p['domain'] in (None, 'code')], sresults)
    code = cells['code']
    ids = arms.select(sprompts, None, None, 'code')
    out['code'] = {'prompts': code['prompts'], 'stats': stats_for(code, 'flash-next'),
                   'decided_by': code.get('decided_by'),
                   'missing': withheld_reasons(code, ('flash-next',)) or None,
                   'task_pass': {arm: task_pass(stests, ids, arm) for arm in (x, y)}
                   if code['rows'] is not None else None}
    # Report half: IFEval strict instruction counts.
    rids = arms.select(sprompts, None, None, 'report')
    rprob = [p['what'] for p in problems if p['domain'] in (None, 'report')]
    rprob += completeness(sprompts, rids, sresults, x, sresults, y)
    rows, ip, summary = (None, [], {}) if rprob else ifeval_outcomes(sruns, sresults, rids, x, y)
    rprob += ip
    out['report'] = {'prompts': len(rids), 'rule': 'IFEval strict: more instructions followed wins',
                     'stats': tally([r['outcome'] for r in rows]) if rows is not None else None,
                     'missing': rprob or None, 'ifeval_summary': summary or None, 'rows': rows}
    # Beside v1's short strata (record judge), never pooled with them.
    out['v1_short'] = {}
    for c in claims:
        if c['generator'] != gen:
            continue
        rows_v1 = c.get('rows')
        ok = c['record'] is not None and rows_v1 is not None
        out['v1_short'][c['domain']] = tally(
            [r[record] for r in rows_v1 if not r['long']]) if ok else None
    return out


def replan(claims: list[dict]) -> dict:
    gains = [f'{c["generator"]}/{c["domain"]}' for c in claims if c.get('counts_for_trigger')]
    withheld = [f'{c["generator"]}/{c["domain"]}' for c in claims if c['status'] == 'withheld']
    if gains:
        status = 'met'
        note = 'a gain in ' + ', '.join(gains) + ': phases A-T may build on the harness'
    elif withheld:
        status = 'undetermined'
        note = ('no gain among the cells with a verdict; ' + ', '.join(withheld)
                + ' have none yet, so the trigger cannot be decided')
    else:
        status = 'not met'
        note = ('no generator x domain cell shows a gain: the re-plan is a Fable 5.1 / high '
                'session (Q-02 Scope)')
    return {'status': status, 'gain_cells': gains, 'withheld_cells': withheld, 'note': note}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _round(obj, nd: int = 4):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {(str(k) if k is not None else 'data'): _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v, nd) for v in obj]
    return obj


def _f(x, nd: int = 2) -> str:
    return '-' if x is None else (f'{x:.{nd}f}' if isinstance(x, float) else str(x))


def _ci(s: dict | None) -> str:
    if not s or not s.get('wilson95'):
        return '-'
    lo, hi = s['wilson95']
    return f'{lo:.2f}-{hi:.2f}'


def _stat_cells(s: dict | None) -> list[str]:
    if s is None:
        return ['-'] * 6
    return [str(s['decisive']), str(s['wins']), str(s['ties']), _f(s['decisive_rate']),
            _ci(s), _f(s['all_pairs_rate'])]


def markdown(rep: dict) -> str:
    # Generators absent from the spec show once, in the claims table.
    present = set(rep['arms_summary'])
    L = ['# Q-E1 analysis (pre-registered; Q-02 stage 2)', '',
         f'Generated {rep["generated_at"]} at commit {rep["commit"][:7]}'
         f'{" (dirty)" if rep["dirty"] else ""} by `qe1_analysis.py` ({rep["version"]}). '
         f'Bench {rep["bench"]["version"]}. Judge of record: '
         f'{rep["pre_registered"]["judge_of_record"]}; concurrence: '
         f'{rep["pre_registered"]["concurrence_judge"]}.', '']
    if rep['conditions']['provisional']:
        L += ['**Provisional:**'] + [f'- {p}' for p in rep['conditions']['provisional']] + ['']
    t = rep['replan_trigger']
    L += [f'**Re-plan trigger: {t["status"]}.** {t["note"]}.', '',
          '## The six claims: (b) vs (a″), decisive pairs', '',
          '| Generator | Domain | n dec. | Wins | Ties | Rate | Wilson 95 % | All-pairs | '
          'Concurrence rate | Q-7 ratio | Verdict |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for c in rep['claims']:
        conc = c['concurrence']['decisive_rate'] if c['concurrence'] else None
        L.append('| ' + ' | '.join([c['generator'], c['domain'], *_stat_cells(c['record']),
                                    _f(conc), _f(c['q7_ratio']), c['label']]) + ' |')
    missing = [c for c in rep['claims'] if c['status'] == 'withheld']
    if missing:
        L += ['', '**Withheld cells:**']
        for c in missing:
            L.append(f'- {c["generator"]}/{c["domain"]}: ' + '; '.join(c['withheld_because'][:6]))
    caveats = [c for c in rep['claims'] if c.get('caveats')]
    if caveats:
        L += ['', '**Caveats:**'] + [f'- {c["generator"]}/{c["domain"]}: ' + '; '.join(c['caveats'])
                                     for c in caveats]
    disagree = [c for c in rep['claims'] if c.get('judges_disagree')]
    if disagree:
        L += ['', '**Judges disagree on direction** (D-021 re-open condition): '
              + ', '.join(f'{c["generator"]}/{c["domain"]}' for c in disagree)]
    L += ['', '## Power of the gain bar at the observed n (exact binomial, record judge)', '',
          '| Generator | Domain | n | at 0.70 | at 0.75 | at 0.80 | "better" at 0.70 | '
          'false gain at 0.5 |', '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for c in rep['claims']:
        p = c['power']  # None when the record judge's inputs are incomplete
        if p and p.get('gain_bar'):
            L.append(f'| {c["generator"]} | {c["domain"]} | {p["n"]} | '
                     + ' | '.join(_f(p['gain_bar'][k]) for k in ('0.70', '0.75', '0.80'))
                     + f' | {_f(p["better"]["0.70"])} | {_f(p["null_gain_bar"], 4)} |')
    L += ['', '## Roots-only sensitivity (prompts without `follows`)', '',
          '| Generator | Domain | n dec. | Wins | Ties | Rate | Wilson 95 % | All-pairs | '
          'Verdict | Same as full |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in rep['roots_only']:
        if r['generator'] not in present:
            continue
        L.append('| ' + ' | '.join([r['generator'], r['domain'], *_stat_cells(r['record']),
                                    r['label'], _f(r.get('agrees_with_full'))]) + ' |')
    L += ['', '## Long / short split (descriptive, § 4.2; record judge)', '',
          '| Generator | Domain | Long rate (n) | Long Wilson | Short rate (n) | Short Wilson | '
          'Long higher |', '| --- | --- | --- | --- | --- | --- | --- |']
    for r in rep['long_short']:
        if r['generator'] not in present:
            continue
        lg, sh = r['long'], r['short']
        L.append(f'| {r["generator"]} | {r["domain"]} | '
                 f'{_f(lg and lg["decisive_rate"])} ({lg["decisive"] if lg else "-"}) | {_ci(lg)} | '
                 f'{_f(sh and sh["decisive_rate"])} ({sh["decisive"] if sh else "-"}) | {_ci(sh)} | '
                 f'{_f(r["long_higher"])} |')
    L += ['', '## Secondary pairings (descriptive; record judge)', '',
          '| Generator | Pairing | Domain | Subset | n dec. | Wins | Ties | Rate | Wilson 95 % | '
          'All-pairs | Note |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for s in rep['secondary']:
        if s['generator'] not in present:
            continue
        note = 'missing: ' + '; '.join(s['missing'][:2]) if s['missing'] else ''
        if s.get('consolidation') and s['consolidation']['turns']:
            k = s['consolidation']
            note = (note + ' ' if note else '') + \
                f'consolidation changed {k["changed"]} of {k["turns"]} turns'
        L.append('| ' + ' | '.join([s['generator'], s['pairing'], s['domain'], s['subset'],
                                    *_stat_cells(s['record']), note]) + ' |')
    L += ['', "## Q-7: (a″) ÷ (b) median completion tokens per prompt", '',
          '| Generator | Level | b median | a″ median | Ratio | Q-7 met | Over-resourced | '
          'Per-prompt ratio p25 / median / p75 (n) |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for gen, q in rep['q7'].items():
        for level in list(arms.DOMAINS) + list(arms.STRATA):
            r = q.get(level)
            if not r:
                continue
            d = r['per_prompt_ratio']
            dist = f'{d["p25"]:.2f} / {d["median"]:.2f} / {d["p75"]:.2f} ({d["n"]})' if d else '-'
            L.append(f'| {gen} | {level} | {_f(r["b_median"], 0)} | {_f(r.get("a2_median"), 0)} | '
                     f'{_f(r["ratio_of_medians"])} | {_f(r["q7_met"])} | '
                     f'{_f(r["over_resourced"])} | {dist} |')
        for p in q.get('budget_problems') or []:
            L.append(f'\n- {gen}: {p}')
    if rep['std']:
        L += ['', '## Standard slice v1-std (§ 4.1), beside v1 short strata', '',
              '| Generator | Half | n dec. | Wins | Ties | Rate | Wilson 95 % | All-pairs | '
              'v1 short rate | v1 short Wilson | Note |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        for gen, s in rep['std'].items():
            for half in arms.DOMAINS:
                h = s[half]
                v1 = s['v1_short'].get(half)
                note = 'missing: ' + '; '.join(h['missing'][:2]) if h['missing'] else ''
                if half == 'code' and h.get('task_pass'):
                    note += ' task pass ' + ', '.join(
                        f'{a} {tp["passed"]}/{tp["n"]}' for a, tp in h['task_pass'].items())
                L.append('| ' + ' | '.join([gen, half, *_stat_cells(h['stats']),
                                            _f(v1 and v1['decisive_rate']), _ci(v1),
                                            note.strip()]) + ' |')
    if rep['aa']:
        L += ['', '## A/A noise floor (§ 4.3): each arm against its repeat on g3', '',
              'Expected all-pairs rate 0.5.', '',
              '| Generator | Arm | Domain | n dec. | Wins | Ties | Rate | Wilson 95 % | All-pairs |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        for gen, per in rep['aa'].items():
            for arm, doms in per.items():
                for d, v in doms.items():
                    L.append('| ' + ' | '.join([gen, arm, d, *_stat_cells(v['stats'])]) + ' |')
    return '\n'.join(L) + '\n'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Q-E1's pre-registered analysis (Q-02 stage 2)")
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('report', help='the verdict report from a spec of inputs')
    r.add_argument('--spec', required=True, help='YAML listing the inputs (see the docstring)')
    r.add_argument('--out', default=str(DEFAULT_OUT),
                   help='directory for qe1_analysis.json and .md')
    args = ap.parse_args(argv)
    spec_path = _resolve(args.spec)
    spec = yaml.safe_load(spec_path.read_text()) or {}
    rep = analyse(spec)
    rep['spec'] = {'path': str(spec_path), 'sha256': _sha_file(spec_path)}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'qe1_analysis.json').write_text(json.dumps(_round(rep), indent=2) + '\n')
    md = markdown(rep)
    (out / 'qe1_analysis.md').write_text(md)
    print(md)
    print(f'Wrote {out / "qe1_analysis.json"} and {out / "qe1_analysis.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
