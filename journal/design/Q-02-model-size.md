# Q-02 amendment proposal: a second generator, so Q-E1 measures the harness at two model strengths

- **Ticket:** Q-02 (criteria Q-2, Q-6, Q-7, Q-8, Q-9). **Date:** 2026-10-23.
  **Model:** Opus 5.5 / medium.
- **Sources:** the user's request of 2026-10-23 ("we need to know how [the
  harness] performs with big and small models"); PLAN § Phase Q; D-016,
  D-019; Q-02 Scope; Q-04 Notes and verdict files to date.
- **Status:** approved by the user on 2026-10-23 with one change: all three
  generators (§ 2), not one. Both downloads approved; flash-next as the
  second-opinion judge approved. D-020 records it; the § 9 fold list is
  applied. The text below is the proposal as approved, unchanged.

## 0. Summary

1. **Q-E1 gets a model-strength factor.** The same arms run on two
   generators: flash-next, the strong generator and today's only one, and a
   faster, weaker one (the low-capability generator). The harness's value
   may depend on the generator: a weak model has more errors to fix, a
   strong one may gain little. One generator cannot show that.
2. **The comparison stays within each generator.** For each one, the
   harness (b) is compared with that generator's own compute-matched
   self-refine arm (a″). Each generator gets its own pre-registered claim
   under Q-6. Generators are never pooled, the same rule as domains (Q-8).
3. **The size trend is reported descriptively, not as a claim.** Showing
   that the gain differs between the two generators needs roughly four
   times the n of either claim alone. The proposal does not buy that n.
4. **One judge of record for both tables**: the slow-tier judge Q-04
   selects. Flash-next judges the weaker generator's table as a second
   opinion, which is cheap and gives a judge-agreement check.
5. **Recommended weaker generator:** Qwen3.6-35B-A3B Q4_K_M. It shares
   flash-next's family, so the size factor is not mixed up with a family
   change, and the judge of record comes from another family either way.
   It needs a download of about 22 GB, which needs the user's approval
   (the 2026-10-22 download limit).
6. **Cost:** one new baseline (D-016) and a second campaign on a fast
   model, then judging. Judging dominates, and its size depends on the
   judge Q-04 picks (§ 5).

## 1. Why within-generator comparisons make the judge question easier

An earlier message in the session said flash-next cannot judge both
generators, because it would be judging its own outputs in one table and
not the other. That overstated it. Every comparison here is between arms of
the same generator. In flash-next's table, every arm is flash-next's
output, so self-preference falls on both sides equally. That is D-019's
argument for self-judging as a control. What stays is D-019's other
caveat: shared blind spots do not cancel. A cross-family judge of record
removes them for both tables.

Using different judges per table would confound judge with generator when
the two gains are set side by side. So the proposal keeps one judge of
record across both tables, and flash-next's second opinion is reported
beside it, never in place of it.

## 2. Choosing the weaker generator

Requirements: it fits beside nothing (the generators run one at a time), is
much faster than flash-next per harness turn, can follow the harness's JSON
operation schema at least some of the time, and is not from the judge of
record's family.

| Candidate | On disk here | Family | Notes |
| --- | --- | --- | --- |
| Qwen3.6-35B-A3B Q4_K_M | no (host only) | Qwen | 3B active parameters, fast; same family as flash-next isolates size; about 22 GB |
| gpt-oss-20b MXFP4 | no | OpenAI | about 12 GB; cross-family from everything; a different chat format and reasoning style |
| Qwen3.8-27B UD-Q6_K | no (host only) | Qwen | the original `:5000` generator, dense; nearer flash-next in strength, so a weaker contrast |

Recommendation: **Qwen3.6-35B-A3B**. If the user prefers a cross-family
contrast, gpt-oss-20b is the alternative. A third point (all three) would
show a trend rather than a contrast, at about 1.5× this proposal's cost.

If the weaker generator cannot drive the harness at all (schema failures
on most turns), that is itself a result: the harness's floor. It is
recorded as op-failure and retry rates per arm, not hidden by a retry
loop.

## 3. What changes in Q-02

- **Arms:** unchanged: (a), (a′), (a″), (b), and (c) on the overlap subset,
  now per generator. (a″) is matched to *that* generator's harness median
  completion tokens ±25 % (Q-7 per generator).
- **Set:** unchanged: bench v1, the same prompts for both generators.
- **Stage 0** gains a generator switch in the arm drivers (the config
  override already planned) and the new generator's launcher.
