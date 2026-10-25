# Q-02: decisions made by delegated review, for the user's later look

- **Why this file exists:** the user delegated the Q-02 mass review
  (planned for Sunday 2026-10-25) to sub-agents on 2026-10-24, to save
  time, and asked for a note of every decision made that way so they can
  review it later. The user's own review is optional.
- **Who decided what** (the user left the choice of model to the agent):
  - value choices (pre-registration, Holm, outcome rules, bias guards,
    compute-matching rule, freezing v1-std, D-025's thresholds): Fable 5.1
    / high;
  - correctness checks (bench v1 content and the § 9 flags; D-024's code;
    whether D-025's wording is measurable): Sonnet 5.5;
  - the coordinator (Opus 5.5 / high, S-022) checked every blocker against
    the code before acting, and wrote this file.
- **Cost of changing a decision later:** a change made after stage 1 has
  produced run files voids the run files it touches (D-022). The close
  calls are marked, so a short look at those before stage 1 starts covers
  most of the risk.

## How to review

For each row, mark approve or change. A change before stage 1 costs only
an amendment; after stage 1, a re-run of what it touches.

## Start here: the close calls

If you look at only five things, look at these. Each is a value choice,
not a correctness one, and changing it before stage 1 costs an amendment.

1. **No multiple-comparison correction (row 6).** It is right only while
   the gain bar keeps "point estimate ≥ 0.70". If you would build on a
   harness that is truly 0.65, Fable's alternative is a point ≥ 0.60 bar
   with Holm reinstated (≈ 72 % power at 0.70).
2. **The effect stays 0.70 (row 7).** Power at exactly 0.70 is ≈ 48 % per
   cell, a property of the magnitude bar, not of n. If the harness is truly
   0.70 everywhere, at least one of six cells passes with ≈ 98 %.
3. **Per-prompt compute matching (row 10)** over "accept the overshoot and
   report it". Keeping the one-round minimum leaves the 35B-A3B's long
   reports at 1.4–1.8× the harness, which favours self-refine.
4. **Your blind spot check (row 15)** is adopted and needs about an hour
   before the stage 2 verdict, in the same sitting as the R1–R5 labels.
5. **V-4 and B-3 keep wall-time bounds (row 18).** They time the store
   (no model calls). D-025 could be read to cover them; the coordinator
   left them as they are for you.

## Decisions

Decided by: **F** = Fable 5.1 / high; **S** = Sonnet 5.5; **C** = the
coordinator, Opus 5.5 / high (S-022). "Voids" means what a change after
stage 1 has run would void; before stage 1, any change is only an
amendment.

| # | Item | Decision | By | Close call? | Committed in | A later change voids |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Delegating the mass review | sub-agents decide; your review is optional | you | no | D-026 | n/a |
| 2 | D-025's rewording of P0-4, A-6, P-P1, P-P5, T-4, Q-4 | kept; see row 17 | C, then F and S | no | `9071d65`, this commit | nothing in Q-02 |
| 3 | Pre-registration wording | adopted with fixes: "gain" defined (lower bound > 0.5, point ≥ 0.70, the concurrence judge agrees), the trigger named, concurrence defined for code | F | no | Q-02 Notes 2026-10-24 amendment | the verdict's analysis |
| 4 | Power figures | corrected: the stated 81 % was for "better" only; the gain bar has ≈ 47–50 % at 0.70, 76–79 % at 0.75, 94–96 % at 0.80 (C recomputed: 48 % at n = 49) | F, checked by C | no (arithmetic) | same | n/a |
| 5 | Code outcome rule | hidden tests first; the judge only when pass-rates tie | F | no | same | every code pair |
| 6 | Holm across six claims | **no correction**: the gain bar's 0.70 point condition is stricter than Holm's strictest step for n ≥ 44, so Holm never changes a verdict | F | **yes** | same | the verdict |
| 7 | Effect size and n | 0.70 and 70 prompts per domain stand | F | **yes** | same | the verdict (n: the campaign) |
| 8 | Re-plan trigger | Phases A–T build on the harness only on a gain in at least one generator × domain cell | F | worth a look | same | the verdict |
| 9 | Roots-only sensitivity | each claim is also computed on the 56 root prompts per domain | F | no | same | n/a (extra analysis) |
| 10 | Compute matching | per-prompt budget = the harness's tokens on that prompt in the same generator's run; next round only if spent + last round ≤ budget; first round always; at most 8; ceiling 3× the larger of the budget and the stratum median | F | **yes** | same; `arms.py --refine-budget-from` | every (a″) run file |
| 11 | Q-7 | one-sided: (a″) ≥ 0.75× the harness's median; above 1.25× labelled over-resourced (that favours (a″), so a harness gain there stands) | F | worth a look | PLAN Q-7; `arms.py match` | the Q-7 verdict |
| 12 | § 4.1 standard slice | adopted; compared with v1's short strata only; IFEval: more strict instructions followed wins | F | no | Q-02 Notes; `bench/v1-std/README.md` | the slice table |
| 13 | § 4.2 long/short split | adopted as written (descriptive) | F | no | Q-02 Notes | n/a |
| 14 | § 4.3 A/A control | adopted on flash-next; the repeat (a″) run reuses run 0's budgets | F | no | Q-02 Notes | the A/A run |
| 15 | § 4.4 your blind spot check | adopted; due before the stage 2 verdict, not blocking stage 1 | F | **yes** (needs your hour) | Q-02 Notes | n/a |
| 16 | Freezing v1-std | frozen as built. Licences checked by C from the published cards: both Apache-2.0 (BigCodeBench-Hard via its parent card); `LICENSE`, attribution and the changes made are now in `bench/v1-std/` | F, licences C | no | `bench/v1-std/` | v1-std run files |
| 17 | D-025 thresholds | kept, with medians named (A-6 over ≥ 10 queries, prompt tokens ±10 %, completion ±25 %; P-P5 and T-4 over s1–s4 × 2) and P-P1's new logging flagged | F and S, reconciled by C | no | PLAN | nothing in Q-02 |
| 18 | V-4, B-3 (pure-store latency) | left as wall-time bounds | C | **yes, yours** | D-026 | nothing in Q-02 |
| 19 | Bench § 9 flags | all kept except c14, c36, r06/r06f, r08 (row 20) | S | no | this file | n/a |
| 20 | Bench v1 → v1.1 | c14: `rows` may be any iterable; c36: the `.` error is at the `.`; c47/c47f: the surrogate-pair escapes restored in the prompt and tests (they tested nothing); r06/r06f: one more decision allowed; r08: a wider "two seasons" pattern | S, checked by C | no | `bench/v1/` | v1.1 run files |
| 21 | Hidden-test scorer | 20 s per test (SIGALRM); the 120 s file timeout stays as the backstop | S, built by C | no | `hidden_tests.py` | code scores |
| 22 | D-024's code | approved; the run file now carries each harness turn's completion tokens, estimated calls and ceiling stop | S, built by C | no | `harness.py`, `task_orchestrator.py` | n/a |
| 23 | (a′) thinking-call defect | a thinking call gets the whole allowance (4 × 8,192 = 32,768) in one call and continues only once its answer has started; flash-next's 60 a1 results are void and a1 re-runs in full at the fix commit; a is kept (a derived a-only file, original under `runs/`) | C, the user approved the re-run | no (a defect fix restoring the pre-registered arm) | `arms.py`, Q-02 Notes 2026-10-24 | the a1 run files |
| 24 | flash-next `--jobs` | 6 (measured: +13 % mixed, +27 % decode over 3; 8 queues) for the remaining flash-next runs | C, at the user's request | no (throughput only; tokens exact at any `--jobs`, D-025) | `arms.DEFAULT_JOBS`, AGENTS.md, Q-02 Notes | nothing |
| 25 | Reading harness file parts that hold a markdown reply | the scorer reads them with the single-call arms' text rule (`hidden_tests._fenced_body`); b 0.091 → 0.677 on flash-next | you (C built it) | no | `hidden_tests.py`, Q-02 Notes 2026-10-25 | every code score |
| 26 | Layout for the 35B-A3B and 27B | side by side, 2 cards each; the 27B at q8_0 KV | you | no | Q-02 Notes 2026-10-25 | nothing (throughput; KV type recorded) |
| 27 | Generators | the Qwen3.8-27B dropped (D-028); the 35B-A3B alone on 4 cards, f16 KV; row 26's layout void; a flash-next thinking-levels study added, exploratory | you | no | D-028, Q-02 Notes 2026-10-25 | nothing (no 27B run existed) |

## Stage 2 analysis script: readings chosen (Opus 5.5 / high)

`journal/baseline/qe1_analysis.py` implements the amended
pre-registration. Where the spec left a choice, it took the reading most
conservative for a harness-gain claim. The ones worth your look:
- **A gain where Q-7 is not met** ((a″) under 0.75× the harness, or the
  ratio unknown) is reported as "gain … not compute-matched" and does
  **not** count for the re-plan trigger.
- **Missing inputs withhold a cell** (no verdict, reasons listed) rather
  than count as losses: a missing concurrence file, an unjudged pair, a
  missing arm, stale test scores, a wrong judge model or rubric, a pilot
  run file. An errored arm on a prompt is still a loss, as pre-registered.
- **Until the R1–R5 labels pass and your § 4.4 check is done**, every
  verdict is marked provisional. If the labels fail, Devstral becomes the
  judge of record for the primary claims (D-021).
- **IFEval outcome:** an errored or empty side loses first, then the
  strict instruction count decides (an empty answer can satisfy rules
  such as "no commas").
- **Not implemented: the length-controlled win-rate.** It is listed as a
  secondary, but the pre-registration never defined its method. Length,
  tokens and wall per arm are in the report's JSON.

## Corrections made on the reviewers' findings

All in the commit that adds this file, with `make test` green.
- **Pre-registration (F, blocker B1):** the verdict, power and
  multiplicity were inconsistent. Rewritten as rows 3–9.
- **Compute matching (F, blocker B2):** the stratum budgets rested on n = 3
  (the 35B-A3B's short-code budget was above its long-code one).
  `arms.py run --refine-budget-from B_RUN_FILE`, the full-last-round stop,
  the larger-of ceiling and `match`'s `ratio_to_b`, `q7_met` and
  `over_resourced`, with tests.
- **Bench fixes (S):** row 20. `check-bench`: 70/70 code, 70/70 report.
- **Scorer timeout (S):** row 21, with a test (one hang fails one test).
- **Run-file logging (S):** row 22, with tests.
- **Wording (S, F):** PLAN's "Critical paths" (the phase chain) renamed
  "Dependency chains", so it does not collide with the new term. A-05's
  title and Q-4 note, and Q-01's design note, no longer say "timing gate".

## Findings not acted on

- **`stream_conversation` sends no `stream_options` (S, should-fix).** Off
  the harness path the meter would estimate tokens from text. The harness
  injects it, so no Q-02 arm is affected; fix it before anything else uses
  `token_ceiling`.
- **D-024 minors (S):** payloads built outside `_emit`'s try (safe in
  practice); no per-turn write-error count in the run file; step files
  sort wrong past 99 steps (unreachable); a first draft that hits the
  ceiling is kept truncated (already marked `stop: ceiling`, rounds 0).
- **`compare.py` (S):** G1 is still wall-based, and it refuses `jobs > 1`.
  Already queued as a D-025 follow-up.
- **P0-6 and P0-7's wall wording (S):** both are passed criteria and
  describe what was measured then; left as recorded.
- **Bench minors (S):** c37's trailing-newline case, c40's live objects,
  c08's `^1.2.3+meta`: each is inferable or near-universal, and costs at
  most one test, equally across arms. A smoke test that runs each numeric
  checklist on a gold text would catch regex breakage: worth adding later.
- **Long reports over one call's 8,192 tokens (S, note):** not a defect.
  Single-model arms continue on `length` (up to 3 continuations), so they
  are not cut at one call.
- **Both deliverables at 0/N go to the judge (F, note):** symmetric across
  arms; left as pre-registered.
- **D-021's concurrence cost (F, note):** sized for 80 prompts; at 140 it
  is up to 840 judge calls, minus test-decided code pairs. Plan the judging
  window with that.
- **v1-std's code half is mostly file-system and CSV tasks (F, note):** a
  consequence of the stdlib-only filter; it checks the short strata only.
- **AGENTS.md "Timing gates" (F, note):** already reworded in `9071d65`;
  the reviewer read an earlier copy.
