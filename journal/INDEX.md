# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-22 (Q-04 started: the agent serves judges itself from `~/models` in its own container; slow-tier downloads queued; `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** A; A-01 is done (D-018, approved 2026-10-19). Phase 0 close-out: 0-14 (P0-6), 0-15 (P0-10), 0-16 (P0-7, D-016), 0-06 (P0-4) and 0-09 (D-017) are done; 0-11 is deferred by the user (2026-10-19), not dropped.
- **Next move:** Q-04 slow tier is running (started 2026-10-22, Fable 5.1 this session; Sonnet 5.5 / medium for the per-judge runs): `scripts/server/judge-llama-server.sh` per candidate, then `quality.py judge --repeat 2 --jobs 1` on `bench/validation/pairs.yaml`; S-019's verdict file is the `:8091` self-judge control row. Q-01 is blocked only on the R1–R5 labels. Then Q-02 stage 0 (Opus 5.5 / high, no server). Phase Q runs before A-02 starts (D-019); an A-02 session may overlap Q-02's campaign window. The R1–R5 labels wait on the user's labelling app (PLAN § Task board); the fast judge tier waits on the user's three-card experiment, not needed before Q-03. Open AGENTS.md, this file and the ticket.

## Resources
- **Generator:** `:8091` serves Qwen flash (`qwen3.8-flash-next`) on the user's customised vLLM at `http://host.containers.internal:8091/v1`, on all four cards plus 40–50 GiB RAM (≈ 125 tok/s on code); it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). `:5000` is text-generation-webui's API (loader llama.cpp, Qwen3.8-27B GGUF on disk) with no model loaded on 2026-10-19. Export `LLM_BASE_URL` (D-008).
- **Judge:** served by the agent in its container from `~/models` (`scripts/server/judge-llama-server.sh`, `http://localhost:8092/v1`); downloads via `scripts/models/hf-queue.sh`. `:8000` Devstral-123B on the host is down. Hardware: 4 × RTX 3090 (96 GiB), 128 GiB RAM, EPYC 7542; one big model at a time, or two pinned to 2 cards each (`../AGENTS.md` § Environment). Judge tiers and candidate models: Q-01 Notes.
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Baseline:** 0-16 denominators (`:8091`, thinking off) in `../AGENTS.md` § Baseline; contamination yardsticks per backend in `compare.CLEAN_COMPOSE_P50_S`. `:5000` has no current-code baseline.
- **Pushed:** `origin/master` = `f5c590c` (S-012). `master` adds the 0-06 close, S-014, the 0-09 close, the A-01 design, the A-01 approval, the Q-01 stage 1 commits (S-018) and Q-01 stage 2 (S-019); the user pushes from the host.
- **Server owner:** Q-04 (judge serving on the four cards from the agent container, from 2026-10-22; the host-side generator must stay down meanwhile).

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. Q-01 — blocked: Q-1's real-pair half waits on the labelling app (stage 2 done, S-019)
2. Q-04 — judge benchmark, slow tier first — Sonnet 5.5/medium — behavioural (the user swaps models) — Q-01
3. Q-02 stage 0 — bench v1, arm drivers, config override, test runner, commit + wall in drivers — Opus 5.5/high — none — Q-01, Q-04
4. Q-02 stage 1 — the campaign (`--jobs 3`, pinned worktree) — Sonnet 5.5/low — behavioural — stage 0; an A-02 session (Opus 5.5/medium, none) may run meanwhile
5. Q-02 judging window + stage 2 — slow-tier judge batch, then analysis — Opus 5.5/high — behavioural — stage 1
6. Q-03 — G3 gate in `compare.py` — Sonnet 5.5/medium — none — Q-01, Q-02; then the re-plan point (Fable 5.1/high if the harness lost)
7. A-02 (if not already overlapped) → A-03 (Opus 5.5/high) → A-04 (Sonnet 5.5/medium) → A-05 (Sonnet 5.5/medium, timing; includes the `g3` G3 line) → N21 JSON schema dedup (Opus 5.5/medium → re-baseline, timing, D-016)
- Any time, gates nothing in A: A-06 — retrieval escalation + conflict judgement, design only — Fable 5.1/high — none — A-01.
- Deferred by the user (2026-10-19), come back to: 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI).
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, unblocked by 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6), 0-15 done (P0-10), 0-16 done (P0-7, D-016), 0-06 done (P0-4), 0-09 done (D-017). The 0-09 run's s1 failed P0-1 on a composer-chosen prose section (0-09 Notes; not fence-related). Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q:** Q-01 stage 2 done, ticket blocked on R1–R5 labels (Q-1 objective half and Q-5 pass on the `:8091` self-judge); Q-04 started 2026-10-22 (Q-10, slow tier); Q-02 re-staged (Q-2 revised, Q-6…Q-9); Q-03 open; Q-05 ablations and the labelling app on PLAN's task board.
- **A:** A-01 done (A-9, D-018); A-02…A-06 open; A-02 starts after Q-03 or overlaps Q-02's campaign (D-019).
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
