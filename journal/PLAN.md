# PLAN — knowledge-grounded, long-horizon reasoning harness (v2)

The *what* and *why*: goal, phases, scope, and the pass criteria that are the
acceptance criteria. v2 was written by ticket O-01 (2026-10-19) from the
approved roadmap (`archive/plan-2026-10-18-approved.md`, S-004, which also
holds the analysis behind it). v1 is `archive/2026-10-13-PLAN-v1.md`.

Elsewhere, not here:
- Decisions: `DECISIONS.md`.
- How sessions work: `../AGENTS.md`.
- Ticket format and rules: `tickets/README.md`.
- Live state: `INDEX.md` and `make board`.

## Goal and north star

The goal:
- Ingest large corpora (arXiv, Wikipedia, libraries of books) into a knowledge base.
- Run long jobs over that base: analyse papers, write books, continue a series, write code.
- Raise LLM output quality even over very long tasks.

The north star (D-001): **the model never loads a corpus; it explores one
through a bounded interface.** Active context stays small and always
in-prompt: the request, the current sub-task, the document outline and the
rolling summary. Everything else is on-demand retrieval through tools the
model chooses to call. The corpus is unbounded and the window bounded, with
more stores behind the oracle's one door.

## Principles

1. **Validate interfaces in days, against what exists.** `ContextStore` is
   proven against `Document` alone, and V proves it against a 20-paper
   store, before any heavy backend exists.
2. **Every phase is gated on cost, and from Q on also on quality** (D-007).
   Cost is marginal and measured on uncontaminated runs, and the baseline is
   re-recorded when prompts change materially.
3. **Scale by tiers.** Bounded corpora first, and every tier step carries a
   10× scaling test.
4. **Detection must trigger recovery** (D-009). Verdicts carry confidence
   tiers (D-010).
5. **Server hours are the throughput limit.** One 5-slot server is shared
   with the agent. Timing gates need an idle box, and long campaigns get
   scheduled.
6. **Parallel streams only on disjoint files.** One task per session.

## Phase map

```
O (organise) ─► 0-close-A (measure/bookkeep) ─► Q-01 (judge, offline) ∥ A (keystone) ─► V (vertical slice, papers-lite)
   ─► R-mech ∥ B (papers, tier 1) ─► T-science ─► T-book (with R-quality) ─► later: B2 adapters (wiki/books/code), B3 write side, B4 scale tiers
0-close-B (defects) and Q-02 (server campaign): slotted when the server is idle.   P (execution model): deferrable.   C, H: after A, as capacity allows.
```

Critical paths:
- Paper analysis: O → 0-close-A → A → V → B(papers) → T-science.
- Books: … → R-mech → B2(books) → T-book.

"Parallel" means one stream's unattended work (ingest, campaigns) overlaps
the other's coding.

Tickets are instantiated when their phase starts. Instantiated so far: O,
0-close-A/B, Q and A. For those, the ticket front-matter is the source of
truth (`make board`). The board at the end of this file covers the rest.

---

## Phase O — Organisation (zero behaviour change, no server)

O-04 bookkeeping → O-03 reproducible env + endpoint truth → O-02 archive,
delete, `.gitignore` → O-01 journal restructure → O-05 README.

- **O-1 Cold start:** a cold session's first message states six facts:
  - the phase
  - the active ticket
  - the next command
  - the server URL and model
  - the interpreter
  - the last pushed commit

  It must have opened ≤ 3 files to do so, listed in its S-entry.
- **O-2 Clean root:** `git ls-files | cut -d/ -f1 | sort -u` equals
  {`.gitignore`, `AGENTS.md`, `Makefile`, `README.md`, `conftest.py`,
  `journal`, `oobabooga_extension`, `orchestrator.yaml`, `pyproject.toml`,
  `reasoning_sub_agents`, `requirements.txt`, `scripts`, `tests`}.
  `git status --porcelain --ignored`, minus the whitelisted local dirs, is
  empty after `make venv && make test`.
