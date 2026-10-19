# AGENTS.md

The operating reference for agent sessions in this repo: how to start, work,
measure, commit and finish. Other files hold everything else:
- What and why: `journal/PLAN.md`.
- Decisions: `journal/DECISIONS.md`.
- Ticket rules: `journal/tickets/README.md`.
- Live state: `journal/INDEX.md`.

This file holds no decisions; it cites them by `D-nnn`.

## Session start

1. Read this file, then `journal/INDEX.md`, then the active ticket named in
   INDEX § Now, plus any `D-nnn` the ticket cites.
2. State six facts in the first message (criterion O-1):
   - the phase;
   - the active ticket;
   - the next command;
   - the generator URL and model;
   - the interpreter;
   - the last pushed commit.
3. Run `git status` and `git log --oneline origin/master..master`.
4. If any ticket is `in_progress` with no S-entry covering its last commit,
   write a reconstructed S-entry first (`journal/tickets/README.md` rule 6).
5. Check that the ticket's `model`/`effort` match the session. If they
   don't, say so and record it in the S-entry.

## Session end

1. The ticket's Notes and Measurements are current. Evidence should already
   be committed as it was produced.
2. The ticket's status is flipped if its criteria are met.
3. `journal/INDEX.md` is updated: the `updated:` line, Now, Queue, Resources.
4. `journal/S-NNN.md` is written from `journal/SESSION_TEMPLATE.md` before
   closing, and its Handoff matches INDEX § Now.
5. One commit, explicit paths (see Commits).

## What this repo is

`reasoning_sub_agents` is a document pipeline: a `TaskOrchestrator` runs
**decompose → execute → compose → render**.
- A `Document` is the unit of state: a list of `Part`s, a rolling summary
  and an op log.
- Part ops form a discriminated union on `type`. `apply_operations` is atomic
  (it works on a clone).
- All LLM calls go through one instrumentation seam at
  `chat.completions.create`. Two consequences:
  - The client must stay a stock `OpenAI` instance, because `llama_utils.py`
    only takes the instructor path for `isinstance(client, OpenAI)`.
  - `instructor.from_openai` must be built per request. A hoisted one
    bypasses the harness's counting
    (`tests/test_llama_utils/test_instructor_seam.py`).

## Environment (do not re-discover)

- **Working dir:** `/workspace`. Git identity is repo-local: `DSH Agent
  (ubuntu) <dsh-agent@localhost>`. The container cannot push; the user
  pushes from the host.
- **Python:**
  - Use `.venv/bin/python` (3.12, D-012; `make venv` builds it), or
    `dsh-podman-venv/bin/python` if `.venv` is absent. The latter has no
    interpreter in the agent container.
  - `/workspace/venv` is off-limits: never touch it or import from it.
  - `make test` runs the suite.
- **Generator** (D-008):
  - Run `export LLM_BASE_URL=http://host.containers.internal:5000/v1`
    before any harness run or `create_llama_client()` call. Nothing
    defaults it.
  - Model `Qwen3.8-27B-UD-Q6_K.gguf`, no auth, **5 parallel slots**.
    Per-request `max_tokens` is honoured.
  - Requests send `model='llama'` unless `LLM_MODEL` is set. llama-server
    ignores the name; vLLM 404s on it. On 2026-10-19 the user served
    `qwen3.8-flash-next` (vLLM) at `host.containers.internal:8091/v1`, so
    set `LLM_MODEL=qwen3.8-flash-next` there. `localhost` in the container
    is the container, not the host.
  - The YAMLs' `llm` block names `:8000`, the host-side Devstral-123B (big
    model, future judge, usually down). `LLM_BASE_URL` overrides it.
- **The agent runs on the same server.** Harness runs and the agent's own
  calls share the 5 slots. Run harness jobs in a genuinely idle window, and
  claim the server in INDEX first (`journal/tickets/README.md` rule 7).
- **Harness parallelism** (`harness.py --jobs N`):
  - Scenarios run concurrently in a thread pool. The default is 3 and 4 is
    the practical maximum.
  - Above 1, per-turn call attribution and tokens are *approximate* until
    0-14, and per-call wall times inflate.
