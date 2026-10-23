# Q-02 stage 0: bench v1 and the pre-registration, for the user's review

- **Ticket:** Q-02 (criteria Q-2, Q-6, Q-7, Q-8, Q-9). **Date:** 2026-10-23.
  **Session:** S-022, Opus 5.5 / high.
- **Sources:** Q-02 Scope and Notes; D-019, D-020, D-021;
  `design/Q-01-judge.md` § 1, § 3, § 9; `design/Q-02-model-size.md` § 4; the
  user's choice of 140 prompts (2026-10-23); this session's driver smoke
  test (§ 6).
- **Status:** provisionally in force under D-022 (the user's instruction,
  2026-10-23), with the agent's recommendations where § 7 left a choice.
  The pre-registration is committed in Q-02 Notes. The user's later mass
  review may amend or roll back any of it.

## 0. What to review

1. **The prompt list:** `journal/baseline/bench/v1/manifest.yaml`. It has
   140 entries with a one-line `brief` each. Look for prompts that are
   unfair to an arm, trivial, ambiguous, or out of the generators' reach.
2. **The four written exemplars**, which set the quality bar for the other
   136:
   - c06, an LRU cache: the prompt, 18 hidden tests, a reference and three
     broken variants;
   - c06f, its follow-up adding a TTL and statistics: 37 tests, three
     broken variants;
   - r01 and r01f, the s2/s3 report and its follow-up, with checklists.

   `hidden_tests.py check-bench` passes both code prompts: each reference
   passes all its tests, an empty deliverable passes none, and every broken
   variant is caught.
3. **The pre-registration (§ 3).** This is the binding part, so it
   matters more than anything else here.
4. **The bias guards (§ 4):** accept or reject each one.

## 1. Composition

| | Code | Report | Total |
| --- | --- | --- | --- |
| Prompts | 70 | 70 | 140 |
| Short roots | 32 (one file) | 34 (≤ 1,500 words) | 66 |
| Long roots | 24 (packages of 3–5 files) | 22 (6,000–7,500 words) | 46 |
| Follow-ups | 14 (8 long) | 14 (6 long) | 28 (20 %) |
| Long, all | 32 | 28 | 60 (43 %) |
| Overlap roots, for arm (c) | 6 | 6 | 12 |
| Overlap subset (overlap roots + follow-ups) | 20 | 20 | 40 |
| `g3` | c06, c06f, c13, c36, c47 | r01, r01f, r06, r23, r36 | 10 |

`tests/test_baseline/test_bench_v1.py` enforces these rules. "Long" follows
D-019's definition: multi-file code, or a report beyond one call's 8,192
tokens.

**Fairness by design.** Roughly half the prompts are short,
single-deliverable tasks where decomposition has little room to help:
single-function code, 250–900-word documents. The other half are long or
multi-part, which is the harness's natural ground. The report follow-ups
include edits that punish a rewrite-from-scratch: "everything else
unchanged", or "drop nothing still open". The code follow-ups' tests check
the old behaviour as well as the new.

**Known gaps.**
- Every task is self-contained. None needs a corpus beyond one call's
  context, which is the north-star regime (§ 4.4).
- Code is Python standard library only.
- The reports are business and technical writing, with no fiction or
  research synthesis.

## 2. How each domain is scored

**Code (objective first, Q-8).** Each (prompt, arm) output is extracted
(`hidden_tests.py`), and the result is its hidden-test pass-rate. The
denominator is the reference's test count, so a deliverable that fails to
import scores 0/N. Extraction failures are reported separately from test
failures.

**Report.** The judge decides the pairwise outcome (`quality.py`, both
orders). The checklist score (`checklists.py`) is reported per arm beside
it and never merged into it.

The exemplar checklists were calibrated on 0-16's real outputs:
- s2's two runs pass 7 of 8 items on r01, failing on length (743 and 523
  words against "about 300–500").
- On r01f, s3's turn-1 outputs fail the kept-section items and the
  three-step item. Those items are not comparable, though: s3's turn 0 was a
  different report from r01's.

## 3. Draft pre-registration (Q-6), to be committed in Q-02 Notes on approval

