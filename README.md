# Multi-step reasoning

A library that turns one user prompt into several sub-tasks, runs them
separately, and folds the results into a `Document`. Each turn runs
**decompose → execute → compose → render**. Later sub-tasks do not get the
full document. They get an outline, a rolling summary and a `DocumentOracle`
they can query (`list_parts`, `read_part`, `search`, `ask`).

The `Document` is revisable working memory. Earlier parts are not set in
stone: the composer can patch them as later sub-tasks complete, so the model
can revise its answer before presenting it. The north star is *corpus
unbounded, window bounded*: long jobs over more material than fits in one
context window. What, why and the pass criteria are in
[`journal/PLAN.md`](journal/PLAN.md).

## Layout

| Path | Role |
| --- | --- |
| `reasoning_sub_agents/` | Library: decompose → execute → compose → render |
| `oobabooga_extension/` | oobabooga chat face (`script.py`, `chat_adapter.py`, `orchestrator.yaml`) |
| `tests/` | Unit tests (no live model required) |
| `journal/` | Plan, decisions, tickets, session notes, `baseline/` harness and runs, `archive/` |
| `scripts/server/` | Launchers for the host-side Devstral-123B server |
| `orchestrator.yaml` | Which components to wire (see Configuration) |

## Quickstart

```bash
make venv && make test
export LLM_BASE_URL=http://host.containers.internal:5000/v1
.venv/bin/python journal/baseline/harness.py --smoke --base-url http://host.containers.internal:5000/v1
```

`--base-url` defaults to `$LLM_BASE_URL`. `make venv` needs Python 3.12 (via
`uv` if present). The smoke run needs a reachable generator. Run files land
in `journal/baseline/runs/` as `<timestamp>_<label>_<scenarios>.json`.

## Configuration

`orchestrator.yaml`:
- `components`:
  - `decomposer`: `simple` | `self_critique`
  - `executor`: `simple` | `oracle_loop`
  - `composer`: `simple` | `document`
  - `oracle`: `document_oracle` | `null`
- `options`: `max_oracle_rounds`, `summary_max_words`, `render`
  (`markdown_with_files` | `sections_only`), `composer_max_retries`,
  `prompt_token_budget`, `log_prompts`.
- `llm`: `host` + `port`, or `base_url`.

Unknown names and incompatible combinations (for example `oracle_loop`
without an oracle) raise at load time.

**Endpoint rule (D-008).** There is no default endpoint. Set `llm.base_url`
(or `host` and `port`) or export `LLM_BASE_URL`, which overrides the block.
With neither, creating the client raises.

**Dependencies.** `pyproject.toml` pins the runtime set (Python 3.12 only).
Extras: `test` (pytest), `tokens` (tiktoken). `requirements.txt` is the
curated runtime list that mirrors it, not a full-machine freeze.

```python
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

orch = TaskOrchestrator.from_yaml('orchestrator.yaml')
print(orch.query('Write a report on X').content)
```

## Faces

- **oobabooga extension:** copy `oobabooga_extension/script.py` and
  `oobabooga_extension/orchestrator.yaml` to the extension root, next to
  `reasoning_sub_agents/`, and install `requirements.txt` into oobabooga's
  environment. **Known broken at startup until ticket 0-11:** N1, the
  `chat_adapter` import path is stale and `setup()` swallows the error; and
  N12, the whole rendered prompt is passed as the user message instead of
  the clean user text.
- **`jobs` CLI:** planned (Phase R), not implemented.

## Journal

Work is tracked in markdown. See [`AGENTS.md`](AGENTS.md) for how sessions
run and [`journal/INDEX.md`](journal/INDEX.md) for the live board. `make
board` prints the ticket table. Ticket rules are in
`journal/tickets/README.md`.

## Status

Phase 0 closing; roadmap v2 approved 2026-10-18 — see
[`journal/PLAN.md`](journal/PLAN.md).
