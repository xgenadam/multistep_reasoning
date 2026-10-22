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
  - The instructor client must be built per request. It is what
    `instructor.from_openai` builds, with `create` wrapped to capture
    reasoning (D-015). A hoisted one binds a stale `create` and bypasses the
    harness's counting (`tests/test_llama_utils/test_instructor_seam.py`).

## Environment (do not re-discover)

- **Working dir:** `/workspace`. Git identity is repo-local: `DSH Agent
  (ubuntu) <dsh-agent@localhost>`. The container cannot push; the user
  pushes from the host.
- **Agent container `claude-box` (from 2026-10-22):** the repo is at
  `/mnt/myraid/workspace/my_projects/multi_step_reasoning_grok`, `~/models`
  is read-write, `~/workspace/AI/Qwen38-Flash-Next-4x3090` holds the user's
  flash-next lane. The four cards are visible (`nvidia-smi`). `docker` is a
  nested rootless podman: pass GPUs with `--device nvidia.com/gpu=all`;
  `--gpus all` is silently ignored. The host answers at
  `host.containers.internal` (`:5000` text-generation-webui; `:8090`/`:8091`
  when the user's generator is up). One process owns the GPUs at a time:
  check `nvidia-smi` (< 1 GB per card) and that the host ports are down
  before any boot. Judges: `scripts/server/judge-llama-server.sh` (llama.cpp
  server-cuda image, `http://localhost:8092/v1`); downloads:
  `scripts/models/hf-queue.sh` (`hf` CLI). The generator can be booted here
  with the flash-next launcher and `GPU_ARGS="--device nvidia.com/gpu=all"`,
  answering at `http://localhost:8090/v1`.
- **Python:**
  - Use `.venv/bin/python` (3.12, D-012; `make venv` builds it), or
    `dsh-podman-venv/bin/python` if `.venv` is absent. The latter has no
    interpreter in the agent container.
  - `/workspace/venv` is off-limits: never touch it or import from it.
  - `make test` runs the suite.
- **Hardware (host, recorded 2026-10-19):** 4 × RTX 3090 (24 GiB each,
  96 GiB VRAM), 128 GiB RAM, EPYC 7542 (32 cores). `:8091`'s Qwen flash
  runs on a vLLM the user customised for this machine (unfinished): it
  takes all four cards (0.3–0.5 GiB free per card) plus 40–50 GiB of RAM
  and gives coding tasks ≈ 125 tok/s. The user may fit it on three cards;
  two is a stretch. A second model co-resides only on cards the generator
  leaves free, pinned (`CUDA_VISIBLE_DEVICES`, llama.cpp `--tensor-split`)
  and with vLLM's `--gpu-memory-utilization` capped. Judge tiers and
  candidates: Q-01 Notes; the judge benchmark is Q-04.
- **Generator** (D-008):
  - Run `export LLM_BASE_URL=http://host.containers.internal:5000/v1`
    before any harness run or `create_llama_client()` call. Nothing
    defaults it.
  - Model `Qwen3.8-27B-UD-Q6_K.gguf`, no auth, **5 parallel slots**.
    Per-request `max_tokens` is honoured.
  - `:5000` is text-generation-webui's OpenAI-compatible API (uvicorn,
    loader llama.cpp), not a bare llama-server. `/v1/internal/model/list`
    lists the host's GGUF files and `/v1/internal/model/info` the loaded
    one (`"None"` on 2026-10-19). `/health`, `/version` and `/metrics`
    404 there; vLLM answers all three.
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
  - Above 1, per-turn call attribution and tokens stay exact (0-14), but
    per-call wall times inflate.
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
  about 2× across identical scenarios (s2 34K / 78K, s4 62K / 30K; 0-16).
  Compare distributions.
- **Run files** go to `journal/baseline/runs/` (tracked). Commit each with a
  dated Notes bullet in its ticket.

### Baseline

0-16 (D-016). Run file
`journal/baseline/runs/20261019T051008Z_rebaseline-0-16_…json`: s1–s4 × 2 at
`--jobs 1`, thinking `off`, on `:8091` (`qwen3.8-flash-next`, vLLM), and every
turn is timing-clean.
- It is not the 27B. `:5000` has no baseline on current code, so re-baseline
  it before gating a `:5000` run.
- The Oct-15 (S-002) token totals are void (D-016).

| Scenario | Wall s r0/r1 | Compose p50 s | Decompose pair s | Executor p50 s | Prompt / turn | Completion / turn |
| --- | --- | --- | --- | --- | --- | --- |
| s1 | 48.5 / 62.3 | 2.12 | 7.9 / 17.1 | 6.00 | 50.8K / 44.8K | 5.4K / 7.1K |
| s1b | 83.3 / 48.9 | 2.12 | 14.8 / 5.5 | 2.44 | 100.0K / 57.0K | 8.1K / 5.0K |
| s1c | 62.3 / 49.7 | 2.07 | 12.9 / 8.8 | 3.32 | 42.9K / 57.2K | 7.0K / 5.1K |
| s2 | 38.0 / 65.9 | 2.24 | 4.6 / 9.4 | 3.60 | 34.4K / 78.3K | 3.3K / 6.5K |
| s3 t0 | 45.1 / 62.7 | 2.23 | 12.1 / 10.4 | 3.61 | 48.7K / 56.6K | 4.1K / 6.3K |
| s3 t1 | 116.3 / 63.7 | 2.33 | 13.5 / 10.6 | 5.31 | 92.7K / 52.4K | 12.8K / 6.5K |
| s4 | 84.0 / 24.1 | 2.46 | 14.3 / 6.8 | 3.41 | 61.9K / 29.6K | 9.2K / 2.4K |

- Pooled over all 14 turns:
  - compose p50 2.23 s, which is `compare.CLEAN_COMPOSE_P50_S` for `:8091`;
  - executor-turn p50 3.36 s;
  - decompose pair p50 10.5 s (decompose + critique + regeneration, summed per
    turn);
  - wall per turn median 62 s;
  - prompt tokens per turn median 55K, completion tokens median 6.4K.
- Prompt tokens by call kind:
  - compose 54 %: about 7K per call for a 92-token median reply;
  - executor 33 %;
  - decompose and critique 9 %;
  - summary 4 %.

  JSON schema text is ≈ 59 % of all prompt tokens, half of it a duplicate
  (N21, after A-05).
- Oracle calls have no denominator (n = 1), so A-05 measures its own.

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