> **Claim.** For each generator g ∈ {flash-next, qwen3.6-35b-a3b,
> qwen3.8-27b} and each domain d ∈ {code, report}, the harness (b) gives
> better outputs than compute-matched self-refine (a″) on bench v1. That is
> six claims, never pooled across generators or domains (Q-8, D-020).
>
> **Unit.** One prompt. Arms (b) and (a″) run once per prompt, at server
> default sampling, with the same prompt text and `max_tokens` 8,192
> (`arms.py`, prompts version `arms-v1`).
>
> **Per-prompt outcome.**
> - *Code:* the arm with the higher hidden-test pass-rate wins. When the
>   pass-rates are equal, the judge's both-orders outcome decides (decisive
>   only if both orders agree, otherwise a tie). No judge verdict overrides
>   a test difference.
> - *Report:* the judge's both-orders outcome.
>
> A prompt where either arm errored, or produced no extractable
> deliverable, counts as a loss for that arm. It is not excluded, because a
> failure to deliver is a result.
>
> **Judges (D-021).** flash-next is the judge of record. It runs on the tuned
> lane with prefix caching off, rubric `pairwise_v1` and verdict
> `max_tokens` 4,096. Devstral-2-123B (tensor split) is the concurrence
> judge on every (b) vs (a″) pair. A claim passes only if both judges
> favour the same arm, which means both decisive rates are on the same side
> of 0.5.
>
> **Test.**
> - "Better": the Wilson 95 % lower bound of the decisive win-rate of (b)
>   is above 0.5.
> - "Meaningfully better": that, plus a point estimate of at least 0.70.
> - "Worse": the upper bound is below 0.5.
> - Otherwise the result is inconclusive.
>
> Ties are reported beside the decisive rate, along with the all-pairs rate
> with ties at 0.5.
>
> **Multiplicity.** The six claims are tested with Holm–Bonferroni at a
> family-wise α of 0.05. The headline uses the corrected result, and the
> uncorrected one is shown beside it.
>
> **n and power.** 70 prompts per domain. At 25–35 % ties that is ≈ 46–52
> decisive pairs.
> - Uncorrected (z = 1.96): 81 % power at a true 0.70, 95–96 % at 0.75.
> - Under Holm's strictest step (α/6, z = 2.64): 60–61 % at 0.70, 85–87 %
>   at 0.75. Later Holm steps are less strict, so these are lower bounds per
>   claim.
>
> **Compute matching (Q-7).** (a″)'s rounds N are set per generator and
> domain on a pilot of five fixed prompts per domain:
> - code: c02, c09, c16, c35, c43;
> - report: r03, r10, r22, r37, r46.
>
> N is the integer that puts (a″)'s median completion tokens per prompt
> within ±25 % of (b)'s, using `arms.py match`. Completion tokens include
> reasoning tokens. N is recorded before the campaign. The pilot's outputs
> are excluded from the analysis.
>
> **Secondary, reported but not claimed:**
> - (b) vs (a) and (b) vs (a′);
> - (c) vs (b) on the overlap subset, with the number of turns
>   consolidation changed;
> - tokens, wall time and length per arm, per prompt and per generator;
> - a length-controlled win-rate;
> - the long and short split (§ 4.2).
>
> **Stopping.** The full set runs once per generator. There is no optional
> stopping and no re-runs of prompts whose outcome is known. A prompt is
> re-run only on an infrastructure error (an HTTP error or a server crash),
> recorded in the run file.

## 4. Bias guards: proposals for the user (each can be accepted or rejected)

1. **A standard slice as an outside check.** Add about 20 prompts per
   domain from public sets the agent did not write:
   - code: BigCodeBench-Hard or LiveCodeBench, after the generators'
     cutoff;
   - report: IFEval and LongBench-Write (design note § 9).

   They are run on (b) and (a″) and reported as their own table. If the
   harness's effect there differs sharply from the bespoke set, the bespoke
   set is suspect.
   - Cost: about +30 % of generation.
   - It needs the user to download the slices, because the container has no
     internet.
2. **A pre-registered long/short split.** The bench is built so the long
   half should favour the harness and the short half should not. Writing
   that hypothesis down now turns "it only helps on long tasks" into a
   tested statement instead of a story found afterwards. Cost: none.
