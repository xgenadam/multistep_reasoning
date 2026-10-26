# Meta-prompts, after-action reviews and a cheaper experiment loop (gemma study, 2026-10-25)

Exploratory, outside Q-02 (D-029's study on gemma-4-e4b). Status: planned; nothing here has run.
Decisions are logged at the end with their reasons, as they are made.

## Why

On v1's code prompts, gemma through the harness (b) scores below its own single call (a): 0.312 against 0.474 on the
same 48 prompts under the `names` keep rule (`small-models.md`). The user's suspicions (2026-10-25):
1. **The rules are explained in a way the model reads differently** than intended (the prompts, and the checks the
   code enforces but the prompts only half state, such as the keep rule).
2. **The orchestrator does not tie the work together** (decomposition into one-file fragments; the composer stitching).
3. **The validity criteria are wrong** (the keep rule rejecting good work, or accepting bad).

Two tools follow: an after-action review (AAR) that diagnoses losing turns from their traces, and meta-prompts, where
a model writes the instructions it will be given and only the format is fixed.

## The after-action review (`journal/baseline/aar.py`, outside the harness)

- **Input:** one turn's condensed trace from `arms.py run --trace-calls`:
  - the request and the plan;
  - per sub-task: what it was given and what it returned;
  - each composer attempt: its edits, and accepted or rejected with the reason;
  - the final files, and the failing hidden tests with the pytest tail;
  - a's passing answer, as a contrast.

  Repeated system prompts are cut and changes go in as diffs, keeping a turn to about 20–40K tokens.
- **Questions, answered in JSON:**
  - the first point it went wrong, as a step and call index;
  - its category: plan, missing information for a sub-task, the sub-task's work, composer, validity check (good
    rejected or bad accepted), scorer extraction, or other;
  - evidence, as verbatim quotes from the trace;
  - the smallest fix.
- **Against confirmation:**
  - The three suspicions are not offered as the only options, and "other" is always allowed.
  - A script checks every quote is in the trace, and discards a diagnosis whose quote is not.
  - The rest are spot-checked in the trace viewer.
- **Reviewers:**
  - **gemma** (can a small model see its own error? If so, a self-check step becomes an option);
  - **flash-next** for the bulk;
  - **Claude Sonnet** sub-agents on about 3–5 cases only, chosen to cover the categories found, to calibrate
    flash-next (the user, 2026-10-25).

  Agreement between reviewers is reported.
- **Output:** one row per turn, so the dominant category across the losing turns picks the first harness fix.

## Meta-prompts: the variants compete

A prompt template splits into what is **fixed** and what the model **writes**:
- **Fixed:** the JSON schema, the placeholders (request, outline, result, …), and the list of checks the code will
  run, which the written prompt must explain.
- **Written:** everything else.

The model is told the whole workflow (decompose → execute → compose → render) and what each step's output is used for.

The written prompt is validated before use:
- every placeholder present;
- the schema intact;
- every enforced check mentioned.

One that fails is rewritten, not run.

The variants (the user, 2026-10-25: "your way and mine ... frozen, and dynamic at run time and have them compete"):

| Variant | Who writes the prompt | When |
| --- | --- | --- |
| H | the current hand-written template (after D-031) | — |
| FS | gemma, for itself | once, frozen, committed and diffable |
| FT | flash-next, for gemma | once, frozen |
| DS | gemma, for itself | per request, at run time (one extra call per turn) |

DT (flash-next writing per request at run time) is left out: flash-next takes all four cards and gemma needs two, so
the two cannot serve at once.

**The code:**
- Each variant is a subclass registered as its own component (e.g. `decomposer: meta`, with
  `options.meta_prompt: frozen|dynamic` and a frozen prompt file).
- The current components stay the default and unchanged, so H is always available for comparison.
- The decomposer comes first, since the per-file fragmenting starts there. Then the composer.

## Making the experiment loop cheaper

Proposed, for the user's go-ahead (2026-10-25: "start thinking about optimizations we can make at the experimental
level"):