- **O-3 Env:** a fresh `.venv` gives 186 passed / ≤ 10 skipped / 0 failed,
  or the exact diff is recorded in O-03. It is never silently skipped.
  Python 3.12 per D-012.
- **O-4 Single-sourced process:** `grep -l 'Status changes are commit[s]'
  AGENTS.md journal/PLAN.md journal/tickets/README.md` returns exactly one
  file. Every `D-nnn` cited anywhere exists in `DECISIONS.md`
  (`make board` lints this).
- **O-5 Archive complete:** every path in O-02's lists appears in
  `archive/README.md`. No `.gitignore` line matches `^\*\.(md|json)$`.
  `git check-ignore journal/baseline/runs/probe.json` exits 1.
- **O-6 Bookkeeping:** `git ls-files journal/baseline/runs | wc -l` = 9.
  S-003 exists with `reconstructed: true`. Every open ticket's front-matter
  has `criteria`, `model`, `effort`, `needs_server` and `depends_on`
  (`make board` lints this).
- **O-7 README runs:** every command `README.md` gives exists and runs as
  written. Added at instantiation in S-004.
- **O-8 Live schemas:** every `response_model` the pipeline passes to
  instructor builds under the pinned version
  (`tests/test_llama_utils/test_response_model_schemas.py`), and the README
  smoke command completes on a non-llama-server endpoint via `LLM_MODEL`.
  Added in S-007 (O-06).

## Phase 0 — Document flexibility (0-01…0-09) and close-out

Done:
- 0-01: broken imports.
- 0-02: optional titles.
- 0-03: `merge_parts`.
- 0-04: composer ops + dedupe rule.
- 0-05: file parts for code.
- 0-07: integrity tests.
- 0-08: `Document.from_dict`.

Open:
- 0-06: consolidation pass.
- 0-09: double-fenced file parts.

The close-out exists because the Phase 0 measurements are not yet trustworthy:
- Call labels are wrong (N13).
- Attribution is approximate at `--jobs > 1` (N14).
- Streamed calls carry no usage (N15).
- The S-002 token baseline is stale by 3–5× (N18).

**0-close-A — measurement and bookkeeping.** Tickets 0-14 → 0-16 → 0-06,
0-09, plus 0-11.
- 0-14 makes the harness truthful:
  - phase labels come from the orchestrator ContextVar;
  - per-turn attribution is exact;
  - streamed usage is recorded;
  - real executor statuses are recorded;
  - `check.py` gets the three missing P0 checks;
  - `compare.py` gets the marginal G2 and an exit 2 on contaminated input.
- 0-15 makes model thinking explicit and logged (D-013), so the baseline
  records which setting it measured.
- 0-16 re-baselines s1–s4 at `--jobs 1` and attributes the token growth.
- Then 0-06 and 0-09 are re-measured.
- 0-11 repairs the oobabooga extension (N1, N12).

**0-close-B — defects**, slotted between other work:
- 0-10a skips the critique call whose text is ignored.
- 0-10b makes the critique drive regeneration (N2; after Q-01).
- 0-12 covers N4 partial status, N7 history copies and N3 integrity coverage.
- 0-13 covers N9 instructor-path coverage.

(0-15 is unallocated.)

Pass criteria. The IDs are unchanged (no renumbering); P0-6…P0-9 were added
by O-01 for the close-out tickets, and P0-4's text was revised per D-007.
- **P0-1 Shape:** "write a CLI tool that does X" gives a final `Document`
  with ≥ 1 `file` part of runnable code and zero prose-report parts *about*
  the tool. Three different X; pass = 3/3.
- **P0-2 Shape:** "write a report on Y" gives sectioned markdown with no
  `file` parts.
