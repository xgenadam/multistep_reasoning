# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-19 (A-01 design note written, awaiting the user's approval; `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** A started with A-01. Phase 0 close-out: 0-14 (P0-6), 0-15 (P0-10), 0-16 (P0-7, D-016), 0-06 (P0-4) and 0-09 (D-017) are done; 0-11 is deferred by the user (2026-10-19), not dropped.
- **Next move:** the user reads `journal/design/A-01-context-store.md` and answers its § 7. On approval, a short session (Sonnet 5.5 / low, no server) records the dated approval bullet in `tickets/A-01.md`, appends the note's § 8 draft decision to DECISIONS.md under the next free D-nnn and flips A-01 to done; then A-02 (Opus 5.5 / medium) starts. Meanwhile Q-01 stage 1 (Fable 5.1 / high, no server) can run. Open AGENTS.md, this file and the ticket.

## Resources
- **Generator:** `:5000` (Qwen3.8-27B GGUF, llama-server) still had no model loaded at S-016 (2026-10-19). The user served `qwen3.8-flash-next` (vLLM) at `http://host.containers.internal:8091/v1`; it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). Export `LLM_BASE_URL` (D-008).
- **Judge:** `:8000` Devstral-123B is down (launchers in `scripts/server/`).
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Baseline:** 0-16 denominators (`:8091`, thinking off) in `../AGENTS.md` § Baseline; contamination yardsticks per backend in `compare.CLEAN_COMPOSE_P50_S`. `:5000` has no current-code baseline.
- **Pushed:** `origin/master` = `f5c590c` (S-012). `master` adds the 0-06 close, S-014, the 0-09 close and the A-01 design commits; the user pushes from the host.
- **Server owner:** nobody (0-09 run finished 2026-10-19).

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. A-01 — ContextStore design — Fable 5.1/high — none — none (note written 2026-10-19; blocked on the user's approval)
2. Q-01 — judge tool — Fable→Opus, high→medium — behavioural — none (stage 1 rules on PLAN § Phase Q's S-012 proposal before A-02)
3. A-02 — Document store + BM25 — Opus 5.5/medium — none — A-01 (if Q-01 accepts the S-012 proposal's P1, run Q-02 first)
4. A-03 — ToolRegistry + multi-store oracle — Opus 5.5/high — none — A-02 (the note proposes the `results` store lands here; the user decides)
5. A-04 — op-log seq/ts + snapshot promotion — Sonnet 5.5/medium — none — none (the note proposes `Part.role` lands here; the user decides)
6. A-05 — Phase A live criteria run — Sonnet 5.5/medium — timing — A-02, A-03, A-04, 0-16 (measure the pre-A oracle first: A-05 Notes)
7. N21 JSON schema dedup (task board, not yet a ticket) — Opus 5.5/medium → re-baseline — timing — A-05 (D-016)
- Deferred by the user (2026-10-19), come back to: 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI).
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, unblocked by 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6), 0-15 done (P0-10), 0-16 done (P0-7, D-016), 0-06 done (P0-4), 0-09 done (D-017). The 0-09 run's s1 failed P0-1 on a composer-chosen prose section (0-09 Notes; not fence-related). Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q:** instantiated, not started.
- **A:** A-01 blocked on the user's approval of `design/A-01-context-store.md` (2026-10-19); A-02…A-05 open.
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