1. **Use both card pairs.**
   - gemma runs on cards 0–1; cards 2–3 sit idle.
   - A second gemma server on 2–3, on its own port, runs a second arm at the same time: about 2× the throughput for
     no other change.
   - `generator-server.sh` fixes one port per model, so it needs a port and container-name override.
2. **Batch by model.**
   - flash-next needs all four cards and a boot of several minutes.
   - Do all gemma work in one block. Then do all flash-next work in one block: writing FT, the bulk AAR, and any judging.
3. **A working subset, then confirm.**
   - Iterate on about 20 prompts chosen to discriminate:
     - prompts where b and a differ;
     - single-call pass rates of 20–60 %;
     - mixed strata.
   - Run them twice each, rather than all 70 once.
   - Confirm only the winner on all 70.
   - Comparisons are paired per prompt.
4. **Know the noise floor once.** Two runs of a on the same prompts differed by about 0.05. One A/A run of H on the
   subset sets the difference that counts, before any variant is called better.
5. **Screen cheaply, then tournament (successive halving).**
   - **Round 0, plans only:** every variant decomposes the subset. That takes seconds per prompt. Screen out variants
     whose plans are malformed or still split one file into fragments.
   - **Round 1:** the full pipeline on 10 prompts.
   - **Round 2:** the better half on the 20.
   - **Final:** the winner on all 70, against H and against a.
6. **Replay a recorded stage** (needs a small replay mode).
   - A composer-only change can start from a traced run's recorded plan and sub-task results.
   - That skips decomposition and execution, and holds them fixed, so the comparison isolates the composer.
7. **Trace every experiment run on the subset.** It costs only disk (ignored `intermediates/`), and every losing turn
   is then reviewable and replayable.

## Decisions and why

- 2026-10-25, the user: AAR reviewers are gemma plus a stronger one. flash-next takes the bulk and Sonnet a few
  calibration cases, because Claude usage costs the user and local GPUs do not.
- 2026-10-25, the user: meta-prompts as competing variants H / FS / FT / DS, frozen and dynamic. Kept as new components
  beside the old ones, so the old way stays for comparison or improvement.
