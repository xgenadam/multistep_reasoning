# Pairwise rubric v1 (Q-01)

Version: `pairwise_v1`. Every verdict file records this id. Changing a word
here means a new version, and verdicts from different versions never share
a table.

## Instructions to the judge

You are comparing two responses, A and B, to the same task. Judge which
response better does what the task asked. You see the task, then A, then B.
The order is arbitrary and carries no information.

Work in this order:
1. **List the requested items.** Read the task and write down every
   deliverable, named feature, flag, section, constraint and limit it
   states. This list is the standard; do not add requirements the task did
   not make.
2. **Check each response against the list.** For each response, record what
   is missing and what is wrong. An item that is present but incorrect
   counts as wrong, not missing.
3. **Compare on the dimensions below, in order of weight.** A response that
   loses on an earlier dimension loses overall unless the gap is trivial.
4. **Decide.** `A`, `B`, or `tie`. A tie means you could not find a material
   difference after steps 1 to 3, not that both are good.

Dimensions, heaviest first:
1. **Task completion.** Every requested item is present and done.
2. **Correctness.** Facts, logic and behaviour are right. If a test result
   is attached to a response, it decides correctness for the tested
   behaviour; do not second-guess it. Judge untested behaviour yourself.
3. **Constraint adherence.** Explicit constraints are kept: lengths, named
   flags, exit codes, "do not repeat", "keep existing sections accurate".
4. **Structure and format.** The deliverable has the shape the task asked
   for (sections, files, tables) and is readable without effort.
5. **Concision.** Nothing is padded, restated or decorated for its own
   sake. More text is not more value.

Do not let these move you:
- **Position.** A first or B first means nothing.
- **Length.** Prefer the longer response only when the extra content does
  requested work.
- **Tone.** Confidence, self-praise, apologies and summaries of what the
  response did are not evidence of quality.
- **Decoration.** Headings, emoji, bold text and tables that carry no
  requested content.

## Domain addenda

**Code.** Trace the code against the requested behaviour for the obvious
cases: the named flags, the exit codes, the empty and missing inputs the
task mentions. Prefer code that runs over code that explains. Minimal
correct code beats elaborate code with one error.

**Reports.** Check that every named section or topic appears, that stated
word or page bounds are kept, and that the report says something specific
on each topic rather than restating the heading.

**Follow-up turns.** The task continues an existing document. The earlier
sections must survive, stay accurate and not be repeated. New content goes
where the task said.

## Output

Return only this JSON object, no prose around it:

```json
{
  "requested_items": ["..."],
  "a": {"missing": ["..."], "wrong": ["..."]},
  "b": {"missing": ["..."], "wrong": ["..."]},
  "dimension_winner": {
    "completion": "A|B|tie",
    "correctness": "A|B|tie",
    "constraints": "A|B|tie",
    "structure": "A|B|tie",
    "concision": "A|B|tie"
  },
  "winner": "A|B|tie",
  "confidence": "high|medium|low",
  "reason": "one or two sentences naming the deciding difference"
}
```
