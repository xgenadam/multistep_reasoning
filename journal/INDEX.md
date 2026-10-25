# INDEX — live board (hand-maintained; ticket status lives only in front-matter: `make board`)

updated: 2026-10-24 (Q-02 stage 1 paused at 14:10Z for a host shutdown, resume steps in Now; the 2,048 JSON cap removed (`ac1f636`); the freeform-then-JSON idea and the composer keep rule noted for later; earlier: D-025, D-026, S-022; `git log -1 -- journal/INDEX.md`)

## Now
- **Phase:** A; A-01 is done (D-018, approved 2026-10-19). Phase 0 close-out: 0-14 (P0-6), 0-15 (P0-10), 0-16 (P0-7, D-016), 0-06 (P0-4) and 0-09 (D-017) are done; 0-11 is deferred by the user (2026-10-19), not dropped.
- **Next move:** **Q-02 stage 1 paused after flash-next a1 (2026-10-25 ~01:15Z, the user)** to investigate the flash-next lane: with thinking on, 53 of 70 code prompts gave no answer (50 at the 32,768 allowance, coherent reasoning, no loop): `journal/design/flash-next-thinking-issue.md` (evidence, lane config, the test). The generator stays up for the user. After the investigation: if the lane was the cause, re-run a1 on the fixed lane; then the rest of `runs/q02-stage1-logs/driver/chain2.sh` from its c step (c, v1-std b and a2, A/A b and a2, from `a82c5b7`, `--jobs 6`), then `match`; then the D-027 history rewrite (**do not push until it is done**); then the 35B-A3B alone on four cards (f16 KV; the 27B is dropped, D-028; MTP and 8 slots checked first if quick), and the flash-next thinking-levels study (D-028). Spec draft: `journal/baseline/qe1_spec.draft.yaml`. Run files are 2–14 MB, past rule 8: the user decides trim or commit. Open AGENTS.md, this file, S-022, the ticket.

## Resources
- **Generator:** `:8091` serves Qwen flash (`qwen3.8-flash-next`) on the user's customised vLLM at `http://host.containers.internal:8091/v1`, on all four cards plus 40–50 GiB RAM (≈ 125 tok/s on code); it needs `LLM_MODEL=qwen3.8-flash-next` (O-06). `:5000` is text-generation-webui's API (loader llama.cpp, Qwen3.8-27B GGUF on disk) with no model loaded on 2026-10-19. Export `LLM_BASE_URL` (D-008). Q-02's generators boot in the container with `scripts/server/generator-server.sh <flash-next|qwen3.8-27b|qwen3.6-35b-a3b>` (`:8090` / `:8093` / `:8094`; `stop` to release).
- **Judge:** flash-next of record (tuned lane, prefix caching off, D-021), Devstral-2-123B Q3_K_M (`SPLIT=tensor`) as concurrence judge; provisional until the R1–R5 labels; all four slow-tier GGUFs and both new generators are in `~/models`. Judges are served by the agent in its container from `~/models` (`scripts/server/judge-llama-server.sh`, `http://localhost:8092/v1`); downloads via `scripts/models/hf-queue.sh`. `:8000` Devstral-123B on the host is down. Hardware: 4 × RTX 3090 (96 GiB), 128 GiB RAM, EPYC 7542; one big model at a time, or two pinned to 2 cards each (`../AGENTS.md` § Environment). Judge tiers and candidate models: Q-01 Notes.
- **Interpreter:** `.venv/bin/python` (3.12.15, D-012); `make venv` rebuilds it, `make test` runs the suite.
- **Baseline:** 0-16 denominators (`:8091`, thinking off) in `../AGENTS.md` § Baseline; contamination yardsticks per backend in `compare.CLEAN_COMPOSE_P50_S`. `:5000` has no current-code baseline.
- **Pushed:** `origin/master` = `f5c590c` (S-012). `master` adds the 0-06 close, S-014, the 0-09 close, the A-01 design, the A-01 approval, the Q-01 stage 1 commits (S-018) and Q-01 stage 2 (S-019), Q-04, D-020, S-020, D-021, Q-06, S-021 and S-022 (Q-02 stage 0: tooling, bench v1, D-022, D-023, three baselines and pilots); the user pushes from the host.
- **Server owner:** the small-model relaxed study (S-022, the user, 2026-10-25 from 16:25Z): gemma-4-e4b on cards 0–1 (`:8100`), arms b, b-think, a, a1, a2 on v1's 70 code prompts at relaxed budgets, from worktree `runs/relaxed-67dee1e`; driver `runs/small-models/relaxed.sh` (status `relaxed_gemma-4-e4b.status`); notes `journal/design/small-models.md`. Q-02's 35B-A3B campaign follows. Every card capped at 250 W; the watchdog runs.