- 2026-10-25, the agent: DT dropped. flash-next and gemma cannot be served at once on four cards.
- 2026-10-26 00:20Z, the agent, found while building the AAR:
  - **The decomposer is `self_critique`, the default.** Its critique prompt states a "Critical Rule" (any request with
    more than one logical action must be split) and a "Strong Rule" (3–5 sub-tasks for any request containing 'write'
    or 'create').
  - **`should_regenerate` forces a regeneration of every plan under 3 sub-tasks,** and the regeneration prompt asks
    for 3–5. So a one- or two-sub-task plan can never survive, whatever the base prompt's "Use 1 sub-task if …" says.
  - **For gemma it never fired:** all 139 of its plans in b-names and b-verbfb had 3 or more sub-tasks (mostly 4–6;
    27 of 70 over the base prompt's 5).
  - **Consequence for the meta arms:** they replace these rules too (the critique and regeneration prompts and the
    count threshold), or the hand-written rules override what the model writes.
- 2026-10-26, the agent: `aar.py` built.
  - `build` writes condensed Markdown traces per turn (`--lost-only` keeps the turns below the first `--compare`).
  - `review` asks any OpenAI-compatible server, using JSON mode rather than a schema, so the reviewer may write its
    own field order.
  - `summary` reports categories per reviewer and agreement between reviewers.
  - A diagnosis counts only when it gives a quote and every quote is in the trace, whitespace-insensitive.
- 2026-10-26, the agent: `decomposer: meta` built (`task_decomposition/meta_decomposition.py`).
  - **Options:** `options.meta_prompt: frozen|dynamic`, and `options.meta_prompt_file` for frozen.
  - **The fixed frame:** the request, then the written instructions, then the schema.
  - **The meta prompt** describes the pipeline as it runs today: what an executor sees, what the composer does, what
    the checks reject, how answers are scored.
  - **No critique or forced regeneration,** for the reason above. The H arm keeps them. A plain `decomposer: simple` run
    (the hand-written prompt, no critique) separates "the critique's rules" from "who wrote the prompt" if the meta
    arms win.
  - **Checks on written instructions:** too short, or restating the schema, means asked again, then refused.
  - **Frozen files** come from `journal/baseline/write_meta_prompt.py`, as
    `journal/design/meta-prompts/decompose.<writer>.txt` plus a `.json` of provenance.
  - **Dynamic calls** are counted as their own kind, `decompose_meta`.
- 2026-10-26, the agent, noted for the executor and composer stage: the executor's system prompt rule 5 ("Your result
  is the deliverable for THIS sub-task only, not the whole document") is another hand-written push towards fragments.
- 2026-10-26 00:11Z: FS written (`meta-prompts/decompose.gemma-4-e4b.txt`, first attempt, 3,238 characters).
  - **First read, the agent's, before any run:** gemma asks for "the smallest logical, independent, and executable
    steps possible", for "design must precede implementation", and for a "ruthlessly narrow" objective per sub-task.
    The meta prompt says that files are extracted and tested, but nothing in its instructions mentions files,
    interfaces or whole-file deliverables.
  - It names the schema's classes (`DecomposeThinkingStep`, `DecompositionPause`) rather than the `meta_type` values.
  - If anything, FS should fragment more than H. The tournament will show.

## The working subset (2026-10-26, the agent; the user approved the loop optimisations: "i approve")

**The 20 prompts:**

| Group | Prompts |
| --- | --- |
| Long | c38, c40, c43, c49, c51 |
| Short, b lost to a | c03, c07, c08, c18, c23, c28, c30 |
| Short, b at or above a | c12, c13, c15, c27 |
| Chains (parent and follow-up) | c01 → c01f, c06 → c06f |

**How they were chosen:**
- **Source:** gemma's three single-call runs (a at 8K, a relaxed, a1 relaxed) and b-names.
- **Rule 1, room both ways:** the single-call mean is between 0.15 and 0.85 (39 prompts qualify).
- **Rule 2, a mix:** both b's losses and b's wins are in, so a variant that only fixes one kind still shows up.
- **Rule 3, longer prompts:** the long ones are in, where b collapsed (0.0 on all eight).
- **Rule 4, chains:** a follow-up runs with its parent.

**Each runs twice.** Single-call scores on one prompt swing widely between runs (c11 spans 0 to 1.0 over three runs;
11 of the 39 span 0.75 or more), so per-prompt differences need repeats.

**Rejected:**
- All 70 once: too noisy per prompt, and 3.5× the cost.
- Picking by b's losses only: would favour any change that helps where b fails, even at a cost elsewhere.

**Second gemma instance:** cards 2–3, port 8102 (`INSTANCE=b` in `generator-server.sh`), loading the model through
the symlink `~/models/small-gemma-4-E4B-it-GGUF-inst-b`. The running b-off driver ends with a per-model-path
`pkill -f`, which would otherwise kill this instance too.

## Round 0 (plans only), gemma, 2026-10-26 01:02Z

**Setup:** 20 prompts × 2 reps per variant, no errors, no fallbacks
(`runs/20261026T010235Z_plan-screen_round0-gemma.json`).

| Variant | Median sub-tasks | Median per expected file | One sub-task per file | Range |
| --- | --- | --- | --- | --- |
| H (self_critique) | 5 | 4 | 1 of 40 | 3–8 |
| S (simple, no critique) | 5 | 4 | 2 of 40 | 3–8 |
| FS (gemma, frozen) | 6 | 5 | 0 of 40 | 3–9 |
| DS (gemma, per request) | 5.5 | 5 | 3 of 40 | 3–13 |

**Findings:**
- **The critique and its forced regeneration do not drive the fragmenting:** S fragments as H does.
- **Gemma, writing its own instructions, keeps the staged plan or makes it worse,** frozen or per request. Its c01
  instructions split wordcount.py into "core counting", "argument parsing" and "output formatting" tasks.

**What the screen can and cannot say:** it was to drop malformed or fragmenting variants, but every variant fragments
and none is malformed. So none is dropped on plans alone. The full pipeline (round 1) decides whether fragmenting is
what costs b the score.

**Variants added for round 1 (the agent):**
- **FT (flash-next, frozen), to test whether a stronger writer avoids the split.** It is written in the flash-next block.
- **HW, a hand-written "one sub-task per file, each delivering the whole file" variant of S.** This is the "whole
  files per sub-task" option deferred under D-031, now a control. If HW beats S, the split matters. If FT beats FS,
  the writer matters.
- 01:33Z, HW screened (`runs/20261026T013319Z_plan-screen_round0-gemma-HW.json`): median 1 sub-task (per file 1),
  one sub-task per file in 31 of 40 plans, no errors.
  - **Gemma follows the instruction closely.** The fragmenting comes from what it is told (and from what it tells
    itself, in FS and DS), not from something it cannot help.
  - **Whether whole-file plans score better is round 1's question.** A one-sub-task plan for a one-file program is
    close to a single call with the harness's overhead around it.

## H on the subset, and the noise floor (2026-10-26 01:26Z)

**The run:** `20261026T001500Z_work-H_gemma-4-e4b.json`, at commit 5d6bf02 (the decomposition prompt without the climate example, D-031),
`names` + fallback, relaxed budgets, traced.

| Arm, same 20 prompts | Mean pass |
| --- | --- |
| H (mean of 2 runs) | 0.307 |
| b-names (old prompt) | 0.265 |
| a | 0.572 |
| a1 | 0.572 |

1 of 40 turns errored, and extraction was incomplete on 11 of 40.

**Noise:** H's two runs scored 0.259 and 0.354; per prompt, \|r0 − r1\| averages 0.25. A variant needs to beat H by
more than about 0.1 on this subset before it counts. The leaders may need a third run.

**Round 1 schedule (the agent):**
- Instance 2 runs HW, then S.
- Instance 1 runs FS, then DS, once b-off ends.
- FT follows the flash-next block.

**Why HW goes first:** it is the clearest test of whether fragmenting is what costs b.

**First sign, in HW's c03:** with one sub-task, the composer still retypes the whole file under `names` and breaks
it (an unterminated f-string). Whole-file plans may need the composer to keep the file as written. That is a
question for the AAR.

## Round 1 (full pipeline, 20 prompts × 2, gemma, traced), 2026-10-26 05:00Z

**Setup:** H at 5d6bf02; HW, S, FS and DS at c7472bd. `names` + fallback, relaxed budgets. Run files (1.7–2.8 MB each, over rule 8, untracked pending the user's trim-or-commit call) are
`journal/baseline/runs/*_work-<variant>_gemma-4-e4b.json`.

| Variant | Mean (2 runs) | Run 0 / run 1 | All pass | Extraction incomplete | Errors | vs H better / worse | Wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HW, hand-written whole-file | **0.401** | 0.332 / 0.470 | 3 | 9 of 40 | 0 | 9 / 7 | 52 min |
| S, simple, no critique | 0.340 | 0.320 / 0.360 | 2 | 10 | 4 | 8 / 6 | 67 min |
| H, self_critique (baseline) | 0.307 | 0.259 / 0.354 | 2 | 11 | 1 | — | 71 min |
| DS, gemma per request | 0.287 | 0.212 / 0.362 | 1 | 12 | 3 | 8 / 8 | 77 min |
| FS, gemma frozen | 0.197 | 0.267 / 0.127 | 1 | 13 | 5 | 4 / 12 | 80 min |
| a, single call (one run) | 0.572 | | | | | | |

- **HW leads by 0.094 over H, at the noise floor (about 0.1).** It is also the fastest arm: one sub-task per file means
  fewer compose and executor calls. It is still far below a.
- **Gemma writing its own planner instructions does not help:** FS loses to H, worst of all, and DS ties H. That
  matches round 0: its instructions keep or worsen the split.
- **The critique adds nothing:** S is at or above H.
- **No variant comes near a single call on gemma.** The decomposer is not the whole problem. The composer
  (retyping, breaking files) and extraction (9–13 of 40 incomplete everywhere) are the next suspects, for the AAR.
- **Box:** GPU1 reached the watchdog's warn level, 83 °C, twice at 03:36–03:37 (fan 80 %, 248 W). No trip.