- **P0-3 Dedupe** (revised by D-014; was "puts `merge_parts` or a patch in
  the op log"): a deliberately overlapping follow-up that edits an artifact
  keeps the prior turn's parts. None is dropped unless `merge_parts` folds
  it into a part that survives; updates, patches, moves, new parts and
  deleted scratch parts are all fine. In the final document no two parts
  share > 50% of body tokens (`n/a` with fewer than two parts).
- **P0-4 Consolidation cost** (revised by D-007; was "turn totals B vs A"):
  - On an uncontaminated `--jobs 1` run, the consolidate call's p50 ≤ 1.5×
    the compose p50 from the same run.
  - Marginal tokens (the consolidate call plus the summary call it triggers)
    ≤ 25% of the turn total.
- **P0-5 Regression:** the golden-fixture parser tests (truncated JSON, junk
  meta-shapes through the `llama_utils.py` repair logic) are all green.
- **P0-6 Measurement truth (0-14):**
  - Every call in a fresh run carries a phase label, and the labels sum to
    the call total.
  - Per-turn call and token counts are exact at `--jobs 3`, proved by a test
    with a fake client.
  - Streamed calls carry usage.
  - Executor statuses are real.
  - `check.py` asserts P0-1/P0-2/P0-3.
  - `compare.py` computes the marginal G2 and exits 2 on `jobs > 1` or a
    compose p50 > 1.3× the recorded clean baseline.
  - Re-scoring the tracked runs reproduces S-002's compose, consolidate and
    decompose verdicts.
- **P0-10 Thinking explicit and logged (0-15, D-013):**
  - Every call, in all three `llama_utils.py` call paths, carries the thinking
    switch from config, proved by a fake-client test at the seam.
  - Reasoning text is captured from `reasoning`, `reasoning_content` and a
    leading `<think>…</think>` (stripped before JSON parse). Tests cover each
    one.
  - Reasoning never appears in any prompt, the summary or the Document. A
    test asserts this with thinking `on`.
  - Harness run files carry the setting, per-call and per-kind
    `reasoning_tokens`, and capped excerpts; the full text lands in
    `/runs/thinking/`.
  - Live check on `:8091`: an s1 smoke with `off` has 0 reasoning tokens; with
    `on` it has more than 0, the side log has entries, and the run completes.
- **P0-7 Fresh baseline (0-16):**
  - s1–s4 × 2 at `--jobs 1` in an idle window, every run accepted by
    `compare.py`'s contamination check.
  - New denominators (wall, compose p50, prompt/completion tokens per turn
    per scenario) in `AGENTS.md` § Baseline and in `INDEX.md`.
  - The prompt-token growth since S-002 attributed by call kind, with a
    fix-or-accept decision appended to `DECISIONS.md`.
- **P0-8 Defects closed with evidence:**
  - Every N-defect a ticket names gets a test that fails on the pre-fix code
    and passes after. For a coverage defect (N9), the test exercises the
    uncovered path.
  - A behavioural defect also needs a run file showing it fixed. For 0-09
    that is an s1 run where `check.py`'s "file part bodies not pre-fenced"
    passes; for 0-11, the user confirms in the UI that the extension loads
    and answers.
- **P0-9 Decomposer cost and quality:**
  - 0-10a: critique calls drop to 0 on turns with ≥ 3 sub-tasks, and the
    sub-task-count distribution over s1–s4 is unchanged.
  - 0-10b: decompose-pair p50 and the sub-task-count distribution are
    recorded, a simple request yields 1 sub-task, and G3 (Q-3) against
    0-10a is ≥ 0.45.

## Phase Q — Quality evaluation (∥ A; Q-01 needs no server)

- **Q-01, the judge tool:**
  - `journal/baseline/quality.py` plus `rubrics/`.
  - `judge.base_url` and a reachability check come first.
  - Pairwise with position swap; ties count 0.5; an absolute rubric is
    secondary.
  - Reports win-rate with a Wilson 95% CI.
  - Validated offline on pairs cut from the tracked run files.
  - Open question for the user at the start: Devstral-123B as judge beside
    Qwen, run sequentially, or accept self-judging. If self-judging is
    used, the caveat goes to DECISIONS.
- **Q-02, experiment Q-E1 (harness vs single call):**
  - Three arms with the same prompt, model and `max_tokens`:
    (a) single call, (b) harness, (c) harness + consolidation.
  - ≥ 10 prompts × 2 domains.
  - Win-rate + CI per pairing, with tokens and wall time per arm beside
    quality.
  - A scheduled campaign. `--jobs 3` is acceptable, since outputs and tokens
    stay clean. It answers the README's open question, whatever the answer is.
- **Q-03, the G3 gate in `compare.py`:** needs n ≥ 10 pairs. Win-rate
  ≥ 0.45 passes, < 0.35 fails, and anything between is inconclusive.

Pass criteria:
- **Q-1:** the judge agrees with 5 user-labelled real pairs ≥ 4/5. It also
  picks the correct side of 5 plausible-but-wrong pairs (missing requested
  section; off-by-one in code) ≥ 4/5, in both orders.
- **Q-2:** Q-E1 is recorded with tokens and wall time per arm.
- **Q-3:** G3 is exercised on the Q-E1 set.
- **Q-4:** a judge budget is recorded ("10-pair set ≤ N tokens / ≤ M min"),
  and judge calls never run inside a timing-gate window.
- **Q-5:** repeatability. The same pair in the same order, judged twice,
  agrees ≥ 90%.

## Phase A — `ContextStore` keystone (zero new deps or services; D-001)

- **A-01, interface on paper:**
  - `ContextStore{store_id, list(filters), read(id, start, end),
    search(query, k, filters) -> list[Hit], ask(question, k), summary(id)}`.
  - `Hit{store_id, doc_id, chunk_id, title, span, score, text, provenance}`.
  - A write-side method is reserved (D-004), declared but not implemented.
  - The conflict policy:
    - working memory outranks corpus for current-task questions;
    - cross-store conflicts are annotated, never silently resolved;
    - every citation carries a store id.
- **A-02:** `Document` becomes the first store.
  - A hand-rolled BM25 replaces substring search.
  - The first-8-parts fallback is deleted.
  - This fixes N5.
- **A-03:** a `ToolRegistry` (name → schema + handler) replaces the tool set
  that is closed in three places (the `oracle/tools.py` union,
  `DocumentOracle._run`, the type hints). The oracle takes a set of stores
  with a `store` param.
- **A-04:**
  - Op-log entries get `seq`/`ts`.
  - Snapshot/rehydrate moves out of `harness.py` into
    `reasoning_sub_agents/document/`, for R and Q-02.
- **A-05:** the live criteria run.

Pass criteria:
- **A-1 Citation honesty:** `ask` over a > 30-part document returns citations
  that all exist and all contain the cited content, with no first-8
  artefacts. Ten questions, five of them answered in the last third. Pass
  = 10/10.
- **A-2 Rank quality:** for 10 planted needles, the containing part is in the
  top 3 for ≥ 8/10.
- **A-3 No regression vs substring:** on the same needles BM25 recalls a
  strict superset of what the substring search did.
- **A-4 Interface stability:** the `ContextStore` protocol type-checks
  against `Document` without adapter hacks, and every interface method is
  exercised by a live call in A-1/A-2.
- **A-5 Zero new runtime dependencies and zero new services.** If either
  appears, the phase has grown into B and is re-split.
- **A-6 Latency:** `search`/`ask` wall time on a 30-part document is within
  10% of the baseline oracle calls (P0-7 denominators).
- **A-7 One place per tool:** adding a tool touches one place; a test
  registers a dummy tool and the executor calls it.
- **A-8 Persistence groundwork:**
  - Op-log entries carry a monotonic `seq` and a `ts`.
  - A run's `Document` snapshot → rehydrate round-trip is lossless.
  - The harness uses the promoted functions.
- **A-9 Interface dry-run:** the A-01 design note walks the interface through
  five store kinds (document, papers, books, code, notes/chat). Per method
  it records "fits" or the change made. The user approves it before A-02
  starts.

## Phase V — Vertical slice, papers-lite (D-005)

- A script fetches ~20 arXiv papers on one topic into `corpora/papers-lite/`
  (ignored), using the LaTeX source where available and PDF text otherwise.
- Papers are chunked by section into an SQLite FTS5 store that implements
  `ContextStore`. No dense index, no graph, no embedding service.
- Two tasks run through the existing pipeline: "summarise paper X" and
  "compare papers X, Y, Z on question Q", with citations (store/doc/chunk
  ids). Q-01 judges the results.

Pass criteria:
- **V-1:** `search(store=papers)` returns `Hit`s with provenance, and `ask`'s
  citations resolve to real chunks 10/10.
- **V-2:** 20-needle recall@10 ≥ 0.8 with FTS5 alone.
- **V-3:** the compare task's citations resolve ≥ 90%, and the judge scores
  ≥ 3.5/5 on a 4-criterion rubric in 2/3 runs.
- **V-4:** per-query p50 ≤ 0.5 s; cost per turn is recorded.

## Phase R — Durable runs (D-006). R-mech now; R-quality lives in T-book (T-6)

Mechanics are tested against a recorded or fake client, plus one live
2-milestone smoke.
- Run persistence under `/runs/<run_id>/`:
  - a manifest with request, pack, config, status and budgets;
  - a `Document` snapshot after every compose;
  - an op log with `seq`/`ts`;
  - sub-task results, so `body_source` ops replay;
  - `plan.json`;
  - an event log.
- The two-level milestone loop, with budgets for milestones, sub-tasks per
  milestone and tokens per run.
- Pause-for-user: `review` milestones put the run in `awaiting_input`.
- A `jobs` CLI: `start | status | resume | cancel | export | log` (D-002).
- An in-run notes scratchpad (canon, facts, decisions) that packs fill and
  executors query.

Pass criteria:
- **R-1:** SIGKILL after milestone k, then `resume`, completes the run with
  an identical op-log prefix and no milestone re-executed. Tested with a
  fake client in seconds, plus one live 2-milestone smoke.
- **R-2:** an edited milestone title appears in the resumed event log, and a
  removed milestone never executes.
- **R-3:** a checkpoint write takes ≤ 200 ms per compose at 100 parts; the
  snapshot is ≤ 2× the rendered size.
- **R-4:** a scripted CLI smoke gets the expected exit codes; `status` shows
  milestone i/N and tokens.
- **R-5:** `status: budget_exhausted`; `export` yields all completed
  milestones; manifest tokens ≥ budget.
- **R-6, tier 0:** 3 chapters in 1 run. Given a planted contradiction, a
  `replace_in_part`/`merge_parts` op targets the earlier chapter.

## Phase B — Corpus framework, `papers` adapter, tier 1 (D-003, D-004)

Ingest runs unattended while R-mech is coded.
- **B-01, the framework** (`reasoning_sub_agents/context/`):
  - `Corpus`;
  - `Chunk{chunk_id, doc_id, corpus_id, ordinal, text, span, heading_path,
    metadata}`;
  - `Edge{src, dst, type, weight}`;
  - FTS5 lexical retrieval (from V);
  - batch, resumable, incremental ingest (per-document state, content-hash
    dedupe);
  - cost accounting.
- **B-02, the dense backend and embedding service,** chosen by a 1 M-chunk
  benchmark on the real box:
  - backends: Qdrant vs LanceDB vs sqlite-vec;
  - embedding: llama.cpp `--embedding` vs a CPU process.
- **B-03, hybrid retrieval:** RRF of BM25 + dense, optional rerank, and
  citation-graph expansion of 1–2 hops.
- **B-04, the `papers` adapter at tier 1:** one arXiv category × one year,
  ~10–20 K papers.
  - Metadata plus LaTeX-first full text, split into sections.
  - References become citation edges.

Pass criteria:
- **B-1:** kill mid-ingest, then resume: zero duplicate chunks and all docs
  present (hash check).
- **B-2:** on the papers 20-needle set, hybrid recall@10 is ≥ 0.8 and
  ≥ max(lexical, dense). Graph expansion rescues ≥ 3/20.
- **B-3:**
  - Tier 1 ingests unattended.
  - At 10× (tier 1 vs V), p50 ≤ 2× and recall stays within 10%.
  - Single-query p50 ≤ 2 s.
- **B-4:** one door. A-4 is re-checked with the full store behind it.
- **B-5:** a cost profile per corpus is in the journal.

Later phases, instantiated when reached:
- **B2:** wiki, books and code adapters. Code is the original v1 B: tree-sitter
  plus a call/import graph, with v1's structural-recall criteria.
- **B3:** the KB write side (D-004), with a round-trip criterion.
- **B4:** scale tiers 2–4 (Simple English Wikipedia → full Wikipedia → full
  arXiv), gated on measured throughput.

## Phase P — Execution model (deferrable; D-009)

Design detail is in v1 § Phase P. Steps:
1. Code tools are registered through A's `ToolRegistry`.
2. `depends_on` and sub-task ids are added; the decompose prompt carries the
   conservative-bias rule.
3. Frontiers run in a bounded pool with `copy_context` against a frozen
   `Document.clone()` snapshot. Compose stays serial and has an explicit
   duty to reconcile overlapping siblings.
4. Serial recovery: a flagged sub-task is re-run with its siblings' outputs.
5. The legacy `previous_results` chain is retired, together with N10's
   broken synthesiser and its 10 skipped tests.

Pass criteria:
- **P-P1:** a two-branch DAG (A → {B, C} → D) overlaps for real: frontier
  wall ≤ 0.75× the sum of B and C run sequentially.
- **P-P2:** no executor mid-frontier sees a part created after the frontier
  started. Asserted via op-log `seq`/`ts`.
- **P-P3:** when both siblings produce near-duplicates, the final document has
  a merged part and no duplicate (the P0-3 > 50% shared-token check).
- **P-P4:** with a missing edge (B needs A's output), the verifier flags B and
  B is re-run serially with A's output in context. The *recovered* result
  is correct.
- **P-P5:** a degenerate 1-node DAG costs ≤ 10% more turn latency than the
  baseline.
- **P-P6:** 20 random decompositions all order topologically; an injected
  cycle is rejected with a clear error, not a hang.

## Phase T — Packs: code prover → science → book (D-010)

The pack API extends `config/registry.py` (`pack:` in `OrchestratorConfig`,
`extra='forbid'`). It covers prompt overrides, tool set, stores, verifiers and
output shape. The `DomainPack`/`VerifierSpec` sketch is in v1 § Phase T.
- **T-code** is the prover: corpus-less first (CLI scenarios plus a run/test
  verifier); the B2-code store comes later.
- **T-science** works over the `papers` store:
  - summarise;
  - claim/method/result cards (in the run scratchpad until B3);
  - compare N papers;
  - literature review.

  Its verifier is a claim-vs-retrieved-passage judge plus objective citation
  resolution.
- **T-book:**
  - the `books` adapter (B2);
  - canon notes;
  - a consistency verifier that emits revision ops on earlier chapters;
  - series continuation = the R loop plus the canon store.
- **legal:** a config-only existence proof.

Pass criteria:
- **T-1:** code pack end-to-end. Three different features in a small repo:
  the produced code imports and runs 3/3. With B2-code, it also uses ≥ 1
  structurally retrieved neighbour in 2/3 runs.
- **T-2:** book and legal packs load as pure config against `VerifierSpec`,
  with no core code changes.
- **T-3:** every verdict in a run log carries its confidence tier and, at
  judge tier, its evidence. An unverifiable claim yields an annotation, not
  a silent pass or a hard block.
- **T-4:** verifiers add ≤ 30% to code-pack turn latency vs the Phase P
  baseline.
- **T-5:** science. From 5 papers, ≥ 90% of the claim-card citations resolve
  to the right passage. A 3-paper comparison scores ≥ 3.5/5 from the judge.
- **T-6:** book. Continue a 3-chapter seed with ingested canon: 0
  contradictions on a 10-item checklist in 2/3 runs, and ≥ 1 revision op on
  an earlier chapter from a later milestone.

## Phases C and H

**H, faces (D-002).** The oobabooga harness-as-tool trigger uses three
mechanisms:
- a heuristic pre-filter (`agent_detect.py`);
- native tool calling (`deep_reason(prompt, session_id)` first; `retrieve`
  only once B exists);
- the `[[USE-DEEP-REASONING]]` text sentinel as a universal backstop.

H also covers the `jobs` CLI from R and per-chat extension state (N19).

**C, chat memory (D-011):** chat turns become a B2 adapter.

Pass criteria:
- **H-1:** a scripted 20-turn conversation, 10 trivial and 10 complex turns.
  The harness fires on ≥ 8/10 complex and ≤ 2/10 trivial. Every
  non-heuristic decision is made by the model's tool call or by the sentinel.
- **H-2:** a native `deep_reason` call runs the harness, feeds the result back,
  and the model's continuation uses it, 3/3 (judge).
- **H-3:** the sentinel path alone gets the same ≥ 8/10 on the complex turns.
- **H-4:** a trivial turn costs ≤ 1 extra model pass.
- **C-1:** a fact planted in turn N and asked for ≥ 10 turns later is
  retrieved and cited in 3/3 runs.
- **C-2:** over a 20-turn continuation, the rolling summary holds the 3 active
  threads and no stale ones, 3/3 (judge).
- **C-3:** last-6 behaviour still works as the fallback when the store is
  empty or errors.

## Cross-cutting

- Live smoke runs (`make smoke`) before closing a behavioural ticket, plus
  the golden-fixture parser tests.
- A strict-mode flag for the `ExecutorTurn` validator (`_flatten_qwen_shape`
  rescues junk silently): it logs the raw payload at warning level. The value
  is visibility, not crashes. Unscheduled.
- Every new pass (consolidation, expansion, verifiers, recovery retries)
  reports its marginal cost (D-007).

## Defect register (approved plan § 1.3, re-checked by O-01)

| # | Defect | Where | Owner |
| --- | --- | --- | --- |
| N1 | oobabooga extension imports the moved `reasoning_sub_agents.chat_adapter`; `setup()` swallows the error and disables itself | `oobabooga_extension/script.py:83, :416` | 0-11 |
| N2 | Self-critique: `should_regenerate` is `< 3 tasks`, the critique text is ignored, `DECISION_PROMPT_TEMPLATE` is dead | `self_critique_decomposition.py:158-177` | 0-10a, 0-10b |
| N3 | A compose batch of only replace/merge/move/delete passes `assert_payload_kept` unconditionally | `document/integrity.py:13-61` | 0-12 |
| N4 | Budget-exhausted executor returns `COMPLETED` with "Partial result…" | `oracle_loop_executor.py:211-231` | 0-12 |
| N5 | Oracle `search` offset: computed on `title+'\n'+body`, sliced on `body` | `document_oracle.py:91-95, 177-185` | A-02 |
| N6 | Silent endpoint defaults | — | fixed, O-03 (D-008) |
| N7 | Orchestrator `history` stores component histories by reference | `task_orchestrator.py:158-167` | 0-12 |
| N8 | `consolidate()` sends outline + summary only, but docs said "previews" | `document_composer.py:357-390` | 0-06 |
| N9 | `MockOpenAI` is not an `OpenAI` → instructor path untested | `tests/mock_openai.py` | 0-13 |
| N10 | `RollingDocumentUpdateSynthesiser` broken and unregistered; 10 skipped tests | `document_modification_synthesiser.py` | P (legacy chain) |
| N11 | PLAN v1 defect table stale | — | fixed, O-01 (v1 archived) |
| N12 | Extension passes the whole rendered prompt as the user message; clean text stashed, never read | `oobabooga_extension/script.py:350, :424` | 0-11 |
| N13 | Harness `classify_call` mislabels by system-prompt keyword | `journal/baseline/harness.py` | fixed, 0-14 (phase labels; keywords are the fallback) |
| N14 | `--jobs > 1` attribution approximate | `journal/baseline/harness.py` | fixed, 0-14 (turn ContextVar) |
| N15 | Streamed calls record no token usage | `journal/baseline/harness.py` | fixed, 0-14 (`include_usage`) |
| N16 | `exec_status_counts` always `{'None': n}` | `journal/baseline/harness.py` | fixed, 0-14 |
| N17 | `check.py` lacks the P0-1/P0-2/P0-3 checks; Jaccard trivially 0 on 1-part docs | `journal/baseline/check.py` | fixed, 0-14 |
| N20 | Model thinking never set or captured: runs take the server default, reasoning is discarded unseen | `reasoning_sub_agents/llama_utils.py` | fixed, 0-15 (D-013, D-015) |
| N18 | Prompt tokens per turn grew 3–5× after 0-04/0-05, ungated | run files `20261015T18…`, `…19…` | 0-16 |
| N19 | Extension: in-memory Documents, one shared orchestrator, unbounded history, global `_pending_turn` | `oobabooga_extension/script.py` | R / H |

Line numbers are as of S-004. Re-check them before editing.

## Sizing (one task per session)

| Phase | Tickets | Sessions | Server |
| --- | --- | --- | --- |
| O | 5 | 2.5–3.5 | none |
| 0-close-A | 5 | ≈ 1.5 | ≈ 2 h idle (0-16, 0-06, 0-09) |
| 0-close-B | 4 | ≈ 2 | behavioural only |
| Q | 3 | 3–4 | Q-02 campaign: 60 turns ≈ 10–17 h at `--jobs 1` |
| A | 5 | ≈ 3 | A-05 behavioural |
| V | 3 | ≈ 2 | short |
| R-mech | 4 | ≈ 3 | one smoke |
| B (papers, tier 1) | 4 | weeks; ingest unattended | embedding + benchmark |
| T-science | 3–4 | weeks | campaign |

Phases O through A take ≈ 20 sessions. The first user-visible job (V) lands
at ≈ 25.

## Task board for tickets not yet instantiated

Model and effort rules:
- **Fable 5.1** only where reasoning depth decides the outcome: interface and
  loop designs, and re-plans. Never to implement a spec'd ticket.
- **Opus 5.5** is the default implementer:
  - `medium` for a fully specified ticket;
  - `high` for diagnosis, prompt or behaviour work, concurrency, or library
    internals;
  - `xhigh` only for P-02.
- **Sonnet 5.5** for run-and-record (`low`) and checklist edits (`medium`).
- No Haiku: every ticket ends in journal writing and commits.
- A ticket with distinct stages (design / implement / run / analyse) runs
  one stage per session.

| Ticket | Model / effort | Planning | Note |
| --- | --- | --- | --- |
| V-01 fetch / parse / FTS5 store | Opus 5.5 / medium | short | LaTeX/PDF parsing choices |
| V-02 tasks through the pipeline | prompts Opus / medium → runs Sonnet / medium | — | |
| V-03 judge + write-up | Opus 5.5 / medium | — | |
| R-01 run model design | Fable 5.1 / high | yes | persistence layout, milestone semantics, replay |
| R-02 persistence + resume | Opus 5.5 / high | — | |
| R-03 milestone loop + planner prompt | Opus 5.5 / high | — | |
| R-04 `jobs` CLI, fake-client tests, smoke | Opus 5.5 / medium | — | |
| B-01 corpus framework | Fable / high → Opus / high | yes | |
| B-02 backend + embedding benchmark | Sonnet / medium → Opus / medium | — | the user chooses; DECISIONS records it |
| B-03 hybrid retrieval + citation graph | Opus 5.5 / high | — | |
| B-04 papers adapter, tier 1 | Opus / high → ingest Sonnet / low | — | |
| T pack API | Fable / high → Opus / high | yes | T-2 depends on it |
| T-code prover | Opus 5.5 / medium | — | |
| T-science | Opus 5.5 / high | — | reuses Q-01's judge |
| T-book | Fable / high → Opus / high | yes | the hardest verifier |
| P-01 DAG schema + conservative-bias prompt | Opus 5.5 / high | — | |
| P-02 frontier, snapshot, concurrency | Opus 5.5 / xhigh | short | the only concurrency-correctness ticket |
| P-03 serial recovery | Opus 5.5 / high | — | |
| P-04 retire legacy chain | Sonnet 5.5 / low | — | |
