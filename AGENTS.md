# AGENTS.md

Guidance for agent sessions working in this repo. Read this first, then
`journal/S-005.md` (Handoff section) for the current state of the world and
the next move, `journal/plan-2026-10-18-approved.md` for the approved roadmap
v2 (its Part 2 supersedes the phases in `journal/PLAN.md`; ticket O-01
rewrites PLAN.md from it), and `journal/tickets/README.md` for the ticket
format. One ticket per session; each ticket's front-matter names the model
and effort to run it with. This file is the *operating* reference; the plan
is the *what/why*.

## What this repo is

`reasoning_sub_agents` is a document pipeline: a `TaskOrchestrator` runs
**decompose → execute → compose → render**. A `Document` (a list of `Part`s +
a rolling summary + an op log) is the unit of state. All LLM calls go through
a single instrumentation seam at `chat.completions.create`, so the client must
stay a stock `OpenAI` instance (instructor does an `isinstance` check at
`llama_utils.py:259`). Part ops form a discriminated union on `type`;
`apply_operations` is atomic (works on a clone).

Phases, in order: **0** (document flexibility + baseline) → **A** (ContextStore
keystone, zero new services) → **P ∥ B** (execution model ∥ ingest+graph) →
**T** (packs) → **C** (chat memory) / **H** (harness-as-tool). See PLAN.md →
*Sequencing summary*.

## Environment (do not re-discover)

- Working dir: `/workspace`.
- **Python:** `.venv/bin/python` (built by `make venv`; Python 3.12 — see
  `pyproject.toml`) if present, else `dsh-podman-venv/bin/python` (no
  interpreter in the agent container). `/workspace/venv` is off-limits —
  never touch or import from it.
- **LLM endpoint has no default (D-P):** `export
  LLM_BASE_URL=http://host.containers.internal:5000/v1` before any harness
  run or `create_llama_client()` call.
- **Model server:** `http://host.containers.internal:5000/v1`, model
  `Qwen3.8-27B-UD-Q6_K.gguf`, no auth, **5 parallel slots**.
  `LLMConfig`'s default port is **8000** — always pass `port=5000` explicitly
  or calls hit nothing. Per-request `max_tokens` is honored.
- The agent itself runs on this same server. Harness/benchmark runs and the
  agent's own LLM calls share the 5 slots, so **a run's wall-clock times are
  contaminated whenever the agent is also calling the model**. Run harness
  jobs only in a genuinely idle window, and if the agent was active during a
  run, treat its wall times as inflated (op counts, part shapes, token counts
  stay clean). A contaminated time ⇒ rerun for the timing gate.
- **Harness parallelism:** `harness.py --jobs N` runs scenarios concurrently
  (ThreadPool; per-turn call attribution and token counts are *approximate*
  — per-turn stats slice a global call counter and can include calls from
  concurrent turns, until ticket 0-14 lands exact attribution — and per-call
  `wall_seconds` inflate under concurrent load). **Default is 3** (the 5 slots must leave room for the agent); 4 is
  the practical max. **Always use `--jobs 1` for timing-gate measurements**
  (P0-4 / `compare.py` A/B / anything gating wall time).
- Git identity is repo-local: `DSH Agent (ubuntu) <dsh-agent@localhost>`.
- Approval policy is "ask"; file sandbox is `workspace-write` on `/workspace`.

## Journaling process (the meta-memory)

The journal is *about the process*; it lives in `journal/`. There is no tracker
server — files plus `git log` are the audit trail. The main reader of any
document is the **next agent session**, which reads files, not UIs.

### Three artifacts

1. **`journal/PLAN.md`** — the plan. Its *pass criteria* (single-digit IDs:
   `P0-3`, `A-1`, `P-P1`, …) **are** the acceptance criteria. There is no
   parallel criteria list.
