# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-19 (Q-01 stage 1 started: hardware recorded, two judge tiers, Q-04 judge benchmark instantiated with Q-10; `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** A; A-01 is done (D-018, approved 2026-10-19). Phase 0 close-out: 0-14 (P0-6), 0-15 (P0-10), 0-16 (P0-7, D-016), 0-06 (P0-4) and 0-09 (D-017) are done; 0-11 is deferred by the user (2026-10-19), not dropped.
- **Next move:** Q-01 stage 1 is in progress (Fable 5.1, no server). The judges come from Q-04's benchmark (instantiated 2026-10-19 at the user's request; its fast tier waits on the user's three-card experiment on flash-next, which is not needed before Q-03). Next within stage 1: rule on PLAN § Phase Q's S-012 proposal before A-02. Then A-02 (Opus 5.5 / medium, no server; the A-01 note's § 5.2 is its map). A-06 (Fable 5.1 / high, design only) can run any time; it does not gate A-02…A-05. Open AGENTS.md, this file and the ticket.

## Resources
- **Generator:** `:8091` serves Qwen flash (`qwen3.8-flash-next`) on the user's customised vLLM at `http://host.containers.internal:8091/v1`, on all four cards plus 40–50 GiB RAM (≈ 125 tok/s on code); it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). `:5000` is text-generation-webui's API (loader llama.cpp, Qwen3.8-27B GGUF on disk) with no model loaded on 2026-10-19. Export `LLM_BASE_URL` (D-008).
- **Judge:** `:8000` Devstral-123B is down (launchers in `scripts/server/`). Hardware: 4 × RTX 3090 (96 GiB), 128 GiB RAM, EPYC 7542; one big model at a time, or two pinned to 2 cards each (`../AGENTS.md` § Environment). Judge tiers and candidate models: Q-01 Notes.
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Baseline:** 0-16 denominators (`:8091`, thinking off) in `../AGENTS.md` § Baseline; contamination yardsticks per backend in `compare.CLEAN_COMPOSE_P50_S`. `:5000` has no current-code baseline.
- **Pushed:** `origin/master` = `f5c590c` (S-012). `master` adds the 0-06 close, S-014, the 0-09 close, the A-01 design and the A-01 approval commits; the user pushes from the host.
- **Server owner:** nobody (0-09 run finished 2026-10-19).

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. Q-01 — judge tool — Fable→Opus, high→medium — behavioural — none (stage 1 rules on PLAN § Phase Q's S-012 proposal before A-02)
2. Q-04 — judge benchmark, both tiers — Sonnet 5.5/medium — behavioural — Q-01 (slow tier on any model swap; fast tier after the user's three-card experiment)
3. A-02 — Document store + BM25 — Opus 5.5/medium — none — A-01 (if Q-01 accepts the S-012 proposal's P1, run Q-02 first)
4. A-03 — ToolRegistry + multi-store oracle + `results` store — Opus 5.5/high — none — A-02
5. A-04 — op-log seq/ts + snapshot promotion + `Part.role` — Sonnet 5.5/medium — none — none
6. A-05 — Phase A live criteria run — Sonnet 5.5/medium — timing — A-02, A-03, A-04, 0-16 (measure the pre-A oracle first: A-05 Notes)
7. N21 JSON schema dedup (task board, not yet a ticket) — Opus 5.5/medium → re-baseline — timing — A-05 (D-016)
- Any time, gates nothing in A: A-06 — retrieval escalation + conflict judgement, design only — Fable 5.1/high — none — A-01.
- Deferred by the user (2026-10-19), come back to: 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI).
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, unblocked by 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6), 0-15 done (P0-10), 0-16 done (P0-7, D-016), 0-06 done (P0-4), 0-09 done (D-017). The 0-09 run's s1 failed P0-1 on a composer-chosen prose section (0-09 Notes; not fence-related). Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q:** Q-01 stage 1 in progress (judge tiers set; the S-012 ruling next); Q-04 instantiated (Q-10); Q-02, Q-03 open.
- **A:** A-01 done (A-9, D-018); A-02…A-06 open.
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
