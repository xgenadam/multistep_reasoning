# Q-01: the judge on paper (stage 1), and the ruling on the S-012 proposal

- **Ticket:** Q-01 (criteria Q-1, Q-4, Q-5). **Date:** 2026-10-19.
  **Model:** Fable 5.1 / xhigh (the ticket says high).
- **Sources:** PLAN § Phase Q and its "Proposed amendment (S-012)"; D-007,
  D-008, D-016, D-018; Q-01…Q-04 tickets; the 0-16 run file; `config/
  schema.py` (the switches P4 relies on); `harness.py` (`--judge-base-url`,
  no commit recorded); the user's answers of 2026-10-19 in Q-01 Notes
  (hardware, tiers, judges by benchmark, endpoints).
- **Status:** draft for the user's approval. Nothing here is in force until
  the approval bullet lands in `tickets/Q-01.md`. The draft decision in § 7
  is appended to DECISIONS.md at that point, and the fold list in § 8 is
  applied then, not before. Until then PLAN's criteria and the Q tickets'
  Scope stand as written.

## 0. Summary

1. **The S-012 proposal is accepted in substance** with six modifications
   (§ 1): the primary comparison is pre-registered as the harness against a
   compute-matched self-refine arm, matched on completion tokens; the
   default pre-registered effect is 0.70; "long" gets an operational
   definition and the single-model arms get a continue-until-done driver;
   the consolidation arm runs only on the overlap subset; ablations become
   a later ticket on the G3 subset; Q-2 is revised in place instead of
   renumbered.
2. **Order (P1).** Q-01 stage 2 → Q-04 slow tier → Q-02 (bench and drivers,
   campaign, analysis) → Q-03, all before A-02 starts. A-02's session may
   overlap the campaign's background window, with the campaign on a pinned
   worktree. The Q-E1 verdict is the re-plan point before A-03.
3. **Judging** runs on two tiers with judges chosen by Q-04 and self-judging
   as the control (§ 2). One judge per table. Every verdict file carries the
   judge's endpoint and model, the rubric version and the commit.
4. **Protocol** (§ 3): pairwise, both orders, decisive only when both orders
   agree, ties 0.5; the absolute rubric is secondary; inputs are blinded and
   normalised; temperature 0; strict JSON.
5. **Validation set** (§ 4): 12 pairs, listed with their sources. Five need
   the user's labels before Q-01 stage 2 measures Q-1.
6. **Budget** (§ 5): the Q-4 form and an estimate; Q-04 measures it.
7. **Draft D-019** (§ 7) supersedes D-007's quality half.

## 1. The ruling on the S-012 proposal

The three re-check questions first.

- **Is the harness still the thing in question?** Yes. A-02…A-05, R, B and
  T all build on decompose → execute → compose. No quality verdict on it
  exists: Phase 0 gated on shape and cost only. The north star is long jobs
  over corpora, where a bare single call is not an option at all, so a
  short-task verdict cannot settle the north-star question. It can still
  show whether the pipeline loses quality where it can be measured, which
  is what a re-plan would act on.
- **Does the generator still make a large campaign cheap?** Generation,
  yes: 62 s per harness turn on `:8091` (0-16), and the generator has all
  four cards during a campaign. Judging is no longer free: the judge is a
  model swap (Q-01 Notes), so judge batches are scheduled windows the user
  operates. The budget in § 5 is sized for that.
- **Have Phase A results answered any part?** No. A-01 is paper only.

Then the items. "Accept" means as written; "modify" lists the change.