- **Stage 1 (campaign)** runs twice, once per generator. The weaker
  generator's campaign is short.
- **Baseline:** the weaker generator gets its own 0-16-style baseline
  (s1–s4 × 2, `--jobs 1`, about 15 minutes) before any wall time is
  compared (D-016). Token and op counts need no baseline.
- **Stage 2 (analysis)** reports two tables, one per generator, each with
  the Q-6 test, and a descriptive side-by-side of the two gains.
- **Pre-registration (Q-6):** both claims are written in Q-02 Notes before
  the first run file of either campaign: the effect (default 0.70), n and
  the analysis, per generator.

## 4. Power

The claim per generator is unchanged: the Wilson 95 % lower bound above
0.5 on decisive pairs, and a point estimate of at least 0.70.

| Decisive pairs | Wilson lower bound at 0.70 |
| --- | --- |
| 20 | 0.48 |
| 25 | 0.52 |
| 40 | 0.55 |
| 60 | 0.58 |
| 80 | 0.59 |

With bench v1's 80 prompts and a tie rate near GLM's 0.34 on the standard
slice, about 50 pairs per generator would be decisive. That is enough for
each claim at a true rate of 0.70, but not for a test of the difference
between the two gains. That test would need about 200 decisive pairs per
generator. Hence the descriptive framing in § 0.3.

## 5. Cost

Per generator, the judged pairings are (b) vs (a″) as the primary, plus
(b) vs (a) and (b) vs (a′) as secondary: 3 pairings × 80 prompts × 2
orders = 480 judge calls. Two generators make 960 calls, plus 480 for
flash-next's second opinion on the weaker generator's table.

Harness outputs are longer than the validation pairs, so judge calls will
cost more than Q-04's measured rates. Using Q-04's bespoke-set rates as a
floor:

| Judge of record | s/call measured | 960 calls, floor |
| --- | --- | --- |
| GLM-4.5-Air | 4.4 | about 70 min |
| Devstral-2-123B, layer split | 18.2 | about 4.9 h |

Devstral's row-split rate, being measured now, may cut its figure
sharply. The second opinion on flash-next costs about 15 minutes.

Generation: the weaker generator's campaign is probably under half
flash-next's wall time; flash-next's own campaign is already in Q-02's
plan.

## 6. Risks

- **The weaker generator's outputs may be too broken to compare.** If most
  of its harness turns fail, the comparison is degenerate. The fix is to
  report it, not to tune the harness for it in this phase.
- **Judge strength.** The judge of record should be at least as strong as
  the generators it judges. Against the weaker generator this is easy;
  against flash-next it depends on Q-04's result. GLM's failure on the
  padded pairs and its position bias on long documents are relevant here.
- **Scope creep.** Two generators double the stage 1 and stage 2 work. The
  re-plan point before A-03 moves back by about one campaign window.

## 7. Draft decision (unnumbered until approval)

> Q-E1 runs on two generators: flash-next and a weaker generator
> (recommended Qwen3.6-35B-A3B Q4_K_M), with the same arms, set and
> per-call `max_tokens`. Each generator's (b) vs (a″) claim is
> pre-registered and tested on its own; generators are never pooled; the
> difference between the two gains is reported descriptively. One judge of
> record (Q-04's slow-tier pick) judges both tables; flash-next's verdicts
> on the weaker generator's table are a second opinion. The weaker
> generator gets its own baseline before any wall-time comparison.
> Refines D-019; supersedes nothing.
> Why: the harness's value may depend on model strength, and the project's
> question is whether the harness helps, not whether it helps one model.
> Re-open if: the weaker generator fails the harness's schema on most turns
> (then the contrast is degenerate), or the judge budget for two tables
> exceeds what Q-4 allows.

## 8. Questions for the user

1. Approve the second generator, and which one: Qwen3.6-35B-A3B
   (recommended), gpt-oss-20b, or all three points including Qwen3.8-27B?
2. Approve the download it needs (about 22 GB for the recommendation).
3. Approve flash-next as the second-opinion judge on the weaker
   generator's table.

## 9. Fold list on approval

- DECISIONS: the § 7 entry, numbered.
- PLAN § Phase Q: Q-02's arms line gains "per generator"; Q-2 and Q-7
  read "per generator".
- Q-02 Scope: § 3's changes. Q-02 Notes: the two pre-registrations, before
  the first run file.
- INDEX: queue item 3 notes the second generator and its baseline.
