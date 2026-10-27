# Lead and workers: a redesign of composition and collaboration (2026-10-26)

Status: design, hashed out with the user on 2026-10-26; nothing built. Exploratory, beside the current harness.
The current components stay the default and the baseline (Q-02's harness is frozen until its verdict). Each piece is
built as its own variant and measured alone (the user: "agreed!" to one piece at a time).

## Why: what the traces showed

Evidence from the gemma study (`meta-prompts.md`, `small-models.md`), traced runs H and HW on the 20-prompt subset:

1. **The composer cannot see what it must place.**
   - It gets the full request, every sub-task's name and objective, and the current sub-task.
   - The sub-task's result comes only as `preview_text`: the first 400 and last 200 characters of anything over 800.
   - The document comes as an outline (ids, kinds, titles, lengths) plus a summary.
   - In HW c13 it saw 600 of 5,466 characters of a correct `ratelimit.py`, retyped a 3,948-character file from the
     request, and dropped a `_refill()` call. Tests went from 13 of 13 to 2 failing.
   - The preview dates from the `verbatim` design, where the composer only pointed at the result
     (`body_source="current_result"`). When `names` (D-030) invited retyping and refactoring, the full text was not
     given with it. That was the agent's oversight.
2. **The rules contradict the format.**
   - Every bench prompt asks for each file as a path line followed by a fenced block.
   - Composer rule 7 says a file part's body is raw code with no fences, because the renderer adds them.
   - So copying a result as written is either a double fence (file part) or prose (section). Retyping is the only
     "legal" path. The model works around rigid rules instead of using judgement (the user).
3. **Both fallbacks add code as `kind="section"`.** That covers "the composer returned no ops" and "all retries
   failed", both through `_fallback_add_part`. The scorer finds no files there (HW c43: 3 of 4 modules lost, 0 of 3
   tests).
4. **The composer is both rescuer and vandal.** Scoring HW's 21 single-sub-task results directly against the
   composed answers:

   | Scored | Mean pass | Extraction OK |
   | --- | --- | --- |
   | Raw result | 0.281 | 10 of 21 |
   | After the composer | 0.577 | 20 of 21 |
   | Single call | 0.645 | |

   - It helped in 13 turns, mostly by repackaging unfenced code into file parts.
   - It hurt in 4, rewriting content: c03 0.61 → 0.00, c28 0.71 → 0.00.
   - Executors' output format is unreliable: a path line then bare code, or bare code alone.
5. **Executors do not see the plan.**
   - In step 1 of 4 a worker cannot know what steps 2–4 will do. So it writes stubs for them, or writes them itself
     and later steps duplicate them (Sonnet on H c08).
   - Rule 5 ("the deliverable for THIS sub-task only") adds to it.
6. **Code travels inside JSON strings,** in the executor's `result` and the composer's patch bodies.
   - HW c43's first executor attempt ran away to 32,768 tokens of `\b`.
   - 21 (H) and 15 (HW) executor replies were empty or unparseable.
7. **The planner fragments because it is told to, and whole-file plans help.**
   - Gemma follows instructions closely: HW's rule gave one sub-task per file in 31 of 40 plans.
   - HW was the best round-1 variant: 0.401 against H's 0.307, at the noise floor.
   - Gemma's and flash-next's own instructions both ask for staged splits.

## The design

### Roles

- **The lead plans the top level** (the user, 2026-10-26). It splits the request into coarse units, reviews each
  worker's result, integrates it, keeps shared notes, and decides when to re-run or split.
- **Each worker plans its own part.** It executes a unit, plans within it, and collaborates with the lead.

### Lazy decomposition