3. **An A/A control.** Run the `g3` subset twice for (b) and twice for
   (a″) on one generator, and judge each arm against itself. The win-rate
   should be ≈ 0.5, and anything else measures the noise floor of server
   sampling and the judge.
   - Cost: 20 extra arm-runs and 40 judge calls.
4. **Your spot check of the judge.** Label 12 random (b) vs (a″) report
   pairs per generator, blind, in the Q-06 app, at the same time as R1–R5.
   That measures the judge of record on this experiment's real outputs.
   - Cost: about an hour of your time.
5. **Note only: Q-E2 for the north star.** After the Q-E1 verdict, run
   8–10 corpus tasks whose input is far beyond one call's context, with
   map-reduce as the comparator, since a single call can't run there. This
   is not part of v1, and is recorded here so the re-plan finds it.

## 5. Cost re-estimate (stage 0's job), rough

The only measured rates come from § 6's two-prompt smoke test on
qwen3.6-35b-a3b at `--jobs 2`. Per prompt:

| Arm | c06 | c06f |
| --- | --- | --- |
| (a) | 9 s | 20 s |
| (a′) | 43 s | 112 s |
| (a″) with N = 1 | 12 s | 59 s |
| (b) | 59 s | 135 s |

Scaling assumptions:
- an average arm-prompt of ≈ 70–140 s;
- about 4.4 arm-runs per prompt: five arms on the overlap 40, four on the
  other 100;
- (a″) at a larger N;
- long reports at ≈ 2× c06f.

That gives roughly:

| Generator | Estimate at `--jobs 3` | Basis |
| --- | --- | --- |
| qwen3.6-35b-a3b | 6–10 h | the smoke test |
| flash-next | 7–11 h | similar decode, 125 vs 142 tok/s |
| qwen3.8-27b | 25–40 h | 35 tok/s decode |

These estimates are wide on purpose. The baselines and the pilot replace
them with measured numbers before stage 1 is scheduled.

**Compute matching will need a large N.** On c06, (b) used 6.4 K completion
tokens against (a″)'s 1.5 K at N = 1. A critique and revision round costs
about 0.9 K there, which suggests N ≈ 5 on short code. The pilot decides.

## 6. Driver smoke test (tooling only, not evidence)

Settings:
- qwen3.6-35b-a3b on `:8094`;
- arms a, a1, a2 (N = 1) and b;
- the chain c06 → c06f;
- output in the ignored `/runs/q02-smoke/`, never tracked, because it ran
  before the pre-registration;
- its outputs are never analysed. c06 and c06f stay in the bench. The agent
  has seen the 35B-A3B's outputs for those two prompts, and no other bench
  output.

What it showed:
- **Errors:** none.
- **Continuations:** one, in arm a1 on c06f (`length` at 8,192 tokens, then
  `stop`).
- **Labels:** every call came back labelled.
- **Reasoning:** text arrived in `reasoning_content` (a1 c06: 21.7 K
  characters).
- **Reasoning tokens:** the server reports no `reasoning_tokens`, so the
  count is 0 while `completion_tokens` includes them.
- **Hidden tests:** a1's c06 output failed 11 of 18. It subclassed `dict`
  and called `move_to_end`, a genuine model bug, so the tests discriminate.

| Prompt | a | a1 | a2 | b |
| --- | --- | --- | --- | --- |
| c06 | 18/18 | 7/18 | 18/18 | 18/18 |
| c06f | 31/37 | 20/37 | 22/37 | 27/37 |

## 7. Questions for the user

1. Approve the prompt list as it stands, or name the entries to change or
   replace.
2. Approve the pre-registration (§ 3). Two choices in it are specifically
   yours:
   - the code outcome rule (tests first, then the judge when the tests
     tie);
   - Holm across the six claims, or no correction. Holm protects the
     verdict, which is the re-plan trigger: under no correction, if the
     harness helps nowhere, one false "better" among six claims has a ≈ 26 %
     chance. But Holm cuts power at a true 0.70 from 81 % to about 60 % per
     claim. At a true 0.75 it still has 85 %. I recommend Holm, because a
     false positive would justify building Phases A–T on the harness.
3. Which bias guards (§ 4.1–4.4) to adopt.
4. Once approved, may sub-agents write the remaining 136 prompts with tests,
   references and checklists, following the exemplars, with every code
   prompt passing `check-bench`? Each batch would be reviewed before it
   lands.