| Item | Ruling | Reasons and modification |
| --- | --- | --- |
| P1 order | modify | Q-01 stage 2, Q-04 slow tier, Q-02 and Q-03 run before A-02 **starts**. D-007 makes quality a gate from Q on, so the gate must exist before A lands code, and the Q-E1 verdict is cheaper to act on before A-03…A-05, R, B and T than after. Modification: A-02 is `needs_server: none`, so its session may run while Q-02's campaign is a background job, provided the campaign runs from a pinned worktree (`git worktree add` at the recorded commit) so edits on master cannot leak into a running process. Q-02 drops `depends_on: A-04`; the snapshot functions in `harness.py` serve as they are. |
| P2 pre-registration and power | modify | Accept the mechanism: Q-02's Notes record the effect, the primary comparison and the analysis before the first run file; "better" needs the Wilson 95 % lower bound above 0.5 on decisive pairs; "meaningfully better" also needs the point estimate at or above the effect. Modification: the default effect is **0.70** (≈ 47 decisive pairs at 80 % power, two-sided α = 0.05), not 0.65 (≈ 85), because judging is a swap window and 0.65 doubles it. The tie rate is reported beside the decisive rate, and the all-pairs rate with ties at 0.5 is reported for G3. |
| P3 compute-matched baseline | modify | Accept the arms: (a) single call, thinking off; (a′) single call, thinking on; (a″) self-refine (draft → critique → revise, N rounds); (b) harness; (c) harness + consolidation. Three modifications. (1) **The primary comparison is pre-registered as (b) against (a″)**; "the strongest single-model arm" chosen after the fact is a forking path. (a) and (a′) are secondary. (2) **Match on completion tokens, ±25 %**, not total tokens: 59 % of the harness's prompt tokens are schema text and half of that a duplicate (N21, D-016), and prompt tokens are prefix-cached, so total tokens overstate the harness's compute. The harness's median is ≈ 6.4 K completion tokens per turn (0-16); N for (a″) is tuned on a 5-prompt pilot per domain and recorded before the campaign. Reasoning tokens count as completion tokens. (3) **(c) runs only on the overlap subset** (follow-up turns and prompts with deliberately overlapping deliverables), since 0-06 found the consolidator emitting no ops on single-turn prompts, so (c) = (b) there. |
| P4 ablations as configuration | accept, deferred | The switches exist in `OrchestratorConfig` (`decomposer`, `executor`, `composer`, `oracle`, `max_oracle_rounds`, `consolidation`, `thinking`, `thinking_by_step`). The harness exposes only `--consolidation` and `--thinking`, so Q-02 stage 0 adds a config-override flag. The ablation campaign is its own ticket, **Q-05**, instantiated after the Q-E1 verdict, on the G3 subset, one switch per arm, reporting the quality delta beside the marginal cost (D-007 form). Criterion Q-9's second sentence covers it. |
| P5 objective scoring first | accept | Code prompts carry hidden tests (pytest files beside the prompt, never in any prompt; a runner writes the rendered file parts to a temp dir and runs them with a timeout). Pass-rate with a Wilson CI is the code domain's primary metric; the judge is secondary there and runs only when both arms' tests agree. Report prompts carry a checklist (required sections, stated bounds, forbidden repeats) scored mechanically; the judge scores the rest. **Domains are never pooled**: a pass-rate and a win-rate are different quantities. The two padded-but-not-better pairs are in the validation set (§ 4) and in Q-04. |
| P6 task mix | modify | Accept ≥ ⅓ long prompts. Modifications: (1) **"long" is operational**: the reference deliverable exceeds the generator's per-call `max_tokens`, or has more than one file. (2) **≥ 20 % follow-up turns**, since s3 is where part identity and dedupe matter (D-014). (3) **The single-model arms get a continue-until-done driver** on long prompts: when a call ends on `length`, the driver sends "continue" with the partial output until a stop or a cap of 3 continuations. Without it the harness wins long prompts by truncation, which measures nothing. |
| P7 standing benchmark | accept | `journal/baseline/bench/v1/`: `prompts/<id>.md`, `tests/<id>/` for code, `checklists/<id>.yaml` for reports, `manifest.yaml` (domain, long, follow-up, overlap flags). One command runs any arm set on any subset. `subset: g3` names ≈ 10 prompts (half code, half report, two follow-ups) for G3 on every material change; the full set serves phase gates and the D-007 re-baselines. The set is frozen per version; a change is `v2`. |
| Q-2′ | modify | Q-2 is **revised in place** with the "(revised by D-019; was …)" form used for P0-3 and P0-4. Pass-criterion IDs are never renumbered (`tickets/README.md`), and a primed ID is a renumbering. |
| Q-6, Q-7, Q-8, Q-9 | accept with wording | Q-7 reads "within ±25 % of the harness's median completion tokens per prompt". Q-9 keeps both sentences; its ablation sentence is Q-05's criterion. |
| Draft decision | accept as D-019 | With the modifications above folded in (§ 7). |
| Cost estimate | revise | See § 5. The proposal's 7 h at `--jobs 1` covered generation only. Judging adds 10–18 h of slow-tier swap windows for Q-E1 at 80 prompts, unattended. |

