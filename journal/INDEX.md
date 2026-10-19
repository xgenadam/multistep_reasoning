# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-19 (the S-008 0-14 close commit, `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** 0 close-out (0-close-A). Phase O is complete: O-01 closed in S-008 (O-1 passed with 3 files). 0-14 is done, so the harness is truthful (P0-6).
- **Next move:** 0-15 (Opus 5.5 / medium, behavioural). Open AGENTS.md, this file and `tickets/0-15.md` (plus D-013), then `make test`. Read `tickets/README.md` and `SESSION_TEMPLATE.md` at session end, not start.

## Resources
- **Generator:** `:5000` (Qwen3.8-27B GGUF, llama-server) had no model loaded on 2026-10-19. The user served `qwen3.8-flash-next` (vLLM) at `http://host.containers.internal:8091/v1`; it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). Export `LLM_BASE_URL` (D-008).
- **Judge:** `:8000` Devstral-123B is down (launchers in `scripts/server/`).
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Pushed:** `origin/master` = `236d168`. `master` adds `a81a95f` (O-02), `bba6c39` (O-01), `f9b5d24` (O-05), `59ad620` (O-05/O-06), `bafde28` (D-013) and the 0-14 close commit; the user pushes from the host.
- **Server owner:** nobody (no harness job running).

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. 0-15 — thinking switch + log (D-013) — Opus 5.5/medium — behavioural — 0-14
2. 0-16 — re-baseline + token growth — Sonnet→Opus, low→high — timing — 0-14, 0-15
3. 0-06 — consolidation re-measure — Sonnet 5.5/medium — timing — 0-14, 0-16
4. 0-09 — s1 fence re-run — Sonnet 5.5/low — behavioural — 0-14
5. 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI) — none
6. A-01 — ContextStore design — Fable 5.1/high — none — none
7. Q-01 — judge tool — Fable→Opus, high→medium — behavioural — none
8. A-02 — Document store + BM25 — Opus 5.5/medium — none — A-01
9. A-03 — ToolRegistry + multi-store oracle — Opus 5.5/high — none — A-02
10. A-04 — op-log seq/ts + snapshot promotion — Sonnet 5.5/medium — none — none
11. A-05 — Phase A live criteria run — Sonnet 5.5/medium — timing — A-02, A-03, A-04, 0-16
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, after 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6). 0-06 and 0-09 re-measure after 0-16. Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q, A:** instantiated, not started.
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