- **Sandbox:** approval policy is "ask"; files are `workspace-write` on
  `/workspace`.

## Measurement

- **Contamination rule.** A run's wall times are void if the agent was
  calling the model during the run. Op counts, part shapes and token counts
  stay clean. A void time means a rerun for the timing gate.
- **Timing gates** (P0-4, A-6, P-P5, T-4, anything `compare.py` gates on
  wall time) run with `--jobs 1` on an idle box (`needs_server: timing`).
- **Cost gates are marginal and uncontaminated, and the baseline is
  re-recorded after material prompt changes** (D-007).
- **Token counts are distributions, not points.** Prompt tokens vary
  36K–305K across identical scenarios. Compare distributions.
- **Run files** go to `journal/baseline/runs/` (tracked). Commit each with a
  dated Notes bullet in its ticket.

### Baseline

These are the S-002 numbers (2026-10-15, pre-consolidation). **They are
stale.** Prompt tokens per turn grew 3–5× after 0-04/0-05 (N18), and 0-16
replaces them. Do not gate on them.
- s4 anchors: wall 497.0 / 514.8 s; tokens per turn 55.8K / 46.1K.
- Compose call p50 ≈ 13–18 s.
- The decompose + critique pair takes 40–97 s per call.
- Executor turns take 34–96 s each.

## Commits

- **Explicit paths only. Never `git add -A`.** `.dsh/` holds live agent-tool
  state, credentials included. It stays ignored and is never committed or
  deleted.
- `.gitignore` is a plain list of local dirs and build artefacts, so new
  files show up as untracked. Live run state goes under `/runs/` (ignored,
  root-anchored).
- Commit journal and code **together**, so the audit trail reads as one
  change. Put ticket IDs in the message.
- Commit or push only when asked. Executing a ticket includes its commit.
- Run `make test` before committing behaviour changes. A green suite
  (`… passed … skipped`, 0 failed) is the bar.
- End commit messages with the `Co-Authored-By:` trailer for the model that
  ran the session.

## Journal process

The journal is *about the process*. Its main reader is the next agent
session, which reads files, not UIs.

| File | Role |
| --- | --- |
| `journal/INDEX.md` | Live board: Now, Resources, Queue, Phase status. Hand-maintained, ≤ 40 lines; never repeats a ticket's `status`. |
| `journal/PLAN.md` | Phases, scope, pass criteria. The criteria **are** the acceptance criteria; there is no parallel list. |
| `journal/DECISIONS.md` | Append-only decisions. Superseding means a new entry plus a status-word change on the old one. |
| `journal/tickets/*.md` | One file per work item. Format and rules in `journal/tickets/README.md`. |
| `journal/S-NNN.md` | One wrap-up per session, from `SESSION_TEMPLATE.md`. |
| `journal/archive/` | Dead docs, indexed by `archive/README.md`. Never cited as current. |

- **One task per session.** The ticket's front-matter names the model and
  effort.
- **S-entry skeleton is fixed:**
  1. ticket
  2. what went right
  3. what went wrong
  4. pain points
  5. decisions (load-bearing ones are appended to DECISIONS.md)
  6. measurements vs criteria
  7. superseded docs
  8. handoff
- **Supersede rule:** every S-entry names the stale state docs it retires.
  One session must not leave another session's state doc unretired.
- **The AAR is mechanical synthesis** of all S-entries, the pass-criterion
  outcomes and `git log`. No new writing.
- **Graduation triggers.** Do not re-litigate until one fires:
  - (a) two humans executing in parallel need shared workflow state; or
  - (b) ~30–50 active items, where grep-on-markdown demonstrably hurts.

  If graduating, in order of fit: Gitea/Forgejo on existing git infra →
  Redmine → Plane.

## Self-reference

I am the model behind `:5000` (Qwen3.8-27B): fast, high-performing and
comparable to the big model. Never describe myself as "small". Devstral-123B
is the big model.
