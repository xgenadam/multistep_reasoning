# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-19 (the S-009 0-15 close commit, `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** 0 close-out (0-close-A). 0-14 (P0-6, truthful harness) and 0-15 (P0-10, thinking explicit and logged, D-013/D-015) are done.
- **Next move:** 0-16 stage 1 (Sonnet 5.5 / low, timing: idle box, `--jobs 1`, thinking `off` is the default). Open AGENTS.md, this file and `tickets/0-16.md`, then `make test`. Read `tickets/README.md` and `SESSION_TEMPLATE.md` at session end, not start.

## Resources
- **Generator:** `:5000` (Qwen3.8-27B GGUF, llama-server) still had no model loaded at S-009 (2026-10-19). The user served `qwen3.8-flash-next` (vLLM) at `http://host.containers.internal:8091/v1`; it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). Export `LLM_BASE_URL` (D-008).
- **Judge:** `:8000` Devstral-123B is down (launchers in `scripts/server/`).
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Pushed:** `origin/master` = `dc31608` (D-014). `master` adds the 0-15 close commit; the user pushes from the host.
- **Server owner:** nobody (no harness job running).

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. 0-16 — re-baseline + token growth — Sonnet→Opus, low→high — timing — 0-14, 0-15
2. 0-06 — consolidation re-measure — Sonnet 5.5/medium — timing — 0-14, 0-16
3. 0-09 — s1 fence re-run — Sonnet 5.5/low — behavioural — 0-14
4. 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI) — none
5. A-01 — ContextStore design — Fable 5.1/high — none — none
6. Q-01 — judge tool — Fable→Opus, high→medium — behavioural — none
7. A-02 — Document store + BM25 — Opus 5.5/medium — none — A-01
8. A-03 — ToolRegistry + multi-store oracle — Opus 5.5/high — none — A-02
9. A-04 — op-log seq/ts + snapshot promotion — Sonnet 5.5/medium — none — none
10. A-05 — Phase A live criteria run — Sonnet 5.5/medium — timing — A-02, A-03, A-04, 0-16
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, after 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6), 0-15 done (P0-10). 0-06 and 0-09 re-measure after 0-16; 0-15's off smoke failed 0-09's fence check (0-09 Notes). Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q, A:** instantiated, not started.
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
