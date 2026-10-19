# Absolute rubric v1 (Q-01, secondary)

Version: `absolute_v1`. The pairwise rubric decides win-rates; this one
scores a single response so that arms can be described on their own and so
that a pairwise verdict can be explained. Its scores never replace a
pairwise verdict or a test result.

## Instructions to the judge

You are scoring one response to a task. First list every deliverable,
feature, flag, section, constraint and limit the task states. Then score
the response on each dimension from 1 to 5 using the anchors. Score what
the task asked for, not what you would have asked for.

| Dimension | 1 | 3 | 5 |
| --- | --- | --- | --- |
| Task completion | most requested items missing | one requested item missing or incomplete | every requested item present and done |
| Correctness | a central fact, result or behaviour is wrong | one minor error that does not change the outcome | no errors found; attached test results, if any, pass |
| Constraint adherence | an explicit constraint is broken in a way that changes the deliverable | one explicit constraint bent (a length, a flag name, a repeat) | every explicit constraint kept |
| Structure and format | the deliverable is not in the requested shape | the shape is right but navigation takes effort | the requested shape, readable at a glance |
| Concision | half or more of the text does no requested work | some restatement or padding | nothing could be removed without losing requested content |

Rules:
- A test result attached to the response decides correctness for the
  tested behaviour.
- Length is not a dimension. Score concision on the share of text that does
  requested work, not on the total.
- Do not reward tone, confidence, decoration or a summary of the response's
  own work.

## Output

Return only this JSON object, no prose around it:

```json
{
  "requested_items": ["..."],
  "missing": ["..."],
  "wrong": ["..."],
  "scores": {
    "completion": 1,
    "correctness": 1,
    "constraints": 1,
    "structure": 1,
    "concision": 1
  },
  "overall": 1,
  "reason": "one or two sentences"
}
```

`overall` is your judgement of the response as a deliverable, 1 to 5, not
an average.
