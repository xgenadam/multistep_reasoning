"""Integration replay (E-1, journal/design/lead-worker.md).

Feeds a traced harness run's recorded sub-task results, in their order, to an
integrator, so only the integration step changes: no planning or execution
calls are made. Each chain (a prompt and its follow-ups) is replayed in order,
so a follow-up starts from its parent's replayed Document.

    .venv/bin/python journal/baseline/integration_replay.py SOURCE_RUN.json --integrator C \
        --base-url http://localhost:8100/v1 --label e1-C [--prompt c13 ...] [--trace-calls]

Integrators:
  C   the source run's own composer and summary step (components and options from
      the run file's config), the control.
  M   the mechanical merge only (no model): see `mechanical_merge`.

Writes journal/baseline/runs/<stamp>_replay-<label>_<generator>.json, one
result per replayed turn with the final Document (scored by hidden_tests.py
as any run file), and intermediates/<that stem>/ as arms.py does. The source
must have been run with the step fields (result, compose_attempts): commit
ba67ae8 or later.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import harness  # noqa: E402
from arms import IntermediateWriter, sha256  # noqa: E402
from harness import REPO_ROOT  # noqa: E402
from openai.types.chat import ChatCompletionMessage  # noqa: E402

from reasoning_sub_agents.config.loader import parse_orchestrator_config  # noqa: E402
from reasoning_sub_agents.document import Document  # noqa: E402
from reasoning_sub_agents.document.summary import update_rolling_summary  # noqa: E402
from reasoning_sub_agents.execution_synthesiser.document_composer import changed_part_ids  # noqa: E402
from reasoning_sub_agents.llama_utils import create_llama_client  # noqa: E402
from reasoning_sub_agents.schemas import DecomposeSubTask, SubTask, SubTaskResult, TaskStatus  # noqa: E402
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator  # noqa: E402

INTEGRATORS = ('C', 'M')


def load_turn(inter_dir: Path) -> dict:
    """The plan and each step's recorded result, from a traced turn's intermediates."""
    plan = json.loads((inter_dir / '01_plan.json').read_text())
    steps = []
    for f in sorted(inter_dir.glob('*.json')):
        data = json.loads(f.read_text())
        if data.get('kind') in ('document', 'compose_failed') and isinstance(data.get('step'), int):
            steps.append(data)
    steps.sort(key=lambda s: s['step'])
    missing = [s['step'] for s in steps if 'result' not in s]
    if missing:
        raise ValueError(f'{inter_dir}: steps {missing} have no recorded result (traced before ba67ae8?)')
    return {'user_input': (plan.get('decomposition_history') or {}).get('user_input'),
            'sub_tasks': plan['sub_tasks'], 'steps': steps}


def build_sub_tasks(turn: dict) -> list[SubTask]:
    """SubTasks with the recorded results; a step that never ran keeps no result."""
    by_name = {s['sub_task']: s for s in turn['steps']}
    tasks = []
    for st in turn['sub_tasks']:
        task = SubTask(meta_type='sub_task', decomposed_sub_task=DecomposeSubTask.model_validate(st))
        step = by_name.get(st['name'])
        if step is not None:
            task.sub_task_result = SubTaskResult(chat_response=ChatCompletionMessage(
                role='assistant', content=step['result']))
            task.status = TaskStatus.FAILED if 'FAILED' in str(step.get('status', '')).upper() else TaskStatus.COMPLETED
        tasks.append(task)
    return tasks


def mechanical_merge(*args, **kwargs):  # build step 2
    raise NotImplementedError('the mechanical merge is build step 2')


class ComposerIntegrator:
    """C: the source run's composer and rolling-summary step, rebuilt from its config."""

    def __init__(self, config, client):
        self.config = config
        self.client = client

    def new_turn(self):
        orch = TaskOrchestrator.from_orchestrator_config(self.config, llm_client=self.client)
        self.composer = orch.document_composer
        self.oracle_factory = orch.oracle_factory
        self.oracle = None

    def integrate(self, user_input, sub_tasks, sub_task, document, step):
        if self.oracle is None and self.oracle_factory is not None:
            self.oracle = self.oracle_factory(document)
        harness._current_phase.set(f"Composing after {step['step']}/{step['of']}: {step['sub_task']}")
        attempts_from = len(self.composer.history)
        ops = self.composer.compose(user_request=user_input, sub_tasks=sub_tasks,
                                    current_sub_task=sub_task, document=document)
        changed = changed_part_ids(ops)
        harness._current_phase.set(f"Updating summary after {step['step']}/{step['of']}: {step['sub_task']}")
        if self.oracle is not None:
            self.oracle.update_summary(changed)
        else:
            update_rolling_summary(document, changed, self.client,
                                   max_words=self.config.options.summary_max_words,
                                   prompt_token_budget=self.config.options.prompt_token_budget)
        return self.composer.history[attempts_from:]