## 8. Fold list on approval

- Q-02 Notes get § 3 verbatim, plus the accepted § 4 items, in one commit,
  before the pilot's run file.
- The manifest goes to `frozen: true` once all 140 entries are written and
  `check-bench` passes on both domains. That is a separate commit, and it is
  the bench's version of record.
- PLAN § Phase Q: the Q-02 bullet cites this note. Any § 4 slices go into the
  Scope of Q-02.

## 9. Flags for the user's mass review (bench as frozen, 2026-10-23)

The sub-agents and the coordinator raised these points while writing and
checking the bench. None was blocking. Each is a judgement the review can
reverse.

**Strictness: a correct-in-spirit answer can lose tests or items**
- **c01f:** `--json` may appear between file arguments, which needs
  `parse_intermixed_args`. This is stated in the prompt.
- **c08:** pre-releases compare by plain precedence, the opposite of npm.
  This is stated.
- **c09 / c09f:** about a third of the tests check error positions. The
  rules are given with worked examples.
- **c14:** a left-aligned column's separator is `:---`. This is stated.
- **c19:** a brute-force cron search runs about 1.5 M steps on the leap-day
  test and should still fit the 120 s timeout.
- **c25:** a model's solver bug that loops forever times out and scores 0
  for the whole file.
- **c31:** nodes need not be comparable, so `(dist, node)` heap entries
  without a tie-breaker fail.
- **c36 / c36f:** several tests check `SQLSyntaxError.pos`.
- **c37 / c37f:** a deliberately non-CommonMark markdown subset. All rules
  are stated.
- **c40:** holds expire as if a job runs at the start of each day. This is
  the subtlest rule in the bench.
- **c43:** the `evaluations` counter enforces incremental recalculation.
- **c46:** "Thompson NFA, no backtracking" is stated but not enforced,
  because a pathological test would time out the whole file.
- **c47:** the first error in reading order wins, so the parser must scan
  lazily.
- **c49:** the search order and the explanation format are fully specified,
  which makes it more about following a spec than designing a solver.

**Test counts**
- Follow-ups exceed the 20–40 range (c33f 65, c36f 75, c47f 64, c50f 66,
  c54f 65) because they copy the parent's tests whole.
- c52 (24) and c53 (25) sit at the low end of the range.

**Report checklists**
- The long reports carry 18–33 items, against the brief's 8–14.
- r39 (12 of 30 items) and r46 (9 of 29) weight arithmetic heavily.
- Exact heading counts: r45 has 12 "Settings" headings, r48 has 13
  "Errors" headings.
- Exact counts from transcripts, not stated in the prompt: r06 and r06f
  (decisions, action items).
- Hard length bounds without the 10 % widening, because the prompt says
  "under" or gives a range: r07, r08, r13, r14 and r15.
- Format-dependent items: r20's single 16-row table, r27's continuous
  numbering, r30's `<br>`-separated cells, r32's ID-led bullets, and
  r39's column order.
- Loose regexes that could rarely misfire: r23f (a level-1 title
  containing "point-in-time"), r24 (`15 %`), r25 (`young`) and r45 (the
  `E…` codes).
- Follow-ups that depend on the parent's answer: r06f (Android 9 left
  open) and r15f (assumes a self-hosted broker was chosen).
- **Checklists are a secondary score.** The report-domain claim rests on
  the judge (§ 3), so these flags affect the checklist table, not the
  six claims.

**Design choices to confirm**
- **Overlap entries.** c34, c39, c41, c45, c48 and c51, plus r09, r21, r37,
  r42, r47 and r51, ask for shared or repeated material on purpose. They
  have no `max_section_overlap` item.
- **r03f is a trap:** the cheapest new option breaks a stated requirement,
  and only the judge scores the recommendation.
- **r42 and r50 status definitions.** Their compliance statuses depend on
  definitions written into the prompts.

**Standard slice (v1-std)**
- 18 BigCodeBench-Hard tasks: 21 selected by the rule, 3 excluded because
  their tests import `faker`.
- 20 IFEval prompts, whose scoring is pending the user's choice of checker:
  the official checker (fetching code and four packages), the agent's own
  checker, or dropping that half.
