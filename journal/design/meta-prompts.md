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
