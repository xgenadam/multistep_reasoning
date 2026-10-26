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
- 2026-10-26, the agent: E-1 replays recorded results instead of running executors.
  - Why: inputs are held fixed, so only the integration differs, and it is cheap.
  - Rejected: live runs first, where executor noise (per-prompt |r0 − r1| ≈ 0.25) would swamp the integration
    effect.
- 2026-10-26, the agent: the agent's earlier claim that "the composer destroys work" was too strong. The direct
  scoring shows it rescues format in 13 of 21 turns and damages content in 4. The design keeps the rescue (now
  mechanical) and removes the rewriting.
