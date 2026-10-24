# Bench v1-std: the standard slice for Q-E1

An outside check on bench v1. The prompts and their scoring come from two
published datasets, written by people other than the agent running the
experiment. The slice runs on the same arms (`arms.py --bench
journal/baseline/bench/v1-std`) and is reported as its own table, never
pooled with v1.

When this README and the data differ, fidelity to the original datasets wins:
every prompt, test and reference is the dataset's text. The only additions
are the ones listed under "Added paragraph" and "Test adaptations".

Status: **data built, not frozen** (`frozen: false`).
- Code: scored by hidden tests (`hidden_tests.py`).
- Report: scored by Google's official IFEval checker (`ifeval_checker/`,
  `journal/baseline/ifeval_score.py`; adopted by the user 2026-10-24).

## Contents

| Domain | Entries | Source |
| --- | --- | --- |
| code (`sc`) | 18: 21 selected by the rule, minus 3 exclusions | BigCodeBench-Hard v0.1.4 |
| report (`sr`) | 20 | IFEval |

Layout (bench v1's schema, see `../v1/README.md`):

```
manifest.yaml              id, domain, status, title, brief, source, files / target_words
prompts/<id>.md            the prompt text, exactly as sent
tests/<id>/test_task.py    code: BigCodeBench's test, run against task.py
reference/<id>/task.py     code: code_prompt + canonical_solution
ifeval/<id>.json           report: {key, instruction_id_list, kwargs} from the IFEval row
build.py                   regenerates all of the above from the raw files
```

Every entry is `status: written`. The slice has no follow-ups, no `long` or
`overlap` flags and no subsets. `brief` is a one-line paraphrase written for
review; the prompt file is the only text the model sees.

## Sources and versions

Both datasets were downloaded with `huggingface_hub` before this slice was
built. The repo ids were not recorded on disk; the directory names are the
datasets' names.

| Dataset | File | sha256 | HF cache revision |
| --- | --- | --- | --- |
| BigCodeBench-Hard v0.1.4 | `~/models/bench-std-raw/BigCodeBench-Hard/v0.1.4.jsonl` (148 rows) | `2f8a10ad5dc3eee6422dc84171fa599da4d309f81f2c4157b8d3c4bca957c85d` | `298d2cc7b96612e15e47313c3603ee124cee0c1f` |
| IFEval | `~/models/bench-std-raw/IFEval/ifeval_input_data.jsonl` (541 rows) | `6a85310ca8ce15eff755aa08a3a4ff931c7e273e7515ebb3c492ea85fd8288f2` | `966cd89545d6b6acfd7638bc708b98261ca58e84` |

- The BigCodeBench JSONL matches the split
  `data/v0.1.4-00000-of-00001.parquet` beside it (sha256 `73a4270b…a6ce79`,
  the parquet's cache etag).
- The revisions are the first line of the `.metadata` files under each
  `.cache/huggingface/download/`.

## Selection rules (fixed)

**std-code.** Every BigCodeBench-Hard v0.1.4 task that meets both conditions:
- every module in `libs` is in `sys.stdlib_module_names` (Python 3.12);
- no module in `libs` is one of subprocess, ftplib, socket, smtplib, urllib,
  http, ssl, ctypes, multiprocessing, threading or signal.

`libs` is the row's own list, parsed with `ast.literal_eval`. Ids are `sc01`…
in task_id order (numeric), over all the tasks the rule selects, so an
excluded task keeps its number and leaves a gap. Each entry keeps the
task_id in `source`.

**The rule selects 21 tasks, not the 22 expected when the slice was
planned.** The rule was applied as stated and not tuned to reach 22.

**std-report.** `random.Random(0).sample(sorted(keys), 20)` over all 541
IFEval keys (ints). Ids are `sr01`… in sample order. Each entry keeps the key
in `source`.

| id | source | id | source |
| --- | --- | --- | --- |
| sc01 | BigCodeBench/19 | sc12 | BigCodeBench/777 |
| ~~sc02~~ | BigCodeBench/287 (excluded) | sc13 | BigCodeBench/800 |
| sc03 | BigCodeBench/310 | ~~sc14~~ | BigCodeBench/826 (excluded) |
| ~~sc04~~ | BigCodeBench/313 (excluded) | sc15 | BigCodeBench/854 |
| sc05 | BigCodeBench/368 | sc16 | BigCodeBench/857 |
| sc06 | BigCodeBench/454 | sc17 | BigCodeBench/906 |
| sc07 | BigCodeBench/592 | sc18 | BigCodeBench/928 |
| sc08 | BigCodeBench/594 | sc19 | BigCodeBench/963 |
| sc09 | BigCodeBench/720 | sc20 | BigCodeBench/971 |
| sc10 | BigCodeBench/765 | sc21 | BigCodeBench/988 |
| sc11 | BigCodeBench/771 | | |

IFEval keys sr01–sr20: 2943, 3203, 334, 2292, 3710, 3565, 3091, 2482, 3513,
2807, 2035, 3680, 1551, 2386, 1561, 1259, 2247, 1593, 2532, 1281.

## Exclusions

The slice is the selection rule plus these exclusions. A task is excluded
only when its own tests cannot pass in the sandbox. The sandbox has no
network, a temp-dir cwd, a fixed env and only the repo's `.venv`.

| id | task | reason |
| --- | --- | --- |
| sc02 | BigCodeBench/287 | The test does `from faker import Faker`. Faker is third-party and not installed in `.venv`, and installing it is out of scope. The test module fails to import, so the reference scores 0/1. |
| sc04 | BigCodeBench/313 | Same: the test imports `faker`. |
| sc14 | BigCodeBench/826 | Same: the test imports `faker`. |

`check-bench` produced the evidence. Running `build.py --all` (which writes
every selected task) and then check-bench gave `reference 0/1 not passing:
['test_task']` for exactly these three tasks; `import faker` fails in
`.venv`. None of the three tests needs anything else that is missing. If
faker is ever installed, rebuilding without these exclusions would be a new
version (`v1-std` → `v2-std`), not an edit.

## Code entries

**Prompt.** The prompt is the row's `instruct_prompt` verbatim, followed by a
blank line and this added paragraph (the only text added to any prompt):

> Put the code in a file `task.py`. Use only the Python 3.12 standard
> library. Give each file in its own fenced code block, with the file's path
> on the line just before the block.

BigCodeBench's own prompt already asks for self-contained code starting from
a given stub. The paragraph adds a file name and delivery format, so that
`hidden_tests.py` can extract the deliverable the same way it does for v1.

**Reference.** `reference/<id>/task.py` is `code_prompt + canonical_solution`,
concatenated as stored. The only change is a single trailing newline.

**Test adaptations.** `tests/<id>/test_task.py` is the row's `test` field,
unchanged below the marker line `# ---- BigCodeBench test code (unchanged)
----`. The header above that line makes three adaptations, and each file
documents them in a comment:

1. **Shared namespace.** BigCodeBench executes the solution and the test
   code as one module, solution first. Its tests therefore use the
   solution's names without importing them: `task_func`, constants such as
   `OUTPUT_DIR`, and modules such as `os`, `shutil` and `random`. The header
   reproduces this in two steps:
   - it repeats the import lines of the task's `code_prompt` (the stub the
     prompt tells the model to start with);
   - it then runs `from task import *`.
2. **No collectable names from the deliverable.** After the star import, the
   header deletes any name defined in `task.py` that pytest would collect as
   a test: a `test*` function, a `Test*` class or a `unittest.TestCase`
   subclass. A deliverable therefore cannot add its own tests to the count.
3. **Runner.** The tests are run by pytest through `hidden_tests.py`, which
   runs the `TestCases` class's methods unchanged. BigCodeBench runs them
   with unittest.

Known differences from BigCodeBench's own evaluation:
- **`__all__`.** A star import honours `__all__`. A deliverable that defines
  `__all__` without a constant the tests use would fail here, but would pass
  in BigCodeBench's shared namespace.
- **Sandbox.** BigCodeBench's process sandbox and its time and memory limits
  are not reproduced. The sandbox is `hidden_tests.py`'s: netns, temp cwd,
  and a 120 s wall timeout per pytest run.
- **Scoring.** BigCodeBench's metric is task-level pass (every test in the
  task passes). `hidden_tests.py score` reports passed/total per prompt. The
  BigCodeBench-equivalent task pass is `passed == total` with no collection
  error, and the code table should report that alongside passed/total.