What the ruling does not do: it does not change G3's thresholds (Q-03), the
Q-1 or Q-5 bars, or D-007's cost half.

## 2. Judging tiers, judges and endpoints

Recorded in Q-01 Notes (2026-10-19) and Q-04; summarised here so this note
stands alone.

- **Fast tier**, co-resident with the generator on cards it leaves free.
  Runs G3 on the `g3` subset between code changes, Q-5 repeatability and
  rubric development. It has no card until the user's three-card
  experiment, which is not needed before Q-03. If Q-04 shows a slow-tier
  swap per G3 run is tolerable, this tier is dropped.
- **Slow tier**, sequential: the generator alone during a campaign, then
  the judge alone over the committed run files. Runs Q-E1 and the phase
  gates.
- **Judges come from Q-04**, which scores every candidate on the validation
  set with a selection rule fixed before the run. **Self-judging** (the
  generator judging its own output) is the control in both tiers and the
  fallback when no second model is loaded. Its caveat: both arms share the
  generator, so self-preference is symmetric, but shared blind spots are
  not; the damaged pairs in § 4 test exactly that, and a self-judge that
  passes Q-1 is trusted on that evidence, not on its provenance. It is
  never the judge of record for a gate once a cross-family judge has passed
  Q-1 in that tier.
- **Each judge has its own endpoint, server and model name.** `quality.py`
  takes `--judge-base-url` and `--judge-model` with no silent default
  (D-008), checks reachability first, and writes both into every verdict
  file, with the rubric version and `git rev-parse HEAD`. The harness run
  file does not record the commit today; Q-02 stage 0 adds it.
- **One judge per table.** Two judges' verdicts never share a win-rate.

## 3. The pairwise protocol

- **Input.** The task text, the rubric (`rubrics/pairwise_v1.md`), and two
  candidates labelled A and B. Candidates are **normalised**: harness arms
  are `render()` output, single-call arms are their final text; part ids,
  op logs, summaries, reasoning and any mention of the arm are stripped;
  for follow-up turns the judge sees the whole document after the turn. A
  test result, when one exists, is attached to its candidate as one line
  (`tests: 7/9 passed`).
- **Orders.** Every pair is judged twice, A-B and B-A. The pair's outcome is
  the candidate that wins both orders; anything else is a tie, scored 0.5.
  A verdict that fails to parse is retried once, then recorded as `no
  verdict` and excluded from the decisive count (it is not a tie).