def chains_of(results: list[dict]) -> dict[tuple, list[dict]]:
    """(root prompt, run) -> the chain's results in order."""
    chains: dict[tuple, list[dict]] = defaultdict(list)
    for r in results:
        chains[(r['chain'][0], r['run'])].append(r)
    for key, rs in chains.items():
        order = rs[0]['chain']
        rs.sort(key=lambda r: order.index(r['prompt_id']))
    return chains


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source')
    ap.add_argument('--integrator', choices=INTEGRATORS, required=True)
    ap.add_argument('--base-url', default=None, help='the generator, for integrators that call a model')
    ap.add_argument('--label', required=True)
    ap.add_argument('--prompt', action='append', default=None)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--max-tokens', type=int, default=None)
    ap.add_argument('--trace-calls', action='store_true')
    ap.add_argument('--out', default=str(REPO_ROOT / 'journal/baseline/runs'))
    ap.add_argument('--intermediates', default=str(REPO_ROOT / 'intermediates'))
    args = ap.parse_args(argv)

    source_path = Path(args.source).resolve()
    source = json.loads(source_path.read_text())
    if args.max_tokens:
        harness.MAX_TOKENS = args.max_tokens
    elif source.get('max_tokens'):
        harness.MAX_TOKENS = source['max_tokens']
    config = parse_orchestrator_config({**source['config'], 'llm': {}})
    client = measured = None
    if args.integrator != 'M':
        if not args.base_url:
            raise SystemExit(f'--integrator {args.integrator} calls a model: give --base-url')
        client = create_llama_client(base_url=args.base_url)
        measured = harness.install_instrumentation(client)

    results_in = [r for r in source['results'] if not args.prompt or r['prompt_id'] in args.prompt]
    chains = chains_of(results_in)
    started = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out_path = Path(args.out) / f"{started}_replay-{args.label}_{source['generator']}.json"
    writer = IntermediateWriter(Path(args.intermediates) / out_path.stem)
    if measured is not None and args.trace_calls:
        measured.trace = writer.call
    rows: list[dict] = []
    lock = threading.Lock()

    def run_chain(key, chain):
        document = Document.empty(render_mode=config.options.render)
        integrator = ComposerIntegrator(config, client) if args.integrator == 'C' else None
        for r in chain:
            turn_id = f"replay-{args.label}:{r['prompt_id']}#r{r['run']}"
            token = harness._current_turn.set(turn_id)
            t0 = time.time()
            row = {'prompt_id': r['prompt_id'], 'arm': r['arm'], 'run': r['run'], 'chain': r['chain'],
                   'follows': r.get('follows'), 'domain': r.get('domain'), 'stratum': r.get('stratum'),
                   'source_turn': (r.get('intermediates') or {}).get('dir'), 'source_error': r.get('error'),
                   'error': None, 'steps': []}
            try:
                turn = load_turn(Path(r['intermediates']['dir']))
                sub_tasks = build_sub_tasks(turn)
                by_name = {t.decomposed_sub_task.name: t for t in sub_tasks}
                if integrator is not None:
                    integrator.new_turn()
                for step in turn['steps']:
                    attempts = (integrator.integrate(turn['user_input'], sub_tasks, by_name[step['sub_task']], document, step)
                                if integrator is not None else mechanical_merge(document, by_name[step['sub_task']], step))
                    writer('document', {'step': step['step'], 'of': step['of'], 'sub_task': step['sub_task'],
                                        'status': step.get('status'), 'result': step['result'],
                                        'compose_attempts': attempts, 'snapshot': document.to_dict()})
                    row['steps'].append({'step': step['step'], 'attempts': len(attempts or [])})
            except Exception as exc:  # noqa: BLE001 - a failed replay is a row
                row['error'] = repr(exc)
            finally:
                harness._current_turn.reset(token)
            row['wall_seconds'] = round(time.time() - t0, 1)
            row['output'] = {'text': document.render(), 'snapshot': document.to_dict(), 'chars': len(document.render())}
            row['intermediates'] = {'dir': str(writer.root / harness_turn_dir(turn_id))}
            if measured is not None:
                row['llm'] = harness.llm_stats(measured.records_for_turn(turn_id))
            with lock:
                rows.append(row)
                print(f"{r['prompt_id']} r{r['run']}: {len(row['steps'])} steps"
                      f"{' ERROR ' + row['error'][:100] if row['error'] else ''}", flush=True)

    harness.run_jobs(list(chains.items()), lambda i, kv: run_chain(*kv), args.jobs)
    header = {
        'kind': 'replay', 'integrator': args.integrator, 'label': args.label,
        'source': str(source_path.relative_to(REPO_ROOT)) if source_path.is_relative_to(REPO_ROOT) else str(source_path),
        'source_sha256': sha256(source_path.read_text()), 'generator': source['generator'], 'model': source.get('model'),
        'backend': args.base_url, 'bench': source.get('bench'), 'manifest_path': source.get('manifest_path'),
        'manifest_sha256': source.get('manifest_sha256'), 'max_tokens': harness.MAX_TOKENS,
        'config': source['config'], **harness.git_commit(), 'started_at': started, 'jobs': args.jobs,
        'trace_calls': bool(args.trace_calls and measured is not None),
        'results': sorted(rows, key=lambda x: (x['prompt_id'], x['run']))}
    header['intermediates'] = writer.manifest() if writer.root.exists() else None
    out_path.write_text(json.dumps(header, indent=1, default=str))
    print(f'wrote {out_path}')
    return 0


def harness_turn_dir(turn_id: str) -> str:
    from arms import turn_dir_name
    return turn_dir_name(turn_id)


if __name__ == '__main__':
    sys.exit(main())