- **Broken variants.** There are none: the tests are the dataset's, so
  `check-bench` checks only that the reference passes and that an empty
  deliverable fails.

## Report entries

- `prompts/<id>.md` is the row's `prompt` verbatim. Note that `arms.py`
  strips leading and trailing whitespace when it loads any prompt.
- `ifeval/<id>.json` holds `{key, instruction_id_list, kwargs}` exactly as
  in the row.
- `target_words` is the `num_words` kwarg when one of the row's instructions
  has it. Otherwise it is 300. None of the 20 sampled rows has a `num_words`
  kwarg, so every report entry has `target_words: 300`. That value is a
  length budget for the arms, not an IFEval constraint.
- **Scoring:** Google's official IFEval checker, vendored at
  `ifeval_checker/` (the pinned commit, its licence and the one local
  change are in `ifeval_checker/SOURCE.md`; adopted by the user
  2026-10-24). It runs only in its own venv:
  `.venv-ifeval/bin/python journal/baseline/ifeval_score.py RUN_FILE`
  (`make venv-ifeval` builds it). That writes `<run>.ifeval.json` with
  strict and loose verdicts per instruction and IFEval's four headline
  numbers per arm. `checklists.py` does not read `ifeval/`.

## Licences

Only the files on disk were checked. They hold the data files and
`huggingface_hub` cache metadata (`.gitignore`, `CACHEDIR.TAG`, `.lock`,
`.metadata`). **Neither dataset's card, README or licence file is on disk**,
so neither licence is recorded here. Both must be read from the dataset
cards, and recorded here, before any of this slice is redistributed outside
the repo.

## How to run

From the repo root:

```
# regenerate the data from the raw files (reads JSON only; runs no dataset code)
.venv/bin/python -I journal/baseline/bench/v1-std/build.py

# validate the code entries: each reference passes, an empty deliverable fails
.venv/bin/python journal/baseline/hidden_tests.py check-bench --bench journal/baseline/bench/v1-std

# list the chains, with no model calls
.venv/bin/python journal/baseline/arms.py plan --bench journal/baseline/bench/v1-std --arm a

# run the arms, then score the code domain
.venv/bin/python journal/baseline/arms.py run --bench journal/baseline/bench/v1-std --generator ... --arm ...
.venv/bin/python journal/baseline/hidden_tests.py score RUN_FILE --bench journal/baseline/bench/v1-std
```

The slice's structure is tested by `tests/test_baseline/test_bench_v1_std.py`.

Last `check-bench`: `18/18 code prompts OK` (isolation netns). Every
reference passes all of its tests (5–12 per task), and every empty
deliverable passes 0.