## Queue (execution order: id — title — model/effort — needs_server — depends_on)
1. Q-02 stage 1 — the campaign (Now); stage 2 needs the R1–R5 labels and the § 4.4 check — Q-01, Q-04 (formally)
2. Q-06 — labelling app built (Q-11); the user labels R1–R5 later, due before Q-02 stage 2 (deferred 2026-10-23) — Opus 5.5/medium — none — none
3. Q-01 — blocked: Q-1's real-pair half waits on the R1–R5 labels (stage 2 done, S-019)
4. Q-04 — slow tier scored (S-020); final pick waits on the R1–R5 labels (D-021's condition); fast tier deferred to Q-03 — Sonnet 5.5/medium — behavioural — Q-01
5. Q-02 stage 2's analysis script — done (S-022, `qe1_analysis.py report --spec`; readings chosen in the review note); the judging session builds c-vs-b pairs with `qe1_pairs.py --subset overlap` and A/A with `--repeat` — an A-02 session (Opus 5.5/medium, none) may run during stage 1
6. Q-02 judging window + stage 2 — slow-tier judge batch, then analysis — Opus 5.5/high — behavioural — stage 1
7. Q-03 — G3 gate in `compare.py` — Sonnet 5.5/medium — none — Q-01, Q-02; then the re-plan point (Fable 5.1/high if the harness lost)
8. A-02 (if not already overlapped) → A-03 (Opus 5.5/high) → A-04 (Sonnet 5.5/medium) → A-05 (Sonnet 5.5/medium, behavioural (D-025); includes the `g3` G3 line) → N21 JSON schema dedup (Opus 5.5/medium → re-baseline, D-016)
- Any time, gates nothing in A: A-06 — retrieval escalation + conflict judgement, design only — Fable 5.1/high — none — A-01.
- After Q-02's verdict (the harness is frozen until then): the user's idea of freeform first, JSON second, to cut structured-call failures; measure from Q-02's runs first — `design/freeform-then-structure.md`.
- Deferred by the user (2026-10-19), come back to: 0-11 — extension repair — Sonnet 5.5/medium — none (+ user's UI).
- D-025/D-026 follow-ups (Sonnet 5.5/medium, none): `compare.py` drops its `jobs > 1` refusal for cost gates; run files record power cap, card layout and server build; `stream_conversation` asks for usage; a checklist smoke test on gold texts.
- Slot between the above, on a free server: 0-12, 0-13 (none); 0-10a (behavioural, unblocked by 0-16); Q-02 campaign (after Q-01, 0-14, A-04) → Q-03 → 0-10b.

## Phase status
- **O:** complete (O-01…O-06 done).
- **0:** 0-14 done (P0-6), 0-15 done (P0-10), 0-16 done (P0-7, D-016), 0-06 done (P0-4), 0-09 done (D-017). The 0-09 run's s1 failed P0-1 on a composer-chosen prose section (0-09 Notes; not fence-related). Re-scoring shows two tracked s3 follow-ups fail P0-3 as revised by D-014 (part identity; 0-14 Notes).
- **Q:** Q-02 stage 0 done (S-022): bench v1.1 and v1-std frozen, pre-registration amended by the delegated review (D-026), baselines and pilots on all three generators; Q-01 stage 2 done, ticket blocked on R1–R5 labels (Q-1 objective half and Q-5 pass on the `:8091` self-judge); Q-04 slow tier scored 2026-10-23, pick provisional (Q-10); Q-03 open; Q-05 ablations and Q-07 (confidence study, D-023) on PLAN's task board; Q-06 labelling app built 2026-10-23 (Q-11).
- **A:** A-01 done (A-9, D-018); A-02…A-06 open; A-02 starts after Q-03 or overlaps Q-02's campaign (D-019).
- **V, R, B, T, P, C, H:** not instantiated (task board at the end of PLAN.md).

## Pointers
`../AGENTS.md` (how) · `PLAN.md` (what/why, criteria) · `DECISIONS.md` · `tickets/README.md` · latest `S-NNN.md` · `archive/README.md`
