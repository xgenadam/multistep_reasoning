# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-19 (the S-011 0-16 close commit, `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** 0 close-out (0-close-A). 0-14 (P0-6), 0-15 (P0-10) and 0-16 (P0-7: fresh baseline, N18 accepted as a measurement artefact, D-016) are done.
- **Next move:** 0-06 (Sonnet 5.5 / medium, timing): consolidation re-measure on `:8091` at `--jobs 1`; compare.py now judges contamination against that backend's 0-16 yardstick. Claim the server first. Open AGENTS.md, this file and `tickets/0-06.md`.

## Resources
- **Generator:** `:5000` (Qwen3.8-27B GGUF, llama-server) still had no model loaded at S-009 (2026-10-19). The user served `qwen3.8-flash-next` (vLLM) at `http://host.containers.internal:8091/v1`; it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). Export `LLM_BASE_URL` (D-008).
- **Judge:** `:8000` Devstral-123B is down (launchers in `scripts/server/`).
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Baseline:** 0-16 denominators (`:8091`, thinking off) in `../AGENTS.md` § Baseline; contamination yardsticks per backend in `compare.CLEAN_COMPOSE_P50_S`. `:5000` has no current-code baseline.
- **Pushed:** `origin/master` = `dc31608` (D-014). `master` adds the 0-15, 0-16 stage 1 and 0-16 close commits; the user pushes from the host.
- **Server owner:** nobody (0-16 stage 1 run finished 2026-10-19).

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. 0-06 — consolidation re-measure — Sonnet 5.5/medium — timing — 0-14, 0-16
2. 0-09 — s1 fence re-run — Sonnet 5.5/low — behavioural — 0-14
3. 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI) — none
4. A-01 — ContextStore design — Fable 5.1/high — none — none
5. Q-01 — judge tool — Fable→Opus, high→medium — behavioural — none
6. A-02 — Document store + BM25 — Opus 5.5/medium — none — A-01
7. A-03 — ToolRegistry + multi-store oracle — Opus 5.5/high — none — A-02
8. A-04 — op-log seq/ts + snapshot promotion — Sonnet 5.5/medium — none — none
9. A-05 — Phase A live criteria run — Sonnet 5.5/medium — timing — A-02, A-03, A-04, 0-16 (measure the pre-A oracle first: A-05 Notes)
10. N21 JSON schema dedup (task board, not yet a ticket) — Opus 5.5/medium → re-baseline — timing — A-05 (D-016)
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, unblocked by 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6), 0-15 done (P0-10), 0-16 done (P0-7, D-016). 0-06 and 0-09 re-measure next; 0-15's off smoke failed 0-09's fence check (0-09 Notes). Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q, A:** instantiated, not started.
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
