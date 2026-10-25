# Idea: freeform first, JSON second (the user, 2026-10-24)

- **Status:** a note to act on later. The harness is frozen for Q-02 at
  `a82c5b7` (D-022), so nothing changes until Q-02's verdict. Take it up at
  the re-plan point (Q-03) or as an A-phase ticket.
- **Prompted by:** the 8 of 140 harness failures in Q-02 stage 1's flash-next
  (b) run (`journal/baseline/runs/20261024T031144Z_q02-s1-b_flash-next.json`).

## The idea, in the user's words

> We are forcing json on the task breakdown, but depending on the complexity
> of the task this might cause the model to fail to generate valid json, its
> not guaranteed. one approach, token inefficient, is to not force json on
> the first pass, allow the model to be more freeform in generating a reply,
> i.e generate sub tasks freeform as a normal response with sections that
> contain the info we require. Then we have a second call that feeds that
> freeform response back into the llm but constrain it to json there...

So there are two calls: (1) the decomposition, or any structured step, written
as ordinary prose with fixed sections; (2) a short call that turns that prose
into the schema, constrained to JSON.

## What the code does now (checked 2026-10-24)

- Structured calls go through `llama_utils.get_streamed_json_response`:
  instructor `Mode.JSON` (prompted JSON plus parse/validate retries, up to 5).
  This is **not** grammar-constrained decoding, so valid JSON is not
  guaranteed, as the user says.
- **Output caps.** The harness sends `max_tokens=8192` on every call
  (`harness.MAX_TOKENS`). Outside the harness, the OpenAI-client path sends
  none, so the server's default applies (≈ 2,804 on `:5000`, measured in
  0-14). A 2,048-token JSON cap existed, but only the text-generation-webui
  extension read it (`oobabooga_extension/script.py:663`), so it never
  applied to Q-02. **Removed on master 2026-10-24 at the user's request**
  (`llama_utils.get_streamed_json_response`). Q-02 keeps running from
  `a82c5b7`, where it is present but inert. The critique's 1,024 limit
  (`self_critique_decomposition.py:150`, prose, extension only) is
  unchanged.
- The composer (`document_composer.py:219`) retries 3 times on a
  *document-rule* error, then raises `DocumentApplyError`, and the whole
  turn fails.

## What the 8 failures were

All 8 were `DocumentApplyError("composer failed after 3 retries: …")`. Those
are ops that parsed and validated but broke a document rule, not invalid JSON:
- "sub-task result was not kept in part …": 6;
- "body_source=current_result was used but the payload is not in the
  document": 1;
- "part id already exists": 1.

7 of the 8 were report prompts.

### The rule "sub-task result was not kept"

`document/integrity.py:assert_payload_kept`, run on every compose attempt
after the ops apply to a clone. Its purpose: a sub-task's result must never
be lost or silently rewritten in composition. The composer can place the
result in two ways:
- `body_source: current_result`: the document takes the executor's text
  verbatim. Kept by construction.
- A literal `body` on add, append, update or insert: the model retypes the
  text in its JSON. The rule then requires the executor's **entire** result
  to appear as an exact substring of that part's body, with the outer code
  fence allowed to differ. Anything else fails: a trim, a reworded
  sentence, a dropped heading, a split across two parts, a changed
  whitespace run.

In the flash-next (b) run (console log `runs/q02-stage1-logs/flash-next_b.log`, git-ignored)
the rule fired on 40 compose attempts; retries recovered most of them and 6
turns failed. Other attempt errors: "part id already exists" 7, "anchor not
found" 2, `body_source` without the payload 1, unknown part id 1. The
composer also returned no ops 47 times and fell back to a verbatim add.

