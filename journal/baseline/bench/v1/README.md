# Bench v1 (Q-02, criterion Q-9)

The standing benchmark for experiment Q-E1: 140 prompts, 70 code and 70
report (the user, 2026-10-23). Every arm on every generator gets the same
prompt text (`journal/baseline/arms.py`). The set is frozen per version: once
`manifest.yaml` says `frozen: true`, any change to a prompt, test, checklist
or flag is a `v2`, never an edit.

Status: **frozen 2026-10-23, provisional under D-022.** All 140 entries are
written. Every code prompt passes `hidden_tests.py check-bench`: the
reference passes, an empty deliverable fails, and every broken variant is
caught. Every report checklist passes `checklists.py check-bench`. The
user's mass review may amend the set, and an amended set is a new version.
The points flagged for that review are in `journal/design/Q-02-bench-v1.md`
§ 9.

## Layout

```
manifest.yaml              every prompt: id, domain, flags, subsets, files / target_words
prompts/<id>.md            the prompt text, exactly as sent (no front matter)
tests/<id>/test_*.py       code: hidden tests (never shown to a model or a judge)
reference/<id>/...         code: a reference solution, used only to validate the tests
reference/<id>/broken/<v>/ code: deliberately wrong variants, overlaid on the reference;
                           each must fail at least one test (hidden_tests.py check-bench)
checklists/<id>.yaml       report: mechanical checks (checklists.py)
```

## Manifest fields

| Field | Meaning |
| --- | --- |
| `id` | `cNN` code, `rNN` report; a follow-up is its parent's id plus `f` |
| `domain` | `code` or `report`; never pooled (Q-8) |
| `title`, `brief` | for review; `brief` is the one-line spec of a draft entry |
| `status` | `draft` (brief only) or `written` (prompt and tests or checklist exist) |
| `long` | the deliverable exceeds one call's `max_tokens` (8,192 tokens, ≈ 6,000 words), or has more than one file (D-019) |
| `follows` | the parent prompt; the follow-up runs in the parent's chain, in the same arm |
| `overlap` | a root whose deliverables deliberately overlap, for arm (c); follow-ups are always in the overlap subset |
| `files` | code: the paths the prompt asks for (the test runner's `expected_paths`) |
| `target_words` | report: the length the prompt asks for |
| `subsets` | named subsets; `g3` is the ≈ 10-prompt G3 subset (Q-03) |

## Composition rules (checked by `tests/test_baseline/test_bench_v1.py`)

- 70 code and 70 report prompts.
- At least ⅓ long overall (target 60 of 140).
- At least 20 % follow-ups: 14 per domain, each following a root (depth 1),
  and no root has two follow-ups.
- 6 overlap roots per domain.
- `g3`: 5 code and 5 report prompts, two of them follow-ups whose roots are
  also in `g3`.

## Writing rules

**Code prompts**
- Each prompt names every file and the exact interface: function and class
  signatures, CLI arguments, output format, exit codes and error types. The
  tests check behaviour the prompt states, never a guess.
- Only the Python 3.12 standard library is allowed.
- Each prompt ends with the same delivery line: *"Use only the Python 3.12
  standard library. Give each file in its own fenced code block, with the
  file's path on the line just before the block."*
- A follow-up ends with *"Give the complete updated files."* Its tests cover
  the old behaviour and the new.
- Tests are deterministic. Time comes from an injected clock, not the wall
  clock. Any randomness is seeded. Nothing touches the network.
- Each test file has 8–25 tests; long prompts have more.
- Every prompt has at least two `broken/` variants: plausible bugs that the
  tests must catch (Q-1's damaged-pair idea, applied to the tests).

**Report prompts**
- Every fact a report needs is either given in the prompt (data, transcript
  or spec) or is stable general knowledge. Nothing depends on current events.
- Each prompt carries 4–8 checkable constraints: length, required sections,
  counts, given numbers that must reappear or sum correctly, or things that
  must not repeat. The checklist scores those mechanically. The judge scores
  everything else (design note § 3).
- A checklist item checks only a constraint the prompt states. When the
  prompt says "about N words" or "about N-M words", the bounds widen by
  10 %. The exemplars were calibrated on 0-16's real s2/s3 outputs.
- A follow-up ends with *"Reply with the complete updated document."*, so
  every arm's output after the turn is the whole document (the harness
  renders its whole Document too).

**Both domains:** no prompt names the harness, decomposition or an arm.
Prompts are written to be fair to every arm:
- about half are short, single-deliverable tasks where decomposition has
  little room to help;
- the rest are long or multi-part.

## Checklist format

```yaml
id: r01
items:
  - {id: words, check: word_count, min: 300, max: 500}
  - {id: sec-cost, check: heading, pattern: '(?i)cost|hosting'}
  - {id: git, check: contains, pattern: '(?i)\bgit\b'}
  - {id: steps, check: numbered_items, section: '(?i)migrat', min: 3, max: 3}
  - {id: no-repeat, check: max_section_overlap, max: 0.5}
```

Checks:
- `word_count` (`min` / `max`);
- `heading` (a markdown heading matching `pattern`, with optional `min` /
  `max` counts);
- `contains` / `not_contains` (a regex in the body, optional `min` count);
- `numbered_items` / `bullet_items` (top-level list items, optionally inside
  the section whose heading matches `section`);
- `table_rows` (body rows of the first table, optionally in a `section`);
- `max_section_overlap` (the largest word-set Jaccard between any two `##`
  sections, the same measure as the harness's `max_dup_jaccard`);
- `number` (a regex whose first group parses to a number equal to `value`
  within `tol`).

A report's checklist score is the fraction of items that pass. Every item
is reported on its own too.
