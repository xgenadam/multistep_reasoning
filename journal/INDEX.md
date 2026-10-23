# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-23 (Q-02 stage 0: drivers, override, test runner, checklists, launchers committed; bench v1 drafted at 140 prompts and the pre-registration drafted, both awaiting the user's review; S-022; `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** A; A-01 is done (D-018, approved 2026-10-19). Phase 0 close-out: 0-14 (P0-6), 0-15 (P0-10), 0-16 (P0-7, D-016), 0-06 (P0-4) and 0-09 (D-017) are done; 0-11 is deferred by the user (2026-10-19), not dropped.
- **Next move:** the user reviews `journal/design/Q-02-bench-v1.md`: the 140-entry prompt list in `bench/v1/manifest.yaml`, the four exemplars, the draft pre-registration (§ 3), the bias guards (§ 4) and the questions (§ 7). On approval: commit the pre-registration in Q-02 Notes, write the remaining 136 prompts (sub-agents, batches reviewed, `check-bench` green), freeze v1, then the two baselines (timing) and the compute-matching pilot (Opus 5.5 / high). R1–R5 labels are still due before Q-02 stage 2 (Q-06 app, `labelling_app/README.md`). Open AGENTS.md, this file, S-022, the ticket and the note.

## Resources
- **Generator:** `:8091` serves Qwen flash (`qwen3.8-flash-next`) on the user's customised vLLM at `http://host.containers.internal:8091/v1`, on all four cards plus 40–50 GiB RAM (≈ 125 tok/s on code); it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). `:5000` is text-generation-webui's API (loader llama.cpp, Qwen3.8-27B GGUF on disk) with no model loaded on 2026-10-19. Export `LLM_BASE_URL` (D-008). Q-02's generators boot in the container with `scripts/server/generator-server.sh <flash-next|qwen3.8-27b|qwen3.6-35b-a3b>` (`:8090` / `:8093` / `:8094`; `stop` to release).
- **Judge:** flash-next of record (tuned lane, prefix caching off, D-021), Devstral-2-123B Q3_K_M (`SPLIT=tensor`) as concurrence judge; provisional until the R1–R5 labels; all four slow-tier GGUFs and both new generators are in `~/models`. Judges are served by the agent in its container from `~/models` (`scripts/server/judge-llama-server.sh`, `http://localhost:8092/v1`); downloads via `scripts/models/hf-queue.sh`. `:8000` Devstral-123B on the host is down. Hardware: 4 × RTX 3090 (96 GiB), 128 GiB RAM, EPYC 7542; one big model at a time, or two pinned to 2 cards each (`../AGENTS.md` § Environment). Judge tiers and candidate models: Q-01 Notes.
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Baseline:** 0-16 denominators (`:8091`, thinking off) in `../AGENTS.md` § Baseline; contamination yardsticks per backend in `compare.CLEAN_COMPOSE_P50_S`. `:5000` has no current-code baseline.
- **Pushed:** `origin/master` = `f5c590c` (S-012). `master` adds the 0-06 close, S-014, the 0-09 close, the A-01 design, the A-01 approval, the Q-01 stage 1 commits (S-018) and Q-01 stage 2 (S-019), Q-04, D-020, S-020, D-021, Q-06, S-021 and S-022 (Q-02 stage 0); the user pushes from the host.
- **Server owner:** Q-02 stage 0 (S-022, D-022), since 2026-10-23 ~11:40Z. flash-next `:8090` baseline and pilot are done; since 13:44Z qwen3.8-27b runs on cards 0–1 (`:8093`, 4 slots) and qwen3.6-35b-a3b on cards 2–3 (`:8094`) side by side, for their baselines and then their (a″) pilots. The watchdog is pid 207355.

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. Q-02 stage 0, rest — blocked on the user's review of bench v1 and the pre-registration; then the 136 remaining prompts, freeze, baselines for Qwen3.8-27B and Qwen3.6-35B-A3B (timing) and the (a″) pilot — Opus 5.5/high — timing for the baselines — Q-01, Q-04 (formally; stage 2 needs the labels)
2. Q-06 — labelling app built (Q-11); the user labels R1–R5 later, due before Q-02 stage 2 (deferred 2026-10-23) — Opus 5.5/medium — none — none
3. Q-01 — blocked: Q-1's real-pair half waits on the R1–R5 labels (stage 2 done, S-019)
4. Q-04 — slow tier scored (S-020); final pick waits on the R1–R5 labels (D-021's condition); fast tier deferred to Q-03 — Sonnet 5.5/medium — behavioural — Q-01
5. Q-02 stage 1 — the campaign (`--jobs 3`, pinned worktree) — Sonnet 5.5/low — behavioural — stage 0; an A-02 session (Opus 5.5/medium, none) may run meanwhile
6. Q-02 judging window + stage 2 — slow-tier judge batch, then analysis — Opus 5.5/high — behavioural — stage 1
7. Q-03 — G3 gate in `compare.py` — Sonnet 5.5/medium — none — Q-01, Q-02; then the re-plan point (Fable 5.1/high if the harness lost)
8. A-02 (if not already overlapped) → A-03 (Opus 5.5/high) → A-04 (Sonnet 5.5/medium) → A-05 (Sonnet 5.5/medium, timing; includes the `g3` G3 line) → N21 JSON schema dedup (Opus 5.5/medium → re-baseline, timing, D-016)
- Any time, gates nothing in A: A-06 — retrieval escalation + conflict judgement, design only — Fable 5.1/high — none — A-01.
- Deferred by the user (2026-10-19), come back to: 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI).
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, unblocked by 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6), 0-15 done (P0-10), 0-16 done (P0-7, D-016), 0-06 done (P0-4), 0-09 done (D-017). The 0-09 run's s1 failed P0-1 on a composer-chosen prose section (0-09 Notes; not fence-related). Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q:** Q-02 stage 0 tooling done (S-022), bench v1 and pre-registration in review; Q-01 stage 2 done, ticket blocked on R1–R5 labels (Q-1 objective half and Q-5 pass on the `:8091` self-judge); Q-04 slow tier scored 2026-10-23, pick provisional (Q-10); Q-02 re-staged (Q-2 revised, Q-6…Q-9); Q-03 open; Q-05 ablations on PLAN's task board; Q-06 labelling app built 2026-10-23 (Q-11).
- **A:** A-01 done (A-9, D-018); A-02…A-06 open; A-02 starts after Q-03 or overlaps Q-02's campaign (D-019).
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