- **Start coarse:** often one unit per file, sometimes one for the whole request.
- **Split only a unit whose result fails the lead's review,** planned with the failed attempt in view.
- **Units may group related work** where the lead sees it belongs together (the user: "have a sub agent do them
  together").
- **Caps:** split depth ≤ 2, and a split budget per turn.
- **Example, c43** (4 files): 4 units. `formula.py` comes back broken, so it is split into lexer, parser and
  evaluator, each told what failed, each writing into `formula.py`.
- **Rejected:** today's eager split, chosen blind before any work. It cut single files into 4–6 fragments.
- **The risk:** everything rests on the lead's review telling good from bad. E-1 measures that.

### Workers see the plan

Every unit's name and objective, marked *done* / **yours** / *later*, with one sentence on what is theirs. Rule 5
becomes "deliver complete, working files: new ones, or whole updated versions of existing ones".

### Staged merge, with edits before and after (the user)

1. **Mechanical split of the result into incoming parts.**
   - Each path line plus fenced block becomes a `file` part: title = path, body = the inside of the fence.
   - A path line with bare code under it, or bare code under a unit that names one file, becomes that file too.
   - Prose becomes a `section`.
2. **The lead edits the incoming copy:** it sees it in full and patches it (strip a fence, rename, cut a demo
   block, fix a slip).
3. **Place:** a file with the same path replaces its part, and new files are added. The lead sees a diff of the
   document against the staged document, with the full bodies of every part touched.
4. **The lead edits the document:** merge, move, delete, patch.
5. **The default is to accept.** If the lead does nothing, the mechanical merge stands, so work survives without
   any keep rule.

**No keep-rule gate and no lint gate.** The user: running linting on parts is not the problem; give the model
freedom. A failing parse or a lost definition is shown to the lead as information, not enforced. Coverage is still
logged for analysis.

**Fallbacks add code as `file` parts,** never sections.

### Collaboration

- **Worker → lead,** during execution: `ask` goes to the lead instead of the stateless document oracle (used 3
  times in H), e.g. "does `sheet.py` define `Cell` yet?"
- **Lead → worker,** during the merge (the user): ask about intent, request a fix (the worker revises in its own
  context, the revision goes back through the mechanical merge), or confirm before a structural edit.
- **Cap:** about 2 exchanges per merge, and a few questions per unit.
- **Logs:** every exchange is stored in full in the trace. The lead's context holds only a one-line summary it
  writes per exchange, so its window does not blow up (the user).
- **The collaboration log is a first-class record** (the user, 2026-10-26: "do we log the collaborations? we
  should be"):
  - **One file per exchange,** under the turn's intermediates: `collab/NN_<unit>_<direction>.json`, where
    direction is worker→lead (during execution) or lead→worker (during the merge).
  - **Each holds:**
    - the unit and step;
    - who opened it, and why (question, fix request, confirmation);
    - every message in order, in full;
    - the call indices of the model calls behind each message, linking to `calls/`;
    - the outcome: answered, fix delivered and merged, or declined;
    - the lead's one-line summary;
    - any note it pinned as a result.
  - **Written whether or not `--trace-calls` is on.** Exchanges are small, and they are the data for judging the
    collaboration.
  - **Shown in the trace viewer** inline at the step where it happened, and included in the AAR's condensed trace.
    The lead's search reads these same files.
  - **Pinned notes get their own log:** what was pinned, when, by which exchange, and every prompt it was later
    added to.
- **Search:** the lead can search past collaborations (TF-IDF over the summaries and logs, local, no new
  dependencies) and read one in full, to find commonality instead of reinventing (the user).
- **Pinned notes:** decisions the lead chooses to carry forward ("helpers live in `utils.py`"). They go into later
  lead prompts and into later workers' prompts as "decisions so far" (the user: "appending to its compose prompt
  history").

### Plain text instead of JSON for code

1. **Workers use the model's native tool calling,** so the final answer is plain text. llama.cpp with `--jinja`;
   to check per template, for gemma and for flash-next on vLLM.
2. **Fallback:** a JSON lookup loop ending in `finish`, then one plain-text "write your deliverable" call.
3. **The lead edits** with SEARCH/REPLACE blocks in plain text instead of JSON patch ops with code in strings.

### Later: more control of the loop for the lead

Re-run a unit with feedback (first), then add, skip or reorder the remaining units, then finish early, each capped.

### Later: recursive decomposition and exploration rounds (the user, 2026-10-27)

- **Recursive decomposition:** a unit may be split, its parts split again, and so on, with caps. This generalises
  lazy decomposition from one level to a tree.
- **Preliminary exploration rounds:** before planning, the lead explores. It reads the request closely, lists
  ambiguities, sketches interfaces, and perhaps asks a worker for a quick probe. Then it plans from what it found.
- The user: "early days for our harness … we can really tweak the crap out of it … a bit of a rabbit hole".

### Hypothesis: stronger models gain more because they plan better (the user, 2026-10-27)

- "More powerful models benefit due to being better planners. Because they can look ahead more they come up with
  better plans. For smaller models it might be that a simpler loop works best."
- **Consistent with the data so far:**
  - flash-next gains about 0.43 from the harness (H 0.862 against a 0.436);
  - gemma loses about 0.17 (best variant HW 0.401 against a 0.572);
  - gemma does best with the simplest plan (HW, one unit per file).
- **Testable:**
  - compare plan quality across models on the same requests (AAR `plan` diagnoses, and plans-only screens scored
    against outcomes);
  - try a deliberately simple loop for gemma: one unit, then review and fix.

### Later: learned planning and execution policies per model, not fine-tuning (the user, 2026-10-27)

- **What:** a genetic algorithm or reinforcement learning (Q-learning style) over the harness's decisions, tuned per
  model. The model's weights are untouched; the policy around it is learned.
- **Shape, a first sketch:**
  - **State:** request features (files asked for, length, follow-up, domain) and pipeline state (units done, review
    verdicts, retries used, tokens spent).
  - **Actions:** answer directly; plan coarse or fine; split, re-run or merge a unit; ask a worker; pick a variant
    (the routing question as an action).
  - **Reward:** hidden-test pass rate, minus a cost term in tokens.
  - **Learning:** a genetic algorithm over configuration "genomes" (prompts, thresholds, caps, variant choices) is
    the simplest start, since every run file is already an evaluation. Tabular or approximate Q-learning over the
    actions is the step after.
- **Feasibility:**
  - every traced run is already a logged episode (states, actions, outcomes);
  - the replay mode (`integration_replay.py`) makes integration-level actions cheap to evaluate offline.
- **Risks:**
  - overfitting the bench: hold out prompts;
  - noise: per-prompt |r0 − r1| is about 0.25, so rewards are noisy, and averaging over repeats or fixed sampling
    helps;
  - cost: an episode is a full turn.

### Later: routing (the user, 2026-10-26: "this is going to turn into a routing problem")

Which harness, or which variant of one, to use depends on the request and on the model. Tuning per model is a topic
of its own (the user).

The evidence so far, on the 20-prompt subset:

| Model | Long prompts | Short prompts |
| --- | --- | --- |
| flash-next | H best (0.917; OpenCode 0.790; single call 0.071) | OpenCode 0.862, H 0.844, HW 0.757 |
| gemma | every harness variant at or under 0.14; single call 0.096 | single call best |

A router could start as rules read off such tables (request features such as files asked for, length and follow-up;
the model), and later be learned from the run logs and AAR rows. It needs the per-variant traces we already keep.

### Later: mixing models across roles (the user, 2026-10-26: "worth experimenting with later")

For now every role in a run uses one model. Mixing is a later experiment, for example:
- a strong lead over small workers (flash-next leading gemma), or the reverse;
- a small model for cheap roles (summaries, mechanical review) under a strong planner.

It asks something different from the current study: what each role needs, not what one model can do. It needs both
models served at once. Flash-next takes all four cards today, so it needs flash-next on fewer cards, or a smaller
strong model.

## Experiments

### E-1: integration replay (first)

No executor runs. Every traced turn's sub-task results are replayed in order, so only the integration changes.

- **Cases:** the 80 traced turns of H and HW. The 21 single-unit turns give the cleanest read.
- **Arms:**

  | Arm | Integration |
  | --- | --- |
  | M | Mechanical merge only, no model |
  | C | Today's composer, replayed on the same inputs |
  | L | Staged merge + lead review (full result, diff, plain-text edits, accept by default) |
  | L+W | L plus up to 2 lead ↔ worker exchanges during the merge |

  - The worker is resumed from its recorded messages, so inputs stay identical until the lead asks.
  - **Models:** one model for every role in a run (the user, 2026-10-26: "keep the same model for all the agents,
    not mix and match"). Each model replays its own traced results:
    - gemma: H and HW, already traced;
    - flash-next: needs its own traced H and HW runs on the subset first, because its Q-02 runs predate tracing.
- **Measures:**
  - hidden-test pass rate of the final document;
  - steps that leave the code worse than its raw result, against steps that improve it;
  - the size of the lead's edits;
  - calls and tokens.
  - For L+W: how often the lead asks, whether that step's tests improved, and whether the asks were justified
    (aimed at results that really were defective).
- **The lead's judgement:** its "this result is bad, re-run or split" calls, checked against the tests. Precision
  and recall tell whether lazy splitting can work.

### E-2: collaboration and lazy decomposition (after E-1)

Workers get the plan, `ask` to the lead, pinned notes and the collaboration search, plus lazy splitting with caps.
Live runs on the long multi-file prompts, both models, same-model pairs.

## Build order (one variant each, each measured)

1. **Replay mode:** a recorded turn's results, fed in order to a chosen integrator.
2. **Mechanical merge,** coping with bare code.
3. **The lead-review composer,** as a new component beside `document`.
4. E-1 arms M, C, L. Gemma first, on its traced runs. Flash-next after its own traced H and HW runs.
5. **Lead ↔ worker exchange during merge;** E-1 arm L+W.
6. Executors see the plan.
7. Native tools / plain-text deliverables.
8. Collaboration, notes, search; lazy decomposition (E-2).

## Decisions and why

- 2026-10-26, the user: the lead plans the top level and workers plan their own parts. Collaboration history is
  stored but summarised for the lead, and is searchable.
- 2026-10-26, the user: the composer gets more freedom and fewer rigid rules. It edits a copy of the result before
  placing it, and the document after. No lint gate.
- 2026-10-26, the user: workers get the plan, or a summary of it, with their own part made clear.
- 2026-10-26, the user: the breakdown may group related work, and an unsatisfactory result can be broken down again.
- 2026-10-26, the user: workers can query the lead, the lead can query workers during the merge, with conversation
  logs, and the lead can pin notes for future units.
- 2026-10-26, the user: experiment on both models with a narrow first experiment; one piece at a time.
- 2026-10-26, the user: the same model for every agent in a run, no mixing.
  - Consequence: E-1 has no cross-model lead arm, and flash-next gets traced H and HW runs of its own to replay.
  - Mixing models across roles is kept as a later experiment (the user: "worth experimenting with later"); see
    "Later: mixing models across roles".
- 2026-10-26, the agent: E-1 replays recorded results instead of running executors.
  - Why: inputs are held fixed, so only the integration differs, and it is cheap.
  - Rejected: live runs first, where executor noise (per-prompt |r0 − r1| ≈ 0.25) would swamp the integration
    effect.
- 2026-10-26, the agent: the agent's earlier claim that "the composer destroys work" was too strong. The direct
  scoring shows it rescues format in 13 of 21 turns and damages content in 4. The design keeps the rescue (now
  mechanical) and removes the rewriting.

## Inputs for E-1 on flash-next: its own traced H and HW (2026-10-26 21:22Z)

**Setup:** the 20-prompt subset × 2, worktree c7472bd, `names` + fallback, relaxed budgets, `--jobs 6` on `:8090`.

| Arm | Mean | Run 0 / run 1 | All pass | Extraction incomplete | Errors |
| --- | --- | --- | --- | --- | --- |
| H | **0.862** | 0.894 / 0.831 | 26 of 40 | 0 | 0 |
| HW | 0.727 | 0.619 / 0.835 | 19 of 40 | 6 | 0 |

The same prompts in Q-02 (8K budget, `verbatim`): b 0.710, a 0.622.

- **The harness at these settings gains about 0.15 on flash-next.** Three things changed at once (relaxed budgets,
  `names` + fallback, the decomposition prompt without the climate example), so the cause is not yet separable. A
  single call at the relaxed budgets on the subset is the missing comparison.
- **HW helps gemma (0.401 against 0.307) but hurts flash-next (0.727 against 0.862):** HW better on 5 prompts, worse
  on 9.
  - HW brings extraction failures to flash-next (6 against 0).
  - The whole-file rule is not a universal fix. What helps depends on the model, which E-1 should keep in mind.
  - HW's two runs differ by 0.22, so part of the gap may be noise.
- 21:41Z, flash-next's single call at the same relaxed settings on the subset (arm a, × 2, `--jobs 6`):

  | Arm | Mean | Long | Short | Extraction incomplete |
  | --- | --- | --- | --- | --- |
  | a | 0.436 | 0.071 | 0.557 | 16 of 40 |
  | H | **0.862** | 0.917 | 0.844 | 0 |
  | HW | 0.727 | 0.637 | 0.757 | 6 |

  - **H beats a on 16 prompts and loses on 1.** The relaxed budgets did not lift the single call: Q-02's a, at 8K,
    scored 0.622 on these prompts.
  - **14 of a's 40 replies are not answers.** Under 500 characters each, every one ends "stop", and they begin
    "I'll start by exploring the existing project structure…". Flash-next acts as an agent expecting tools, and
    stops.
  - Q-02's a has the same failure, in 32 of 140 replies. That weakens the single-call baseline in Q-02 too, and is
    worth a Q-02 note.
  - **Even on the 26 turns a did answer, H wins:** 0.924 against 0.671.
- 21:40Z, `integration_replay.py` (build step 1), arm C, tested on flash-next's H for c13, c06 and c06f, two runs
  each:
  - all 6 replayed, follow-ups starting from their parents' replayed documents;
  - scored c06 18/18, 18/18; c06f 34/37, 30/37; c13 13/13, 13/13.
  - The agent first wrote it as `journal/baseline/replay.py`, which overwrote the 0-03 op-log forensics tool of
    that name. It was restored from git at once, unchanged, and the new tool has its own name.

## The established-harness comparison: OpenCode (the user, 2026-10-26)

- **Why OpenCode:** the user proposed comparing against established harnesses. DeepSeek's full harness was rejected
  by the user ("so many tools that would make the comparison unfair"), and OpenCode chosen ("ok, opencode it is").
- **Version:** v1.19.3, the official image `ghcr.io/anomalyco/opencode@sha256:6ebc13097f2381301220abe9d1b2a54f50cd1603a910dc1c66e93d8f2c4e8ebb`.
  - Released 2026-10-16. The newest, v1.19.4, was 4 days old and was skipped.
- **Isolation:**
  - OpenCode runs on an internal podman network (`oc-internal`) with no route out (`api.github.com` does not resolve).
  - Its only peer is `oc-proxy` (`journal/baseline/llm_proxy.py`, standard library only, in
    `python:3.12-slim@sha256:a0f5…6704`), attached to both `oc-internal` and the bridge, forwarding to the model
    server.
  - Nothing of OpenCode is committed.
- **Recording:**
  - The proxy logs every request and reply per run, labelled by the base URL's first path segment
    (`http://oc-proxy:9000/<label>/v1`), with token counts (`include_usage` added to streamed calls).
  - That makes its traces and costs comparable to ours, since our call recording does not see a third-party
    harness's calls.
- **Tools, two tiers:**
  - **Like-for-like:** OpenCode's own `build` agent and system prompt, with `bash`, `webfetch`, `websearch`, `task`,
    `external_directory`, `lsp`, `skill` and `question` denied. Verified from the requests: the model is offered
    `edit, glob, grep, read, todowrite, write` only. `todowrite` (its planning checklist) is kept, as the nearest
    thing to our planner.
  - **Real-world:** `bash` allowed, in a derived image with Python 3.12 added (the official image is Alpine, with
    no python3).
- **Smoke test, flash-next, c13, like-for-like:**
  - 6 calls, the first OpenCode's own conversation-title call;
  - 17 s;
  - `ratelimit.py` written; 13 of 13 hidden tests.
- 22:05Z, the real-world tier's image `opencode-python:1.19.3` (`journal/baseline/ext/opencode-python.Dockerfile`):
  the pinned OpenCode image plus Alpine 3.24.2's python3 3.14.8, py3-pytest 9.0.3 and bash 5.3.9.
  - The agent's own runs use Python 3.14. The prompts ask for the 3.12 standard library, and hidden tests run on
    3.12, as for every arm.
- 22:07Z, `journal/baseline/external_harness.py` (the driver) tested on flash-next, like-for-like, one run:
  - c01 12/16; c01f 23/28, continuing c01's session and directory; c13 13/13.
  - The test's run files were deleted. Full runs, both tiers, on the subset × 2, follow.
- 22:55Z, the user's calls:
  - **Four single-card gemma servers:** approved, for the next gemma block.
  - **Proxy records cached tokens:** yes. The server must report them first (vLLM `--enable-prompt-tokens-details`;
    flash-next's lane does not send `prompt_tokens_details` today). The proxy logs the usage block whole, and the
    driver now totals `cached_prompt_tokens` when present.
  - **The speed test, prioritising speed:** `journal/baseline/concurrency_bench.py` replays 24 of OpenCode's
    recorded longest requests (512 output tokens each) at 3 and 6 concurrent, alternating, after a warm-up. The
    real-world tier then runs at whichever is faster (`runs/small-models/oc_rest2.sh`).
    - Rejected: a second hour-long OpenCode run at 3 for the comparison. Slow, and confounded by the turn mix.
  - **No kill-test decision** ("it's making progress now").
  - **The large run files** (75 files, 94 MB, none with third-party text) are committed as they are.
- 22:45Z, vLLM counters, the agent:
  - During OpenCode's like-for-like run the prefix cache hit about 95 % of prompt tokens (its prompts are
    append-only: 58 of 59 consecutive calls), with no new preemptions. The 168 came from earlier runs.
  - The likely bottleneck is generation over about 100K-token contexts, 6 at once. That is what the speed test
    measures.
