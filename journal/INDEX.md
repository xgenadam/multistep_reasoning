# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-19 (the S-007 close commit, `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** O (organisation). O-05 and O-06 are done; O-01 is still `in_progress` (O-1 failed in S-007: 5 files opened).
- **Next move:** a cold session runs 0-14 (Opus 5.5 / high). Before its first message it opens only AGENTS.md, this file and `tickets/0-14.md`. If it states the six facts from those three, it also flips O-01 to done (it re-measures O-1).

## Resources
- **Generator:** `:5000` (Qwen3.8-27B GGUF, llama-server) had no model loaded on 2026-10-19. The user served `qwen3.8-flash-next` (vLLM) at `http://host.containers.internal:8091/v1`; it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). Export `LLM_BASE_URL` (D-008).
- **Judge:** `:8000` Devstral-123B is down (launchers in `scripts/server/`).
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Pushed:** `origin/master` = `236d168`. `master` adds `a81a95f` (O-02), `bba6c39` (O-01), `f9b5d24` (O-05) and the O-05/O-06 close commit; the user pushes from the host.
- **Server owner:** nobody (no harness job running).

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. 0-14 — harness truthfulness — Opus 5.5/high — none — O-01
2. 0-15 — thinking switch + log (D-013) — Opus 5.5/medium — behavioural — 0-14
3. 0-16 — re-baseline + token growth — Sonnet→Opus, low→high — timing — 0-14, 0-15
4. 0-06 — consolidation re-measure — Sonnet 5.5/medium — timing — 0-14, 0-16
5. 0-09 — s1 fence re-run — Sonnet 5.5/low — behavioural — 0-14
6. 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI) — none
7. A-01 — ContextStore design — Fable 5.1/high — none — none
8. Q-01 — judge tool — Fable→Opus, high→medium — behavioural — none
9. A-02 — Document store + BM25 — Opus 5.5/medium — none — A-01
10. A-03 — ToolRegistry + multi-store oracle — Opus 5.5/high — none — A-02
11. A-04 — op-log seq/ts + snapshot promotion — Sonnet 5.5/medium — none — none
12. A-05 — Phase A live criteria run — Sonnet 5.5/medium — timing — A-02, A-03, A-04, 0-16
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, after 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** O-02…O-06 done. O-01 waits on a cold-session O-1 pass.
- **0:** 0-close-A/B instantiated. 0-06 and 0-09 re-measure after 0-14/0-16.
- **Q, A:** instantiated, not started.
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