- **Rates.** Three numbers per pairing: the decisive win-rate with its
  Wilson 95 % CI (the P2 test), the tie rate, and the all-pairs rate with
  ties at 0.5 (G3's input, Q-03 unchanged).
- **Absolute rubric** (`rubrics/absolute_v1.md`) scores each arm once per
  prompt, secondary: it describes arms on their own and explains verdicts.
  It never replaces a pairwise verdict or a test result.
- **Sampling.** Temperature 0, fixed seed where the server honours one,
  `max_tokens` 2,048 for the verdict. Q-5 measures how deterministic that
  is in practice.
- **Position and length.** The rubric names both biases. The validation set
  measures them: position consistency across the two orders, and the padded
  pairs.
- **Blinding.** The judge never sees which arm produced a candidate, the
  arm's cost, or the other verdict.

## 4. The validation set (Q-1, P5)

Twelve pairs, each judged in both orders; Q-5 repeats each pair/order once.
Files land under `journal/baseline/bench/validation/` with a
`pairs.yaml` manifest (`pair_id`, `kind`, `a`, `b`, `expected`, `source`).
Stage 2 cuts and writes them; the user fills `expected` for R1–R5.

**Real pairs** (the user labels which is better; both sides are harness
output from the 0-16 run file, run 0 against run 1):

| Pair | Scenario | Why this one |
| --- | --- | --- |
| R1 | s1_cli_code | one file part against four: shape differs |
| R2 | s1b_csv2json_cli | same tool, two different sizes (2.5 K vs 4.6 K chars) |
| R3 | s2_report | three sections against one |
| R4 | s3_followup, turn 1 | the follow-up with its prior; two against four parts |
| R5 | s4_anchors | two deliverables; four parts against two |

Alternates if a pair turns out trivial: s1c r0/r1; 0-09's s1 pre-fix
against post-fix (fence-wrapped against unwrapped bodies); 0-06's s4
control against treatment.

**Damaged pairs** (the original against a hand-damaged copy; expected: the
original, in both orders):

| Pair | Source | Damage |
| --- | --- | --- |
| W1 | s2 report | the "one honest drawback" section removed |
| W2 | s1 wordcount | line count off by one (`len(lines) - 1`), all else intact |
| W3 | s1b csv2json | `--indent` parsed but ignored: present and wrong |
| W4 | s3 turn 1 | the new migration section repeats the benefits section verbatim ("do not repeat" broken) |
| W5 | s4 schedule | six days in the seven-day table |

**Padded pairs** (the original against the original plus ≈ 40 % text that
adds no requested content; expected: the original or a tie, in both
orders):

| Pair | Source | Padding |
| --- | --- | --- |
| L1 | s2 report | a "Further considerations" section restating the earlier sections |
| L2 | s1c logscan | a prose "How it works" restatement of the code appended as a second part |

**Scoring against Q-1.** Real pairs: agreement with the user's label on
≥ 4/5 (a tie counts as disagreement). Damaged pairs: the original wins in
both orders on ≥ 4/5. Padded pairs: not preferred in either order, 2/2,
reported beside Q-1 (P5). Q-5: repeat agreement ≥ 90 % over all 24
pair-orders.

## 5. The judge budget (Q-4)

The form: "the 12-pair validation set (48 calls) ≤ N tokens and ≤ M min on
tier T", and the same for the `g3` subset and for Q-E1. Q-04 fills N and
M per judge; these are the sizing estimates.

Assumptions: a short pair is ≈ 10 K input tokens (rubric 1.2 K, task 0.3 K,
two 0-16-sized candidates ≈ 4 K each) and ≈ 1 K output; a long pair is
30–60 K input. Slow tier at ≈ 800 tok/s prefill and ≈ 25 tok/s decode
(a 12B-active MoE on four 3090s); fast tier at ≈ 1,500 tok/s and ≈ 40
tok/s (a 24–27B Q4 on one card).

| Set | Calls | Tokens | Slow tier | Fast tier |
| --- | --- | --- | --- | --- |
| Validation, 12 pairs × 2 orders × 2 repeats | 48 | ≈ 0.5 M | ≈ 45 min | ≈ 20 min |
| `g3` subset, 10 pairs × 2 orders | 20 | ≈ 0.25 M | ≈ 20 min | ≈ 8 min |
| Q-E1, 80 prompts, 3 full pairings + (c) subset, both orders, ⅓ long | ≈ 530 | ≈ 9 M | 10–18 h | n/a |

Rules that follow: judge calls never run inside a timing-gate window (Q-4);
a Q-E1 judge batch is one claimed slow-tier window, scheduled, resumable
from the verdict file; code prompts whose tests decide skip the judge.

## 6. What stage 2 builds

- `journal/baseline/quality.py`: load run files (or bench outputs), build
  pairs, normalise candidates, call the judge with the rubric, parse strict
  JSON, write the verdict file, print the three rates with Wilson CIs. It
  takes `--judge-base-url`, `--judge-model`, `--rubric`, `--pairs`,
  `--repeat`, `--resume`.
- The validation set under `bench/validation/` with its manifest.
- Q-1 and Q-5 measured on whichever judge is up (self-judging on `:8091`
  needs no swap); the result is the tool's validation, and Q-04 repeats it
  per candidate.
- Tests: synthetic verdicts for each outcome, the both-orders rule, the
  no-verdict exclusion, the Wilson CI, and the seam test that `quality.py`
  builds a stock `OpenAI` client (AGENTS.md).

## 7. Draft D-019 (appended on approval)

> ## D-019 — Quality claims are pre-registered, powered and compute-matched; Q precedes A's implementation    2026-10-19 · S-018 · active
> Decision: A pass that claims a quality gain shows a Wilson 95 % CI lower bound above 0.5 on decisive pairs and a point estimate at or above the effect pre-registered in the ticket's Notes before its first run file (default 0.70). The primary comparison is the harness against a self-refine single-model arm matched on completion tokens (±25 %); bare single calls, thinking off and on, are secondary. Objective checks score what they can (hidden tests for code, checklists for reports) and the judge scores the rest; no judge verdict replaces a test result, and domains are never pooled. G3 non-inferiority (Q-03's thresholds) stays for changes that claim no gain and runs on the standing `g3` subset from A-05 on. The benchmark is a frozen, versioned set under `journal/baseline/bench/`, ≥ ⅓ long prompts (deliverable beyond one call's `max_tokens`, or multi-file) and ≥ 20 % follow-ups; single-model arms continue until done. Judging is pairwise, both orders, decisive only when both agree, on two tiers (fast co-resident, slow sequential) with judges chosen by Q-04 and self-judging as control and fallback; one judge per table; every verdict records judge, rubric version and commit. Q-01, Q-04 (slow tier), Q-02 and Q-03 run before A-02 starts; A-02's session may overlap Q-02's campaign window with the campaign on a pinned worktree; the Q-E1 verdict is the re-plan point before A-03. (user-approved, S-018)
> Why: n ≥ 10 cannot separate 0.70 from chance (7/10 gives 0.40–0.89); a bare single call uses a fraction of the harness's compute, so "the harness wins" could mean "more compute wins"; code can be tested; short tasks are where the harness is least likely to help; A through T invest in the pipeline, and D-007 already makes quality a gate from Q on, which needs the gate before A lands code.
> Supersedes: D-007's quality half ("pairwise judge, n ≥ 10"); PLAN's S-012 proposal block.    Re-open if: the measured judge budget (Q-4) makes the powered n infeasible on the generator and the slow-tier judge; or (a″) cannot be matched within ±25 % on completion tokens; or Q-04 finds no judge that passes Q-1 in either tier.

## 8. Fold list (applied on approval, one commit)

1. PLAN § Phase Q: rewrite Q-02's bullet (arms, primary comparison, bench,
   stages), add Q-05 to the task board, revise Q-2 in place, add Q-6…Q-9,
   delete the proposal block, cite D-019.
2. DECISIONS: append D-019; D-007's status word becomes "active; quality
   half superseded by D-019".
3. Tickets: Q-02 Scope and front-matter (three stages: Opus 5.5 / high
   bench and drivers → Sonnet 5.5 / low campaign → Opus 5.5 / high
   analysis; `depends_on: [Q-01, Q-04]`); Q-03 Scope (reads the verdict
   file; the three rates; the `g3` subset); A-02 Notes (start condition);
   A-05 Notes (runs the `g3` subset); Q-01 flips to stage 2.
4. INDEX: Queue in the § 0 order; Phase status.
5. S-018 records the ruling as a load-bearing decision.
