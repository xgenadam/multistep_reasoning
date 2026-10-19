<!-- Approved roadmap v2, 2026-10-18 (session S-004). Copied verbatim from the plan-mode file
     /home/dev/.claude/plans/please-read-the-objective-md-giggly-thacker.md after user approval.
     Ticket O-01 derives journal/PLAN.md v2 from Part 2 of this file and then moves this file to journal/archive/. -->

# Plan: re-organise the journal and re-plan the roadmap toward a knowledge-grounded long-horizon harness

## Context

`reasoning_sub_agents` is a decompose → execute → compose → render harness whose
unit of state is a `Document`. The user's ultimate goal is wider than the current
plan of record (`journal/PLAN.md`, 2026-10-13):

- **ingest vast corpora** (arXiv, Wikipedia, libraries of books) into a knowledge base,
- **task the harness with long-running jobs** over that base: analyse scientific
  papers, write books, write the next book in an existing series, and code,
- all in service of one aim: **raise LLM output quality, even over very long tasks**.

Phase 0 of the current plan is nearly closed (0-01..0-05, 0-07, 0-08 done; 0-06 and
0-09 in progress). The process (plan + tickets + session wrap-ups) worked for one
session and then frayed: the last session ended without a wrap-up, its A/B runs are
untracked and unrecorded, and four generations of planning docs coexist in the tree.
The user asked for (1) an analysis of `OBJECTIVE.md`, the current plan and progress,
(2) improvements, and (3) a multi-step plan, with **organisation as step 1**.

Decisions the user took during planning (2026-10-18): vector backend deferred to
Phase B; first full pack = science / paper analysis; README refreshed; stale docs
archived then deleted. This plan was produced in plan mode: nothing has been executed.

---

## Part 1 — Analysis

### 1.1 What exists (verified in this session)

| Area | State |
| --- | --- |
| Pipeline | Works end-to-end on the 27B model via `TaskOrchestrator`; one instrumentation seam at `chat.completions.create`; ops form a discriminated union, `apply_operations` is atomic. |
| Phase 0 | 0-01..0-05, 0-07, 0-08 **done**; 0-06 consolidation **in_progress** — the A/B ran 15 Oct and both gates fail on paper (G1 2.01× vs 1.5×, G2 +41.5% vs 25%), but **both runs are contaminated** (control compose p50 30.6 s vs the clean 13–18 s although `jobs=1`; the agent was active) and n=1 per arm → inconclusive; 0-09 prompt fix landed, awaiting an s1 spot re-run. |
| Tests | 198 `def test_` (196 real tests) across 20 modules; last recorded suite 186 passed / 10 skipped / 0 failed. **Cannot run in this sandbox**: `dsh-podman-venv/` points at a missing `/usr/bin/python3.12`; only Python 3.13 exists, with no deps. |
| Environment | `uv` at `/usr/local/bin/uv`; PyPI reachable. Model server answers at `http://host.containers.internal:5000` only (lists no model right now); `127.0.0.1:5000` — which `create_llama_client()` and the harness actually use — is refused here; `:8000` (Devstral) is down. No push credentials in this container; `master` is 10 commits ahead of `origin/master`. |
| Measurement | `journal/baseline/{harness,check,compare,replay,scenarios}.py` — latency/tokens/shape/dedupe gates. No quality measurement of any kind. |
| Process | `AGENTS.md` (operating) + `journal/PLAN.md` (what/why, 585 lines, includes a now-stale "current state" audit and a process section) + `journal/tickets/*.md` + `journal/S-00{1,2}.md`. Rules duplicated across three files. No live status board. |
| Repo hygiene | `.gitignore` blanket-ignores `*.md`/`*.json` with un-ignores for the journal. Untracked: `docs/` (Feb journal attempt: `LOG.md`, `TODO.md`, empty `OBJECTIVE.md`/`CURRENT_STATUS.md`, `notespace/`), root pile `ANALYSIS.md`, `CRITICAL.md`, `CRITICAL_ANALYSIS.md`, `TODO.md`, `TODO_ANALYSIS.md`, `TODO_CORRECTNESS_CONFIRMATION.md`, `SYNTHESISER_STATUS_ANALYSIS.md` (Jan–May AI-generated audits, superseded), `README_NEW.md` (byte-identical to README), `intermediate_output.md`, `output_2{3,4,5}.md`, `project_text.txt(.bak)`, `resume_grok.txt`, `test_output.txt`, `parallel_test_agent2.txt`, `main.bak.py`, `requirements.txt.bak`, `start_llama.sh`, `history/` (138 MB), `results/`, `llama_cpp_server/` (77 MB), `.idea/`. Tracked but dead: `mcp_server/`, `llama_server.py`, `project_serializer.py`, `config.json`. `requirements.txt` is a 164-line machine freeze; the venv holds ~15 real packages (openai 1.109, instructor 1.3.2, pydantic 2.14, pyyaml, pytest, httpx, …). Seven local branches, five with unmerged commits. |
| Uncommitted | `harness.py --jobs` default 1→3 + a caveat that wrongly claims exact attribution; matching AGENTS.md paragraph; two A/B run JSONs. |

### 1.2 Verdict on `OBJECTIVE.md` and `journal/PLAN.md`