2. **`journal/tickets/<id>.md`** — one file per work item, instantiated from
   PLAN.md when a phase starts. ID scheme `<phase>-<NN>` (e.g. `0-03`, `A-01`,
   `P-02`) — **distinct** from the single-digit pass-criterion IDs, which are
   referenced in the front-matter `criteria:` field. A ticket without a
   `criteria:` entry is not a ticket.
3. **`journal/S-NNN.md`** — one session wrap-up per working session, started
   from `journal/SESSION_TEMPLATE.md`, written **at session end, before
   closing** — not retroactively.

### Ticket rules

- **Status changes are commits.** A `status:` flip with no code/context change
  in the same or an adjacent commit is noise. Ticket IDs in commit messages
  are the audit trail.
- **A ticket is `done` only when every `criteria:` passes** (or an S-entry
  records an explicit, decided waiver). "Code written" is `in_progress` at best.
- **Retire loudly:** when a ticket completes, confirm its `supersedes:` entries
  were actually deleted/renamed in the same commit.

### Session wrap-up (S-NNN) skeleton

Fixed skeleton, not freeform: phase/tickets touched → what went right → what
went wrong → pain points and how they were solved → decisions made (worthwhile
ones get promoted into PLAN.md's *Settled decisions*) → measurements vs. pass
criteria → **handoff** (exact state of world + next 2–3 moves).

- **Supersede rule:** every entry names which stale state docs it supersedes or
  retires. One session must not leave another session's state doc unretired.
- The eventual **AAR is mechanical synthesis**: all S-entries + pass-criterion
  outcomes + `git log`. No new writing.

### Graduation triggers (do not re-litigate until one fires)

(a) two humans executing in parallel needing shared workflow state, or
(b) ~30–50 active items where grep-on-markdown demonstrably hurts. If
graduating, in order of fit: Gitea/Forgejo on existing git infra → Redmine →
Plane.

## Commit discipline

- **Explicit paths only. Never `git add -A`.** The working tree has untracked
  junk (`docs/`, `main.bak.py`, `*.txt`, `.dsh/`, …) that must stay excluded.
- `.gitignore` is unusual: blanket `*.json` and `*.md` are **ignored**, with
  explicit un-ignores (`!README.md`, `!journal/**/*.md`,
  `!journal/baseline/runs/*.json`). `.dsh/` stays ignored. Add new
  journal/run files with explicit paths; they will not be picked up
  automatically.
- Commit journal and code **together** when a status flip is involved, so the
  audit trail reads as one change.
- Run the test suite before committing behavior changes
  (`make test`); a green suite
  (`… passed … skipped … 0 failed`) is the bar.

## Locked plan decisions (do not reopen without a new session decision)

- No Neo4j initially; MCP is retired (oobabooga extension only).
- Chat memory is on the rolling summary, not a separate store (Phase C, low
  priority).
- DAG is **conservative-biased** (emit the edge when unsure) with **serial
  recovery**, not blind parallel.
- `VerifierSpec` is layered.
- Phase A is zero new runtime deps and zero new services; BM25 retrieval
  replaces the literal substring search and deletes the first-8-parts fallback.
- The 0-06 consolidation pass: merge/move/delete only, outline + previews
  input (never bodies), gate ≤ 1.5× compose p50 and ≤ 25% token growth.

## Baseline denominators (S-002, pre-consolidation)

These are the denominators for gates P0-4, A-6, P-P5, T-4. Treat per-run token
comparisons as distributions (prompt-token variance across identical
scenarios is 36K–305K), not points.

- s4 anchors: wall 497.0 / 514.8 s; tokens/turn 55.8K / 46.1K.
- Compose call p50 ≈ 13–18 s. Decompose+critique pair is the latency hog
  (40–97 s/call). Executor turns 34–96 s each.
- Baseline run files are git-tracked under `journal/baseline/runs/`.

## Self-reference

I am the model behind `:5000` (Qwen3.8-27B) — fast and high-performing,
comparable to the big model. Never describe myself as "small". Devstral-123B is
the big model.