A failed turn records nothing: the run file has `output` empty, no
document and no calls, so the two finished parts of r30 (a 3-step SWOT
report that failed at its last step, "Compose Summary and Finalize
Document", into part `summary`) are lost, and the failing ops are not kept
for diagnosis. Two later questions, separate from the user's idea:
- should a last-step compose failure fall back to a verbatim add (the
  no-ops path already does) instead of failing the turn;
- should the run file keep the failing attempts' ops.

### The user's view on the rule (2026-10-24)

> I think its fine for the composer to retype it. Consider tasks that might
> have some overlapping scope, if we stick to fully copying it, then its just
> going to result in bloated responses with duplicate information

How the rule bears on overlap now:
- The *new* result must go in whole. Overlap with an earlier part can only
  be removed backwards: a later step's `replace` or `delete` on an earlier
  part is not checked, and neither is the end-of-turn consolidation pass
  (`consolidate`, 0-06, off by default; Q-02's arm c tests it against b).
- So the design today is "compose verbatim, dedupe afterwards". The user's
  view is "dedupe while composing".
- What the rule guards against is still real: the composer sees summaries
  and a few attached parts, not the whole document, and a retype can drop
  or degrade content silently (worst for code).

Options for the later ticket, each tested with and without like the
two-pass idea:
1. Allow literal bodies to differ from the result, replacing the
   exact-substring check with a coverage measure that is logged, not
   enforced (for example, the share of the result's sentences or lines
   that survive), so silent loss shows up in the run file.
2. Ask the composer to declare what it left out and why ("duplicates part
   X"), recorded in the op log, and fail only on undeclared loss.
3. Keep `file` parts verbatim (retyped code breaks quietly), and relax the
   rule for prose parts only.
4. Whatever the rule, a final compose failure falls back to a verbatim
   add instead of failing the turn.

Q-02's c-vs-b result tells us how much dedupe-afterwards buys, which is
the baseline for any dedupe-while-composing variant.

## Later work (after Q-02's verdict; the harness is frozen until then)

### Measure first (no new runs needed)

From Q-02's run files, `/intermediates/` and the console logs:
1. Count instructor parse and validation retries per call kind (decompose,
   critique, compose, executor), if the instrumentation records them.
   Otherwise, compare calls per turn with the expected count.
2. Response lengths per call kind, and calls that stopped on `length`.
3. The composer's failed attempts by error class, including the ones a
   later retry fixed, across all three generators.
4. Split each count by prompt length and stratum, to test "depending on the
   complexity of the task".

### The two-pass approach: investigate, with and without

The user (2026-10-24): investigate it later; comparing results with and
without it, qualitatively as well as by counts, is part of developing the
harness. So it is an experiment with a control, not a fix to adopt:
- arms: the current single JSON pass vs freeform-with-sections then a
  constrained JSON conversion, on the same prompts and generator;
- compare the outputs' quality (judged and read), the failure counts above,
  and tokens and critical-path calls per turn (D-025);
- start with the decomposer; the composer only if its errors grow with
  complexity;
- material prompt changes need a re-baseline (D-007).

Other variants worth the same with/without treatment: grammar-constrained
decoding (vLLM `guided_json` / `response_format`, llama.cpp `json_schema`;
valid JSON in one call, but no help to reasoning; check the instrumentation
seam still counts it, O-03), and thinking on for structured calls (free
reasoning before the JSON in the same call; Q-02's (a′) arm tests thinking
only for single calls).

## Built 2026-10-25 (the user: test the smoke model both ways)

- **Correction to the start of this note:** every JSON call already sends
  `response_format: {"type": "json_object"}` (instructor 1.3.2 `Mode.JSON`
  sets it), which vLLM and llama.cpp treat as "decode valid JSON only". So
  syntax was already forced; the **schema** was not (it is only described
  in the prompt, then validated and retried).
- `options.structured_output` (+ `structured_output_by_step`), set per run
  with `--set`:
  - `json_object` (default, every run so far): as above;
  - `json_schema`: the response format is the schema of the model instructor
    parses into, so the server forces the structure;
  - `two_pass`: a prose call (one heading per field, told the structure),
    then the conversion: the request, the prose as the assistant turn, and
    "Now give your answer above as JSON…", under the forced schema.
- **Counting:** each turn's meter records per step kind the mode, logical
  JSON calls, attempts (retries included) and calls that failed every
  attempt; the run file's turn health carries it as `json_calls`.
  Composer document-rule retries are separate (the composer's own history).
- Tests: `tests/test_llama_utils/test_structured_output.py`. The Q-02
  campaign runs from pinned worktrees, so none of its runs change.
- First use: the smoke model `qwen3-0.6b` (`generator-server.sh qwen3-0.6b`,
  `:8095`, one card) on the g3 subset: a, and b under each mode.

## Smoke test, qwen3-0.6b on g3 (2026-10-25 04:58–05:12Z, commit 7768432)

Run files `journal/baseline/runs/20261025T0*_smoke06b-*_qwen3-0.6b.json`
(untracked, like the other run files; logs in `runs/q02-stage1-logs/`).

| Arm | Turns completed (of 10) | Where it stopped | Hidden tests (5 code prompts) |
| --- | --- | --- | --- |
| a, single call | 10 | — (c36, c47 ran to 32,768 tokens of text) | 0 passed anywhere |
| b, `json_object` | 1 (c47, 45 chars) | the task breakdown: valid JSON, wrong fields (e.g. `meta_type: 'DecomposeSubTask'` for the union tag) | 0 |
| b, `json_schema` | 0 | the composer: "Provide exactly one of body or body_source" | 0 |
| b, `two_pass` | 1 (c47, 1,390 chars) | the composer, same rule | 0 |

- Forcing the schema (`json_schema`, `two_pass`) fixes the breakdown:
  every turn reaches the composer.
- What still fails are **cross-field rules written as pydantic
  validators**, which the JSON schema does not express: `body` xor
  `body_source` on the body ops, `tool_calls` xor `result` on
  `ExecutorTurn`. Both fields are optional in the schema, so the forced
  grammar allows both or neither. A forced schema built with one variant
  per alternative (a `oneOf`, each requiring its field) would enforce them.
  That is for the forced modes' response format only; the prompt's schema
  text, and so the default mode, would be unchanged.
- The 0.6B passes no hidden test in any arm, single call included: no
  harness can lift it on this bench. Not a Q-02 generator.

## Smoke test 2: the forced schema (2026-10-25 13:01–13:11Z, commit eb5b187)

`forced_schema` (`llama_utils`): the forced modes send the parsed model's
schema with each exclusive pair (`body_source` / `body`, `tool_calls` /
`result`) split into one variant per field (`anyOf`, `additionalProperties:
false`, the kept field required and non-empty), union tags required and
written first, and the long field last. `json_object` is unchanged. Run files
`20261025T13*_smoke06b-v2-b-*_qwen3-0.6b.json`; a and b-`json_object` were not
re-run (nothing they send changed).

| Arm | Turns completed (of 10) | Composer failures, by kind | Hidden tests |
| --- | --- | --- | --- |
| b, `json_schema` | 2 (c36, c47; were 0) | keep rule 3, duplicate part id 2, unknown part id 1 | 0 |
| b, `two_pass` | 0 (was 1) | duplicate part id 5, `merge_parts` with the same id twice 3 | 0 |

- The rule the grammar now holds stopped failing: no "exactly one of"
  error in either arm.
- What remains is **document state the model gets wrong**, not JSON: adding
  a part id that exists, naming one that doesn't, merging a part into itself,
  dropping the sub-task result. A grammar cannot hold these (they depend on
  the current document; `uniqueItems` is not in llama.cpp's grammar subset).
- n = 10 per arm on a model that solves nothing, so 1 → 0 and 0 → 2 are noise.
  Still 0 hidden tests anywhere.

## What the steps ask the model to write (review, 2026-10-25)

Forced-schema sizes: compose 5.1K characters (8 op types), decompose 3.8K
(4 item types, 7 required fields per sub-task), executor 2.0K, consolidate
2.0K. instructor's `Mode.JSON` puts this schema text in every prompt.

1. **Union tags were optional.** `type: Literal[...] = '...'` has a default,
   so pydantic leaves it out of `required`; a forced grammar let the model drop
   the tag the union is parsed on. Fixed in `forced_schema`.
2. **The long field came first.** `AddPart` lists `body` before `type`, `id`,
   `kind`: the model writes the content before saying what to do with it.
   `forced_schema` now writes it last. llama.cpp's converter (as I understand
   it) orders required fields before optional ones, so `title` and `after`
   still follow `body` there.
3. **Developer notes reach the model.** `MergeParts`' docstring becomes its
   schema description, including "this is what the consolidation pass uses to
   replace the delete-then-re-add churn observed in the s3 baseline", in every
   compose prompt. Same for other docstrings. A prompt change, so after Q-02.
4. **Code inside JSON strings.** The executor's `result` and the composer's
   `body` carry whole files as escaped JSON strings. This is the cost
   `two_pass` and `body_source: current_result` exist to avoid.
5. **The composer's job is broad for a small model**: eight op types and
   document bookkeeping (existing ids, anchors, keep rule) on every sub-task.
   For small models, a reduced op set (add, append, with `body_source` only)
   or a deterministic default (append each result as its own part, with the
   composer only choosing titles and order) would remove most of the failures
   above. Both are harness changes, so after Q-02.

## An easier bench for small models (proposal, 2026-10-25)

The 0.6B scores 0 on v1 even in a single call, so v1 cannot show whether the
harness helps it. A harness gain is only measurable where the single call
passes sometimes (say 20–60 % of tests).
- **v1-easy**: ~20–30 code prompts of our own, in v1's format with hidden
  tests (no third-party data): single-file, 1–3 functions, HumanEval-to-
  LRU-cache difficulty, a few of them decomposable into 2–3 independent
  pieces (the case the harness is for). Calibrate on the target model's
  single call first; keep prompts in its 20–60 % band.
- Reports: the 0.6B already writes coherent reports in a single call, so the
  report strata are measurable through the judge once b completes turns.
- The 0.6B may sit below the floor where any multi-call harness works (its
  code is 9 tokens or a fence repeated to the cap). A 1.7B–4B model is the
  likelier "end user's small model"; none is on disk.