**Keep (it is good):** the north star ("the model never loads a corpus — it explores
one through a bounded interface"; corpus unbounded, window bounded); the `Document`
as working memory with a revision capability; `ContextStore` as the single door;
packs as config bundles; layered `VerifierSpec` with confidence-tiered verdicts;
cost gates on every phase; the "validate the keystone in days against `Document`
alone" rule; tickets-as-files with pass criteria as the only acceptance criteria.

**Where it falls short of the stated goal:**

1. **Corpus ingestion is code-only.** Phase B = tree-sitter + call graph. Papers,
   wiki pages and books need a general framework (parse → structure-aware chunks →
   lexical + dense index → typed graph edges) with per-source adapters; the graph
   generalises (call graph ↔ citation graph ↔ link graph ↔ canon/entity graph).
2. **Scale is unaddressed.** "Vast swathes" needs resumable, incremental, sharded
   ingest, an embedding service, and scale *tiers* with a 10× scaling test. Full
   Wikipedia ≈ 20–30 M chunks; full arXiv ≈ 100 M+. A local box shared with a 27B/123B
   generator cannot embed that in days on CPU; the plan must start with bounded
   tiers and prove the design scales.
3. **No durable, long-horizon run.** One turn lives in memory; no checkpoint/resume,
   no milestone loop, no pause-for-user (the `DecompositionPause` schemas exist,
   unimplemented since Feb). A book or a 200-paper review is hours to days of calls.
4. **Quality is never measured.** Gates cover latency, tokens, shape, dedupe. The
   README's own central question ("does this harness improve responses?") has no
   measurement; the settled decision "big model for quality evaluation" has no
   tooling. Every later phase claims a quality gain nobody can check.
5. **Knowledge base is read-only.** Packs will *produce* knowledge (canon facts,
   paper claim cards, summaries) that should be stored with provenance and retrieved
   later; the plan has no write side.
6. **Recursion rejected, but flat decomposition will not reach book scale.** A
   bounded *two-level* loop (plan/outline → milestones, each milestone = one pipeline
   turn against shared stores) gives the reach without the budget instability that
   motivated the non-goal.
7. **Deployment face.** oobabooga-only is the wrong driver for multi-hour jobs; a
   headless `jobs` CLI (the baseline harness is already half of one) is needed anyway
   and keeps `reasoning_sub_agents` platform-agnostic (the README's own complaint).
8. **The first user-visible job is too far away.** As sequenced, paper analysis
   waits for the whole corpus framework; a thin vertical slice after the keystone
   gives value and tests the interface months earlier.

**Process findings (the "disorganised" feeling, concretely):**

- No single live status file; a new session reads S-002 § Handoff + nine ticket
  front-matters to learn the state. The user's other project converged on
  `journal/INDEX.md` (live board + next task + resource owner) and a task board with
  model/effort per task; this repo should match that pattern.
- Session wrap-up is end-of-session only; when a session dies early (as the last one
  did) its evidence is lost. Ticket Notes/Measurements and INDEX must be updated
  *as work happens*; the S-entry becomes short.
- Process rules live in three files (PLAN.md § Process is a near-verbatim copy of
  AGENTS.md § Journaling); PLAN.md mixes roadmap, stale audit, settled decisions,
  process. Settled decisions have no dates/supersession → "locked" decisions cannot
  be re-opened cleanly (this session re-opens several).
- Ticket IDs `0-03` vs criterion IDs `P0-3` are confusing but renumbering would
  churn every cross-reference for cosmetics; the confusion dies with Phase 0.
- `.gitignore` inverted (ignore-all + un-ignore) guarantees future docs get lost.
- Environment is not reproducible (machine-freeze requirements, venv built in
  another container, three different endpoint defaults).
- Server hours — one 5-slot server shared with the agent, timing gates needing an
  idle box — are the real throughput limiter, and nothing in the process names it.

### 1.3 Code-level findings that shape the roadmap (from the code survey)

Seams that exist and should be reused:
- `TaskOrchestrator(…, oracle_factory=…)` (`task_orchestrator.py:40-67`) — the clean door for retrieval; `iter_query` yields `('status', str)` / `('done', result)`; `on_progress`, `live_session` (`progress.py`).
- `Document.clone()` (`document/models.py:59-66`) is cheap and edits always replace `Part`s → usable as a frozen snapshot; `to_dict`/`from_dict` exist → the basis for run persistence.
- Single instrumentation seam `chat.completions.create` (harness wrapper `journal/baseline/harness.py:123-210`); it only works because `instructor.from_openai` is called per request (`llama_utils.py:260`).
- `config/registry.py` `REGISTRY` + `ComponentSpec{provides, requires, forbids, factory}` — the shape a pack registration API can extend.
- `prompt_budget.py` (`fit_pieces`, `budgeted_prompt`, `cap_prompt`).

Hard facts that constrain design:
- **No retrieval code exists** (zero hits for bm25/embedding/qdrant/sqlite/networkx/tree_sitter/ContextStore). Phase A is greenfield.
- **No DAG / `depends_on` / sub-task id** — tasks are identified by `name` only (collisions possible).
- **Tool set is closed in three places** (`oracle/tools.py` union, `DocumentOracle._run`, concrete type hints); `SearchHit` has no store id or score.
- **Op log has no timestamps/sequence ids/turn ids** and cannot be replayed for `body_source` ops (P-P2 assumes timestamps).
- **Config is thin**: 4 component names + 7 options; unknown YAML keys silently dropped (`extra='ignore'`); all prompts are constants → "pack = config bundle" needs a registration API + prompt injection points.
- `run_multi_concurrent` uses bare threads, no `copy_context`, no slot limit; `LiveState`/history lists are unsynchronised.
- Port 8000 in `LLMConfig`/both YAMLs/`config.json`/`start_llama.sh` describes the **host-side Devstral-123B** server; 5000 in `create_llama_client` is the **container-side Qwen-27B**. Neither is "stale"; the defect is the silent defaulting.

Defects found (new, not in PLAN.md's table) — become tickets:

| # | Defect | Where |
| --- | --- | --- |
| N1 | **oobabooga extension broken at startup**: imports `reasoning_sub_agents.chat_adapter` (moved to `oobabooga_extension/` in 9c4fce5); `setup()` swallows the ImportError and disables itself | `oobabooga_extension/script.py:83, :416` |
| N2 | Self-critique decomposer: `should_regenerate` is deterministic (`< 3 tasks`), critique text ignored, `DECISION_PROMPT_TEMPLATE` dead; conflicts with "1 sub-task for simple requests" → always regenerates simple requests | `self_critique_decomposition.py:158-177` |
| N3 | Integrity loophole: a compose batch of only replace/merge/move/delete passes `assert_payload_kept` unconditionally → result can be silently dropped | `document/integrity.py:13-61` |
| N4 | Budget-exhausted executor returns status COMPLETED with "Partial result…" text → verifiers cannot trust `status` | `oracle_loop_executor.py:211-231` |
| N5 | Oracle `search` offset bug: index computed on `title+'\n'+body`, sliced on `body` → excerpt misses the needle for long titles | `document_oracle.py:91-95, 177-185` |
| N6 | Silent endpoint defaults (8000 vs 5000); harness label says `host.containers.internal:5000` but connects to 127.0.0.1:5000 — refused from this container | `config/schema.py:6-8`, `llama_utils.py:101-104`, `harness.py:52,403,406` |
| N7 | Orchestrator `history` stores component histories by reference → earlier turns mutate in a long-lived orchestrator | `task_orchestrator.py:158-167` |
| N8 | `consolidate()` sends outline+summary only; code comment, 0-06 ticket and AGENTS.md's locked decision say "previews" | `document_composer.py:357-390` |
| N9 | `MockOpenAI` is not an `OpenAI` instance → the instructor path (the one production uses) has no test coverage | `tests/mock_openai.py` |
| N10 | `RollingDocumentUpdateSynthesiser` is broken (`TypeError`, unbound var), unregistered; 10 tests skipped — delete with the legacy chain | `document_modification_synthesiser.py:134-135, :153` |
| N11 | PLAN.md defect table stale: D1/D2/D3/D5/D8 fixed; D9 names the wrong branch; line refs drifted | `journal/PLAN.md:53-64` |
| N12 | Extension passes the **whole rendered prompt** (character context + history + template) to the orchestrator as the user message (`user_text = question`); the clean text is stashed but never read; `chat_adapter.py` prompt regexes are dead | `oobabooga_extension/script.py:424, :350`; `chat_adapter.py:13-40` |
| N13 | Harness `classify_call` mislabels: executor rounds → `summary` (their system prompt contains "rolling summary"); real summary updates and the critique → `system_other`; `executor_turn`/`decompose_critique`/`oracle` never occur. Per-kind stats quoted in S-002 are wrong except `compose`/`consolidate`/`decompose` | `journal/baseline/harness.py:69-106` |
| N14 | `--jobs > 1` attribution is **not** exact (per-turn stats slice a global call counter); the *uncommitted* caveat text and AGENTS.md paragraph claim "exact" — the committed wording was right | `harness.py:140-142, 335-363, 453-455`; `AGENTS.md:38-43` (working tree) |
| N15 | Streamed calls record no token usage → critique + summary updates are excluded from token totals; G2 undercounts | `harness.py:226-239` |
| N16 | `exec_status_counts` is always `{'None': n}`; `budget_exhausted` never surfaces in run files | `harness.py:283-300` |
| N17 | `check.py` does not check P0-1 "no prose parts", P0-2 "no file parts", P0-3 "op log has merge/patch"; Jaccard is trivially 0 on single-part documents | `journal/baseline/check.py:36-74` |
| N18 | **Token-cost regression, ungated:** post-0-04/0-05 runs use 265–432 K prompt tokens per turn (s1 425 K, s2 349 K, s3 398/432 K, s4 265/379 K) vs a pre-change median ≈ 80 K (36–308 K). 3–5× cost increase from the Phase 0 prompt changes; P0-4 only gated consolidation B-vs-A, so the "+25% vs baseline" clause was blown unnoticed and every later token gate (A-6, P-P5, T-4) is anchored to a pipeline that no longer exists | run files `20261015T18…`, `…19…` vs `…143545Z` |
| N19 | Extension state: Documents in memory only, one orchestrator shared by all chats with unbounded `history`; single global `_pending_turn` stash (interleaved chats race) | `script.py:43, 342-369, 441-446` |

---

## Part 2 — Roadmap (recommended approach)

### 2.0 Decisions taken in this planning session → `journal/DECISIONS.md` (each names what it supersedes)

| ID | Decision | Supersedes |
| --- | --- | --- |
| D-A | Vector backend **deferred to Phase B** (chosen at B-02 by a benchmark on the real box). Lexical side = SQLite FTS5 (stdlib). | "Server-based Qdrant or Chroma" |
| D-B | First full pack + corpus = **science / paper analysis**. `code` stays the small contract prover. | "code first, then book/legal/science" |
| D-C | `README.md` is refreshed; its narrative sections move verbatim to `journal/archive/`. | — |
| D-D | Stale docs **archived into git then deleted**; byte-junk (`history/`, `results/`, outputs) deleted unarchived (never in git). **The user pushes `master` from the host before anything is deleted** (no push credentials here). | — |
| D-E | **Quality is a gated metric** (judge, pairwise, n ≥ 10) beside latency/tokens. | cost-only gates |
| D-F | New **Phase R (durable runs)**: every run persists and resumes; a bounded **two-level milestone loop**. Not recursive self-decomposition (that non-goal stands). | — |
| D-G | Faces are thin: oobabooga extension (chat) + `jobs` CLI (long runs). MCP stays retired. | "oobabooga extension only" |
| D-H | Phase B = **corpus framework + adapters**, scoped to the `papers` adapter at tier 1 first; wiki/books/code adapters, tiers 2–4 and the write side are later phases with their own gates. | "tree-sitter + call graph" |
| D-I | The KB gets a **write side** (derived notes with provenance; notes never outrank sources) — a later phase; the interface slot is reserved in A. | read-only KB |
| D-J | **Keep** the existing ID schemes (tickets `<phase>-<NN>`; criteria `P0-3`/`A-1`/`P-P1` style). No renumbering. | — |
| D-K | **One task per session**; tickets carry `model`, `effort`, `needs_server`; "one active ticket per executor" becomes a rule. | "a norm, not a law" |
| D-L | A session that finds an `in_progress` ticket without a matching S-entry writes a `reconstructed: true` wrap-up from git + run files **before** new work. | "written at session end — not retroactively" (still the normal path) |
| D-M | **Vertical slice (Phase V)** right after A: ~20 arXiv papers, FTS5 only, "summarise + compare" through the existing pipeline. | — |
| D-N | Consolidation input = outline + summary (what the code does), **no previews** unless 0-06's re-measure shows they are needed; decided before re-measuring. | locked "outline + previews" |
| D-O | Cost gates measure **marginal** cost (the pass under test + the calls it triggers) ÷ turn total; `compare.py` refuses contaminated inputs; **re-baseline whenever prompts change materially**. | B-vs-A turn totals |
| D-P | **No silent LLM endpoint default**: `base_url` comes from env / CLI / YAML; run files record the real endpoint. 8000 = host-side Devstral config (kept), 5000 = container-side Qwen. | ambiguous defaults |
| D-Q | **No package-rename commit** in Phase A (it breaks the extension's import path and every test import for no A value); `context/` is added beside the existing layout. | PLAN.md Phase A item 1 |

### 2.1 Revised phase map

```
O (organise) ─► 0-close-A (measure/bookkeep) ─► Q-01 (judge, offline) ∥ A (keystone) ─► V (vertical slice, papers-lite)
   ─► R-mech ∥ B (papers, tier 1) ─► T-science ─► T-book (with R-quality) ─► later: B2 adapters (wiki/books/code), B3 write side, B4 scale tiers
0-close-B (defects) and Q-02 (server campaign): slotted when the server is idle.   P (execution model): deferrable.   C, H: after A, as capacity allows.
```

Critical path, paper analysis: O → 0-close-A → A → V → B(papers) → T-science.
Critical path, books: … → R-mech → B2(books) → T-book.
"Parallel" means one stream's unattended work (ingest, campaigns) overlaps the other's coding; sessions stay one-task.

### 2.2 Phase O — Organisation (step 1; zero behaviour change; ≈ 2.5–3.5 sessions; `needs_server: none`)

Execution order: **human push → O-04 → O-03 → O-02 → O-01 → O-05** (Part 3).

**O-04 Bookkeeping first** (Sonnet, medium)
- Commit the pending `harness.py`/`AGENTS.md` hunk **with the caveat corrected** (N14: attribution is approximate at `--jobs > 1` until 0-14 lands; default stays 3; timing gates already mandate `--jobs 1`).
- Track the two A/B run files. Write `journal/S-003.md` (`reconstructed: true`) covering commits `bffb6f8`, `76a0299` and the lost session: the on-paper A/B result (G1 2.01×, G2 +41.5%), **both runs contaminated** (control compose p50 30.6 s vs clean 13–18 s), n=1, consolidation triggering an extra summary call, the merge that folded Deliverable 1 into the outline, N18.
- 0-06 Measurements: "inconclusive; re-measure after 0-14 + 0-16".

**O-03 Reproducible environment + endpoint truth** (Opus, medium)
- `pyproject.toml`: `requires-python >= 3.12`; deps `openai>=1.109,<2`, `instructor==1.3.*` (what is installed and known-good with the seam; upgrading is its own later ticket), `pydantic>=2`, `pyyaml`; extras `test` (pytest), `tokens` (tiktoken). `requirements.txt` becomes the curated runtime list (README's oobabooga install path); `requirements.txt.bak` deleted.
- `Makefile`: `venv` (`uv venv .venv && uv pip install -e .[test]`), `test`, `smoke` (harness `--smoke`), `check`, `board`. AGENTS.md interpreter rule: `.venv/bin/python` if present, else `dsh-podman-venv/bin/python`.
- D-P: `LLMConfig.base_url` (required unless `LLM_BASE_URL` is set); `create_llama_client` without a silent default; harness `--base-url`; the run-file `backend` field comes from the client's real `base_url`. `judge.base_url` placeholder for Q.
- Instructor-seam test: `instructor.from_openai` must be invoked per request so `install_instrumentation`'s replacement of `client.chat.completions` is seen; the test asserts that hoisting it to construction time yields zero measured calls.

**O-02 Archive, delete, `.gitignore`** (Sonnet, medium) — only after the user confirms the push.
- Archive (`mv` + `git add`; these files are ignored, not tracked) into `journal/archive/` with a `README.md` index (origin path, date, why dead): `OBJECTIVE.md`, `docs/LOG.md`, `docs/TODO.md`, `docs/notespace/new_synthesiser_potential_ideas.md`, root `TODO.md`, `TODO_ANALYSIS.md`, `TODO_CORRECTNESS_CONFIRMATION.md`, `CRITICAL.md`, `CRITICAL_ANALYSIS.md`, `ANALYSIS.md`, `SYNTHESISER_STATUS_ANALYSIS.md`, the README narrative. From tracked code: the `deep_reason`/`reset_session` tool schema (`mcp_server/mcp_server.py:138-178`) and `ReasoningSessionStore` (:30-64) as the Phase H reference; `llama_server.py` (needs `requests`, uncalled); `project_serializer.py` (unreferenced). Also the fate of the seven local branches (five unmerged: `multi-stream-llama-client` 6 ahead; `cline-edits`, `open-webui-edits`, `round_2_improvements`, `round_2_redo` 1 each; `cleanup_after_weird_grok_stuff`, `round_3` merged) — recorded for the user to decide, not deleted here.
- Delete: `README_NEW.md`, `intermediate_output.md`, `output_2{3,4,5}.md`, `project_text.txt`, `project_text.txt.bak`, `resume_grok.txt`, `test_output.txt`, `parallel_test_agent2.txt`, `main.bak.py`, all of `docs/` (incl. `docs/notespace/README.md` and the empty `docs/OBJECTIVE.md`, `docs/CURRENT_STATUS.md`), `history/` and `results/` (unarchived — never in git); `git rm -r mcp_server/`; `git rm llama_server.py project_serializer.py` (after archiving).
- `git mv config.json scripts/server/devstral-123b.llama-server.json`; `start_llama.sh` → `scripts/server/start-devstral-123b.sh` (tracked; labelled as the big-model / judge launcher).
- `.gitignore` rewrite, **after the deletes, same commit**: `__pycache__/`, `*.pyc`, `*.egg-info/`, `build/`, `dist/`, `.venv/`, `venv/`, `dsh-podman-venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.idea/`, `.dsh/`, `llama_cpp_server/`, `/runs/` (anchored — an unanchored `runs/` would ignore `journal/baseline/runs/`), `corpora/`. No `*.md` / `*.json` lines. Verify with `git status --porcelain --ignored`.
- Leave alone: `.dsh/` (live agent-tool state), `.idea/`, `llama_cpp_server/`, `venv/`, `dsh-podman-venv/`.

**O-01 Journal restructure** (Opus, high)
- `journal/INDEX.md` (new; ≤ 40 lines; hand-maintained; **never repeats ticket `status`**): `updated: <date> (<commit>)`; **Now** (phase, active ticket, next move as one command); **Resources** (generator URL/model/slots, judge URL or "down", interpreter path, last pushed commit vs `origin/master`, server owner); **Queue** (open ticket ids in execution order: `id — title — model/effort — needs_server — depends_on`); **Phase status** (one line per phase); **Pointers**. The status board is generated: `make board` runs `journal/board.py` over ticket front-matter.
- `journal/DECISIONS.md` (new; append-only; ≤ 12 load-bearing entries seeded from table 2.0 + the old settled/locked lists; ≤ 4 lines each): `## D-007 — title    2026-10-18 · S-004 · active` / `Decision:` / `Why:` / `Supersedes: D-002 | none    Re-open if: …`. A superseded entry only gets its status word changed.
- `journal/PLAN.md` v2: north star, principles, phase map, per-phase scope + pass criteria (this Part 2, IDs per D-J) + task board. Removed: the stale audit/defect table (archived), the process section (→ AGENTS.md), settled decisions (→ DECISIONS.md).
- `journal/tickets/README.md` v2: front-matter adds `model:`, `effort:`, `needs_server: none | behavioural | timing`, `depends_on:` (static ticket ids; `blocked_on:` stays a live condition), `needs_planning:`, `runs:` (paths produced). Rules: the first commit of a ticket flips `in_progress` + `started:`; evidence lands when produced (run file + dated Notes bullet in the same commit, never at session end); D-L reconstructed entries; INDEX's server-owner line is updated before/after any background harness job; run files live under `journal/baseline/runs/` (tracked), live run state under `/runs/` (ignored); snapshot bodies in run files capped (today 25–525 KB each).
- `journal/SESSION_TEMPLATE.md` v2: shorter; `reconstructed:` field; "runs produced"; "files opened to orient" (feeds O-1).
- `AGENTS.md` rewrite: session-start/end checklists, environment (interpreter rule, endpoints, slots, the contamination rule), measurement rules, commit discipline, process rules. **Zero decision content** (links DECISIONS.md); drop the `.gitignore`-oddity paragraph; keep "explicit paths only".
- Instantiate the 0-close-A/B, Q and A tickets with the new front-matter.

**O-05 README refresh** (Sonnet, medium) — after O-02 archived the narrative: what/why, layout, quickstart (`make venv && make test`, `harness.py --smoke`), config, faces (extension: "known broken until 0-11"), pointer to `journal/`.

**Phase O pass criteria**
- **O-1 Cold start:** the first message of a cold session states phase, active ticket, next command, server URL/model, interpreter, last pushed commit — having opened ≤ 3 files (listed in its S-entry).
- **O-2 Clean root:** `git ls-files | cut -d/ -f1 | sort -u` equals {`.gitignore`, `AGENTS.md`, `Makefile`, `README.md`, `conftest.py`, `journal`, `oobabooga_extension`, `orchestrator.yaml`, `pyproject.toml`, `reasoning_sub_agents`, `requirements.txt`, `scripts`, `tests`}; `git status --porcelain --ignored` minus the whitelisted local dirs is empty **after** `pip install -e .` and `make test`.
- **O-3 Env:** pip reachable → fresh `.venv` (3.13) gives 186 passed / ≤ 10 skipped / 0 failed, or the exact diff is recorded in O-03's ticket; else recorded `deferred (no network/interpreter)` — never silently skipped.
- **O-4 Single-sourced process:** `grep -l 'Status changes are commits' AGENTS.md journal/PLAN.md journal/tickets/README.md` returns exactly one file; every `D-\d{3}` cited anywhere exists in DECISIONS.md.
- **O-5 Archive complete:** every path in O-02's lists appears in `journal/archive/README.md`; no `.gitignore` line matches `^\*\.(md|json)$`; `git check-ignore journal/baseline/runs/probe.json` exits 1.
- **O-6 Bookkeeping:** `git ls-files journal/baseline/runs | wc -l` = 9; S-003 exists with `reconstructed: true`; every open ticket's front-matter has `criteria`, `model`, `effort`, `needs_server`, `depends_on`.

### 2.3 Phase 0 close-out

**0-close-A — measurement & bookkeeping** (≈ 1.5 sessions + ≈ 2 h idle server)

| Ticket | Scope | Model/effort | needs_server |
| --- | --- | --- | --- |
| 0-14 | **Harness truthfulness**: **N13** classify by the orchestrator's phase ContextVar (already set per status event) instead of system-prompt keywords; **N14** exact per-turn attribution via a turn-id ContextVar per scenario thread; **N15** streamed usage (`stream_options={'include_usage': true}`); **N16** executor status incl. partial; **N17** the three missing P0 checks; per-kind `prompt_tokens`/`completion_tokens` sums in `llm_stats`; `compare.py`: **G2 := marginal tokens (consolidate + its summary call) ÷ turn total ≤ 25%** (deterministic at n=1) and **exit 2 "contaminated"** when `jobs > 1` or compose p50 > 1.3× the recorded clean baseline; `base_url` recorded. Verify: re-scored old runs agree with S-002 verdicts; labels sum to total calls. | Opus, medium | none |
| 0-16 | **Re-baseline** (N18, D-O): s1–s4 × 2, `--jobs 1`, idle box, post-0-14 labels → new denominators in AGENTS.md/INDEX (the S-002 anchors are stale by ~6×); attribute the 3–5× prompt-token growth by kind (composer `need_part_ids` fetches? extra oracle rounds? regeneration?) → fix-or-accept recorded in DECISIONS. | Opus, high | timing |
| 0-06 | Decide N8/D-N first; re-measure `--runs 2 --jobs 1` per arm with the marginal G2; keep (default on) only if G1+G2 pass and — once Q-01 exists — the judge finds the s4 merge non-harmful; else code stays, default off, closed with waiver or dropped. | Sonnet, low | timing |
| 0-09 | s1 spot re-run; pre-fence check PASS. | Sonnet, low | behavioural |
| 0-11 | **N1** extension import; **N12** pass the stashed clean user text; import smoke test; the user confirms in the UI. | Sonnet, low | none (+ user's UI) |

**0-close-B — defects** (slotted between other work; ≈ 2 sessions)

| Ticket | Scope | Model/effort | needs_server |
| --- | --- | --- | --- |
| 0-10a | Behaviour-identical cheap win: skip the critique call when `len(sub_tasks) >= 3` (its text is ignored there) — one fewer 40–97 s call per turn. | Sonnet, low | behavioural |
| 0-10b | **N2** critique drives regeneration (revive `DECISION_PROMPT_TEMPLATE`, drop the `< 3` rule, honour "1 sub-task for simple requests"); measured by decompose p50 + sub-task-count distribution and Q's G3. | Opus, high; after Q-01 | behavioural |
| 0-12 | **N4** `TaskStatus.partial`; **N7** history copies; **N3** patch-only compose batches must pass a token-coverage check (≥ 0.8 of the result's distinct content tokens present post-apply) — split out if it fights the composer prompt. | Opus, medium | none |
| 0-13 | **N9** instructor-path coverage (`OpenAI` subclass over `httpx.MockTransport`). Budget one session; if instructor internals fight back, stop and record. | Opus, medium | none |

(N5 dies in A-02's search rewrite; N10 in P; N11 in O-01; N19 in R/H.)

### 2.4 Phase Q — Quality evaluation (∥ A; Q-01 needs no server)

- **Q-01 Judge tool** (design Fable, implement Opus; `needs_planning`; `needs_server: none`): `journal/baseline/quality.py` + `rubrics/`; `judge.base_url` + a reachability check as step one; pairwise with position swap, ties 0.5, absolute rubric secondary; win-rate + Wilson 95% CI; **validated offline on pairs cut from the nine existing run files**. Self-judging caveat (Qwen judging Qwen; `:8000` Devstral is down and may not co-fit beside the 27B) goes into DECISIONS if used. Question for the user at Q-01 start: Devstral as judge beside Qwen, sequentially, or accept self-judging.
- **Q-02 Experiment Q-E1, harness vs single call** (Sonnet run, Opus analysis; `needs_server: behavioural`; a scheduled campaign — `--jobs 3` is acceptable since outputs/tokens stay clean): fixed arms (same prompt, model, `max_tokens`): (a) single call, (b) harness, (c) harness + consolidation; ≥ 10 prompts × 2 domains; win-rate + CI per pairing; **tokens and wall per arm beside quality**. The README's unanswered question, recorded whatever it says.
- **Q-03 G3 gate** in `compare.py` (Sonnet): n ≥ 10 pairs; win-rate ≥ 0.45 pass, < 0.35 fail, between → inconclusive; exercised on Q-E1 (b) vs (c).

Pass criteria: **Q-1** the judge agrees with 5 user-labelled real pairs ≥ 4/5 and picks 5 plausible-but-wrong pairs (missing requested section; off-by-one in code) ≥ 4/5 in both orders; **Q-2** Q-E1 recorded with tokens/wall per arm; **Q-3** G3 exercised on the Q-E1 set; **Q-4** a recorded judge budget ("10-pair set ≤ N tokens / ≤ M min") and judge calls never run inside a timing-gate window; **Q-5** repeatability — same pair, same order, judged twice agrees ≥ 90%.

### 2.5 Phase A — `ContextStore` keystone (≈ 3 sessions; zero new deps/services; no rename commit — D-Q)

- **A-01** interface on paper (Fable; `needs_planning`): `ContextStore{store_id, list(filters), read(id, start, end), search(query, k, filters) -> list[Hit], ask(question, k), summary(id)}`; `Hit{store_id, doc_id, chunk_id, title, span, score, text, provenance}`; conflict policy as PLAN.md (working memory outranks corpus for current-task questions; cross-store conflicts annotated, never silently resolved; every citation carries a store id); a reserved write-side method declared, not implemented.
- **A-02** `Document` as the first store; hand-rolled BM25 (≈ 60 lines) replaces substring search; the first-8 fallback deleted; fixes N5 (Opus).
- **A-03** `ToolRegistry` (name → schema + handler) replacing the closed union in `oracle/tools.py`, `DocumentOracle._run` and the type hints; the oracle takes a set of stores with a `store` param. The big ticket (`tools.py` 125, `document_oracle.py` 185, `oracle_loop_executor.py` 278 lines + tests) (Opus, high). P's tool-set generalisation lands here; P only registers code tools.
- **A-04** op-log `seq`/`ts` **and** promote snapshot/rehydrate out of `harness.py:257-366` into `reasoning_sub_agents/document/` (R-01 and Q-02 both need it) (Sonnet).
- **A-05** live criteria run (Sonnet; `needs_server: behavioural`).

Pass criteria **A-1…A-6** as PLAN.md; **A-7** adding a tool touches one place (a test registers a dummy tool; the executor calls it).

### 2.6 Phase V — Vertical slice, papers-lite (D-M; ≈ 2 sessions + a short server window)

- ~20 arXiv papers on one topic fetched by a script into `corpora/papers-lite/` (ignored); LaTeX source where available, else PDF text; chunked by section into a **SQLite FTS5** store implementing `ContextStore`. No dense index, no graph, no embedding service.
- Through the existing pipeline: "summarise paper X"; "compare papers X, Y, Z on question Q" with citations (store/doc/chunk ids); judged by Q-01.

Pass criteria: **V-1** second store behind the same door — `search(store=papers)` returns `Hit`s with provenance and `ask` citations resolve to real chunks 10/10; **V-2** 20-needle recall@10 ≥ 0.8 with FTS5 alone; **V-3** the compare task's citations resolve ≥ 90% (objective) and the judge scores ≥ 3.5/5 on a 4-criterion rubric in 2/3 runs; **V-4** per-query p50 ≤ 0.5 s; cost per turn recorded.

### 2.7 Phase R — Durable runs (split: mechanics now, quality in T-book)

- **R-mech** (≈ 3 sessions; deterministic against a recorded/fake client plus one live 2-milestone smoke): run persistence under `/runs/<run_id>/` (manifest with request/pack/config/status/budgets; Document snapshot after every compose; op log with `seq`/`ts`; sub-task results so `body_source` ops replay; `plan.json`; event log); the two-level milestone loop (D-F) with explicit budgets (milestones, sub-tasks per milestone, tokens per run); pause-for-user (`review` milestones → `awaiting_input`); `jobs` CLI (`start | status | resume | cancel | export | log`); an in-run notes scratchpad (canon/facts/decisions) packs fill and executors query.
- **R-quality** lives in T-book (T-6).

Pass criteria: **R-1** SIGKILL after milestone k → `resume` completes, op-log prefix identical, no milestone re-executed (fake client, seconds) + one live 2-milestone smoke; **R-2** an edited milestone title appears in the resumed event log and a removed milestone never executes; **R-3** checkpoint write ≤ 200 ms per compose at 100 parts; snapshot ≤ 2× rendered size; **R-4** scripted CLI smoke with expected exit codes; `status` shows milestone i/N and tokens; **R-5** `status: budget_exhausted`, `export` yields all completed milestones, manifest tokens ≥ budget; **R-6** tier-0: 3 chapters, 1 run — given a planted contradiction, a `replace_in_part`/`merge_parts` op targets the earlier chapter.

### 2.8 Phase B — Corpus framework, `papers` adapter, tier 1 (D-H; weeks; ingest runs unattended while R-mech is coded)

- **B-01** framework (`reasoning_sub_agents/context/`): `Corpus`, `Chunk{chunk_id, doc_id, corpus_id, ordinal, text, span, heading_path, metadata}`, `Edge{src, dst, type, weight}`; FTS5 lexical (from V); batch, **resumable, incremental** ingest (per-document state, content-hash dedupe); cost accounting.
- **B-02** dense backend decision (D-A): 1 M-chunk benchmark on the real box (Qdrant vs LanceDB vs sqlite-vec) and an embedding service chosen by measured throughput (llama.cpp `--embedding` with a small GGUF vs a CPU process).
- **B-03** hybrid retrieval (RRF of BM25 + dense) + optional rerank + citation-graph 1–2-hop expansion.
- **B-04** `papers` adapter at **tier 1** (one arXiv category × one year, ~10–20 K papers): metadata + LaTeX-first full text → sections; references → citation edges.

Pass criteria: **B-1** kill mid-ingest → resume → zero duplicate chunks, all docs present (hash check); **B-2** `papers` 20-needle set: hybrid recall@10 ≥ 0.8 and ≥ max(lexical, dense); graph expansion rescues ≥ 3/20; **B-3** tier 1 ingested unattended; 10× (tier 1 vs V) → p50 ≤ 2× and recall within 10%; single query p50 ≤ 2 s; **B-4** one door re-checked with the full store (A-4 again); **B-5** cost profile per corpus in the journal.
Later phases, instantiated when reached: **B2** adapters wiki / books / code (tree-sitter — the original B); **B3** KB write side (D-I: notes store with provenance; round-trip criterion); **B4** scale tiers 2–4 (Simple English Wikipedia → full Wikipedia → full arXiv), gated on measured throughput.

### 2.9 Phase P — Execution model (deferrable; scope as PLAN.md)

Code tools via A's registry → `depends_on` + sub-task ids with the conservative-bias rule → bounded pool with `copy_context` → frozen snapshot (`Document.clone()`) → serial compose with the reconciliation duty → serial recovery → retire the legacy chain incl. N10. Criteria **P-P1…P-P6** unchanged (P-P2 uses `seq`/`ts`).

### 2.10 Phase T — Packs: code prover → science → book

- Pack API extends `config/registry.py` (`pack:` in `OrchestratorConfig`, `extra='forbid'`): prompt overrides, tool set, stores, verifiers, output shape (`needs_planning`).
- **T-code** prover: corpus-less first (CLI scenarios + run/test verifier); B2-code later.
- **T-science** (D-B): over B's `papers` store; summarise; claim/method/result cards (in-run scratchpad until B3); compare N papers; literature review; verifier = claim-vs-retrieved-passage judge + objective citation resolution.
- **T-book**: `books` adapter (B2); canon notes; consistency verifier emitting revision ops on earlier chapters; series continuation = R loop + canon store.
- `legal`: config-only existence proof.

Pass criteria: **T-1…T-4** as PLAN.md (T-1's structural-neighbour clause only once B2-code exists); **T-5** science: 5 papers → claim cards with ≥ 90% of citations resolving to the right passage; a 3-paper comparison ≥ 3.5/5 (judge); **T-6** book: continue a 3-chapter seed with ingested canon → 0 contradictions on a 10-item checklist in 2/3 runs and ≥ 1 revision op on an earlier chapter from a later milestone.

### 2.11 Phases C and H

H = faces: the oobabooga trigger (H-1…H-4 as PLAN.md), the `jobs` CLI from R, N19 per-chat state. C = chat turns as a B2 adapter.

### 2.12 Sizing (honest; one task per session)

| Phase | Tickets | Sessions | Server |
| --- | --- | --- | --- |
| O | 5 | 2.5–3.5 | none |
| 0-close-A | 5 | ≈ 1.5 | ≈ 2 h idle (re-baseline, 0-06, 0-09) |
| 0-close-B | 4 | ≈ 2 | behavioural only |
| Q | 3 | 3–4 | Q-02 campaign: 60 turns ≈ 10–17 h at `--jobs 1`; `--jobs 3` acceptable |
| A | 5 | ≈ 3 | A-05 behavioural |
| V | 3 | ≈ 2 | short |
| R-mech | 4 | ≈ 3 | one smoke |
| B (papers, tier 1) | 4 | weeks; ingest unattended | embedding + benchmark |
| T-science | 3–4 | weeks | campaign |

≈ 20 sessions from O through A; the first user-visible job (V) lands at ≈ 25.

### 2.13 Task board — model / effort / planning per ticket (D-K)

Rules: **Fable 5.1 only where reasoning depth decides the outcome** (interface and loop designs; re-plan moments) — never to implement a spec'd ticket. **Opus 5.5 is the default implementer**: `medium` for a fully specified ticket; `high` for diagnosis, prompt/behaviour work, concurrency, or library internals; `xhigh` only for P-02. **Sonnet 5.5** for run-and-record (`low`) and mechanical edits with a checklist (`medium`). **No Haiku** on this repo (every ticket ends in journal writing + commits). Nothing needs `max`. A ticket with distinct parts (design / implement / run / analyse) is split across sessions, one model each. These values go into each ticket's `model:` / `effort:` / `needs_planning:` front-matter when instantiated.

| Ticket | Model | Effort | Planning stage? | Why |
| --- | --- | --- | --- | --- |
| O-04 reconstructed S-003, track runs, caveat fix | Sonnet 5.5 | medium | no | facts enumerated here; first `reconstructed` entry sets the pattern |
| O-03 env, endpoint truth, seam test | Opus 5.5 | medium (seam test high) | no | `llama_utils`/`schema`/`harness`; instructor internals; escalate if the 3.13 venv changes results |
| O-02 archive / delete / `.gitignore` | Sonnet 5.5 | medium | no | mechanical but ordered; traps spelled out |
| O-01 INDEX / DECISIONS / PLAN v2 / AGENTS | Opus 5.5 | high | no (this file is the spec) | condense 585 lines, choose ≤ 12 decisions; every later session reads it |
| O-05 README | Sonnet 5.5 | low | no | |
| 0-14 harness truthfulness, marginal G2, contamination exit | Opus 5.5 | high | no | ContextVar attribution across threads; re-score old runs |
| 0-16 re-baseline + token-growth attribution | run Sonnet/low → analysis Opus/high | — | no | idle-window job; if the diagnosis implies a prompt redesign, that design is Fable/high |
| 0-06 N8 decision + re-measure | Sonnet 5.5 | medium | no | decision rule in the ticket |
| 0-09 s1 re-run | Sonnet 5.5 | low | no | |
| 0-11 extension import + clean user text | Sonnet 5.5 | medium | no | hook flow documented; user confirms in UI |
| 0-10a skip the ignored critique call | Sonnet 5.5 | low | no | behaviour-identical by construction |
| 0-10b critique-driven regeneration | Opus 5.5 | high | no | prompt behaviour + measurement; after Q-01 |
| 0-12 partial status, history copies, integrity coverage | Opus 5.5 | medium | no | split N3 out if it fights the composer |
| 0-13 instructor-path test coverage | Opus 5.5 | high | no | time-boxed to one session |
| Q-01 judge tool | design Fable/high → implement Opus/medium | — | **yes** | rubric, pairwise protocol, validation set |
| Q-02 harness vs single call | run Sonnet/low → analysis Opus/high | — | no | if the harness loses, the re-plan is Fable/high |
| Q-03 G3 gate | Sonnet 5.5 | medium | no | |
| A-01 `ContextStore` interface | Fable 5.1 | high | **yes** | most load-bearing decision; dry-run on paper against papers/books/code/notes/chat stores |
| A-02 Document store + BM25 | Opus 5.5 | medium | no | |
| A-03 ToolRegistry + multi-store oracle | Opus 5.5 | high | short | largest A ticket; executor loop + tests |
| A-04 op-log seq/ts, snapshot promotion | Sonnet 5.5 | medium | no | |
| A-05 live criteria run | Sonnet 5.5 | medium | no | needle-set construction |
| V-01 fetch / parse / FTS5 store | Opus 5.5 | medium | brief, in-session | LaTeX/PDF parsing choices |
| V-02 tasks through the pipeline | prompts Opus/medium; runs Sonnet/medium | — | no | |
| V-03 judge + write-up | Opus 5.5 | medium | no | |
| R-01 run model design | Fable 5.1 | high | **yes** | persistence layout, milestone semantics, replayability |
| R-02 persistence + resume | Opus 5.5 | high | no | |
| R-03 milestone loop + planner prompt | Opus 5.5 | high | no | |
| R-04 `jobs` CLI, fake-client tests, smoke | Opus 5.5 | medium | no | |
| B-01 corpus framework | design Fable/high → implement Opus/high | — | **yes** | |
| B-02 backend + embedding benchmark | sweeps Sonnet/medium → write-up Opus/medium | — | no | the choice is the user's, recorded in DECISIONS |
| B-03 hybrid retrieval + citation graph | Opus 5.5 | high | no | |
| B-04 papers adapter, tier 1 | adapter Opus/high; ingest runs Sonnet/low | — | no | |
| T pack API | design Fable/high → implement Opus/high | — | **yes** | contract generality (T-2) depends on it |
| T-code prover | Opus 5.5 | medium | no | |
| T-science | Opus 5.5 | high | no | reuses Q-01's judge for the verifier |
| T-book | verifier design Fable/high → implement Opus/high | — | **yes** | long-context consistency is the hardest verifier |
| P-01 DAG schema + conservative-bias prompt | Opus 5.5 | high | no | |
| P-02 frontier, snapshot, concurrency | Opus 5.5 | **xhigh** | short | the only concurrency-correctness ticket |
| P-03 serial recovery | Opus 5.5 | high | no | |
| P-04 retire legacy chain | Sonnet 5.5 | low | no | |

---

## Part 3 — Execution order for Phase O (five commits, no server)

0. **Human step:** the user pushes `master` to `origin` from the host (10 commits unpushed; this container has no credentials). INDEX carries a "last pushed" line from then on.
1. **O-04** — commit the pending harness/AGENTS hunk with the corrected caveat; track the two run files; `S-003.md` (`reconstructed: true`); 0-06 Measurements.
2. **O-03** — `pyproject.toml`, `Makefile`, curated `requirements.txt`, endpoint truth (D-P), seam test; `make venv && make test`; record the result in the ticket.
3. **O-02** (after step 0 is confirmed) — archive → delete → `git rm` / `git mv` → `.gitignore` rewrite → `git status --porcelain --ignored` → suite still green. One commit.
4. **O-01** — INDEX, DECISIONS, PLAN v2, tickets README v2, SESSION_TEMPLATE v2, AGENTS rewrite; instantiate the 0-close-A/B, Q and A tickets.
5. **O-05** — README refresh.
6. `S-004.md` before closing; INDEX "Now" → 0-14.

## Part 4 — Verification of Phase O

1. `make venv && make test` → result recorded (expected 186 passed / ≤ 10 skipped / 0 failed on 3.13; any diff goes into O-03's ticket).
2. `git ls-files | cut -d/ -f1 | sort -u` equals the O-2 set; `git status --porcelain --ignored` shows only the whitelisted local dirs after `pip install -e .` + `make test`.
3. `git check-ignore -v journal/baseline/runs/probe.json` exits 1; `grep -nE '^\*\.(md|json)$' .gitignore` is empty.
4. `grep -rn "mcp_server" --include=*.py .` → nothing but the retirement message in `reasoning_sub_agents/__main__.py` (rewrite its wording if it points at a deleted path).
5. `journal/archive/README.md` lists every archived/deleted path and the branch table; `grep -c '^## D-' journal/DECISIONS.md` ≤ 12 and every `D-\d{3}` cited in AGENTS/PLAN/tickets resolves.
6. Cold read: `AGENTS.md` → `INDEX.md` answers O-1's six facts; `make board` renders every ticket from front-matter.
7. Commits: explicit paths only; journal + code together; ticket IDs in messages; trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
