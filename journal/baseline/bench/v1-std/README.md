# Bench v1-std: the standard slice for Q-E1

An outside check on bench v1. The prompts and their scoring come from two
published datasets, written by people other than the agent running the
experiment. The slice runs on the same arms (`arms.py --bench
journal/baseline/bench/v1-std`) and is reported as its own table, never
pooled with v1.

When this README and the data differ, fidelity to the original datasets wins:
every prompt, test and reference is the dataset's text. The only additions
are the ones listed under "Added paragraph" and "Test adaptations".

**The datasets' text and the IFEval checker are not in this repo.** The repo
keeps the references (pinned URLs and sha256s), the code that regenerates
the slice, and `data.lock`, which proves the regenerated files are
byte-identical to what the experiments ran on. From the repo root:

```
make venv-ifeval bench-std
```

See "Getting the data" below.

Status: **frozen** 2026-10-24 (`frozen: true`, D-026).
- Code: scored by hidden tests (`hidden_tests.py`).
- Report: scored by Google's official IFEval checker (`ifeval_checker/`,
  `journal/baseline/ifeval_score.py`; adopted by the user 2026-10-24).

## Contents

| Domain | Entries | Source |
| --- | --- | --- |
| code (`sc`) | 18: 21 selected by the rule, minus 3 exclusions | BigCodeBench-Hard v0.1.4 |
| report (`sr`) | 20 | IFEval |

Layout (bench v1's schema, see `../v1/README.md`). Committed:

```
manifest.yaml              id, domain, status, title, brief, source, files / target_words
build.py                   regenerates manifest.yaml and the generated files below from the raw files
fetch.py                   downloads the raw files and the IFEval checker by pinned URL and sha256
convert_bcb.py             makes the BigCodeBench JSONL from its parquet (needs pyarrow)
data.lock                  sha256 of every generated and fetched file below, and of manifest.yaml
ifeval_checker/            SOURCE.md, requirements.lock, local-change.patch
```

Generated or fetched, git-ignored:

```
prompts/<id>.md            the prompt text, exactly as sent
tests/<id>/test_task.py    code: BigCodeBench's test, run against task.py
reference/<id>/task.py     code: code_prompt + canonical_solution
ifeval/<id>.json           report: {key, instruction_id_list, kwargs} from the IFEval row
LICENSE                    the Apache-2.0 text (fetched)
ifeval_checker/LICENSE, ifeval_checker/instruction_following_eval/   the checker (fetched)
```

Every entry is `status: written`. The slice has no follow-ups, no `long` or
`overlap` flags and no subsets. `brief` is a one-line paraphrase written for
review; the prompt file is the only text the model sees.

## Sources and versions

The slice was built from these files. fetch.py downloads them, by these
URLs, into the raw dir (default `~/models/bench-std-raw`, `--raw DIR` /
`make bench-std RAW=DIR`), and refuses a file whose sha256 differs.

| Dataset | URL (HF revision pinned) | File in the raw dir | sha256 |
| --- | --- | --- | --- |
| IFEval | `https://huggingface.co/datasets/google/IFEval/resolve/966cd89545d6b6acfd7638bc708b98261ca58e84/ifeval_input_data.jsonl` | `IFEval/ifeval_input_data.jsonl` (541 rows) | `6a85310ca8ce15eff755aa08a3a4ff931c7e273e7515ebb3c492ea85fd8288f2` |
| BigCodeBench-Hard v0.1.4 | `https://huggingface.co/datasets/bigcode/bigcodebench-hard/resolve/298d2cc7b96612e15e47313c3603ee124cee0c1f/data/v0.1.4-00000-of-00001.parquet` | `BigCodeBench-Hard/data/v0.1.4-00000-of-00001.parquet` | `73a4270b43feb81abefad7bb1b592937c768ea45c3263bedc1cabd30a9a6ce79` |
| BigCodeBench-Hard v0.1.4, as JSONL | made from the parquet by `convert_bcb.py` | `BigCodeBench-Hard/v0.1.4.jsonl` (148 rows) | `2f8a10ad5dc3eee6422dc84171fa599da4d309f81f2c4157b8d3c4bca957c85d` |

- build.py reads the two JSONL files and refuses them unless their sha256
  match these pins. manifest.yaml's header records the same two hashes.
- The JSONL the slice was first built from was converted from the parquet
  when the datasets were downloaded (with `huggingface_hub`, 2026-10-23),
  but the conversion was not recorded. `convert_bcb.py` reproduces it as
  the parquet's rows in file order, one `json.dumps(row)` per line: that is
  exactly the recorded file's format (re-serialising its rows that way gives
  its bytes), and the parquet's schema has the same columns in the same
  order with the same types. The output must match the pinned sha256 or it
  is refused. The conversion runs in `.venv-ifeval`, which pins pyarrow
  25.0.1 (`make venv-ifeval`). Verified 2026-10-24: converting the pinned
  parquet in a fresh raw dir reproduces the pinned JSONL byte for byte.
- The IFEval checker's source, commit and file hashes are in
  `ifeval_checker/SOURCE.md`.

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
  a 20 s timeout per test and a 120 s wall timeout per pytest run.
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
  kwarg, so every report entry has `target_words: 300`. That value is
  metadata only: neither `arms.py` nor the harness reads it, and it is not
  an IFEval constraint.
- **Scoring:** Google's official IFEval checker, fetched into
  `ifeval_checker/` at a pinned commit (the commit, the file hashes, its
  licence and the one local change are in `ifeval_checker/SOURCE.md`;
  adopted by the user 2026-10-24). It runs only in its own venv:
  `.venv-ifeval/bin/python journal/baseline/ifeval_score.py RUN_FILE`
  (`make venv-ifeval` builds it). That writes `<run>.ifeval.json` with
  strict and loose verdicts per instruction and IFEval's four headline
  numbers per arm. `checklists.py` does not read `ifeval/`.

## How it is compared (Q-02 § 4.1, the delegated review, 2026-10-24)

- **Frozen** 2026-10-24 (D-026), as built: `build.py` writes `frozen: true`.
- Every prompt here is short, so (b)'s decisive rate over (a″) on this
  slice is compared with bench v1's **short** strata, never with v1 as a
  whole. It is its own table and never part of the six claims.
- **Per-prompt outcome.** IFEval half: the arm that follows strictly more
  instructions (IFEval strict) wins; equal counts tie. Code half: the v1
  rule (the higher hidden-test pass-rate wins; equal rates go to the
  judge), with task-level pass (all tests) reported beside it.

## Licences and attribution

None of these sources' files is in this repo; they are fetched by the
references above. All three are Apache License 2.0 (read from the published
cards and the checker repository on 2026-10-24). The raw dataset files carry
no card or licence file; fetch.py writes the licence text, the
google-research repository's `LICENSE` at the checker's commit (the
standard Apache-2.0 text), beside this file and in `ifeval_checker/`.

| Source | Licence | Where it is stated | Cite |
| --- | --- | --- | --- |
| BigCodeBench-Hard v0.1.4 (BigCode) | Apache-2.0 | the parent dataset card, `huggingface.co/datasets/bigcode/bigcodebench` ("BigCodeBench is licensed under the Apache License, Version 2.0"); the `-hard` subset's own card is empty, so its licence is the parent's; the GitHub repo `bigcode-project/bigcodebench` is Apache-2.0 too | Zhuo et al., 2024, "BigCodeBench: Benchmarking Code Generation with Diverse Function Calls and Complex Instructions", arXiv:2406.15877 |
| IFEval (Google) | Apache-2.0 | `huggingface.co/datasets/google/IFEval` card metadata and text | Zhou et al., 2023, "Instruction-Following Evaluation for Large Language Models", arXiv:2311.07911 |
| IFEval checker (google-research `instruction_following_eval/`) | Apache-2.0 | the repository's `LICENSE` at the pinned commit; the one local change is `ifeval_checker/local-change.patch` (`ifeval_checker/SOURCE.md`) | as IFEval |

**Changes made** (Apache 2.0 § 4(b) asks modified files to say so):
`build.py` reformats the source rows into this bench's layout, and the
changes are those listed under "Code entries" and "Report entries" above:
each BigCodeBench prompt gets one added delivery paragraph, each test file
gets a documented header above the unchanged test code, and each reference
is the stub plus the canonical solution. IFEval prompts are written
verbatim and their instruction lists kept as `ifeval/<id>.json`. Neither
card adds restrictions beyond the licence (no no-training clause, no canary
string).

## Getting the data

From the repo root, `make venv-ifeval bench-std` (`RAW=DIR` for another raw
dir). The `bench-std` target runs, in order:

1. `fetch.py` (stdlib only): downloads the two raw dataset files and the
   checker, checks every sha256 against its pin, applies
   `ifeval_checker/local-change.patch`, and checks the fetched files against
   `data.lock`. Present files that match are not downloaded again; a present
   file that does not match is an error.
2. `convert_bcb.py`, in `.venv-ifeval`: makes the BigCodeBench JSONL from
   the parquet unless it is already there with its pinned sha256. It needs
   pyarrow and prints the install command when it is missing.
3. `build.py`: writes manifest.yaml, prompts/, tests/, reference/ and
   ifeval/.
4. `build.py --check`: every generated and fetched file, and manifest.yaml,
   against `data.lock`; any missing, extra or changed file fails.

`data.lock` is in `sha256sum` format, so `cd journal/baseline/bench/v1-std
&& sha256sum -c data.lock` checks it too. The rebuild was confirmed
byte-identical to the files the experiments ran on (2026-10-24): all 105
locked files, manifest.yaml included. Run files record manifest.yaml's
sha256, so it is committed and must not change.

## How to run

From the repo root:

```
# fetch, convert, regenerate and check the data (fetch.py and build.py run no dataset code)
make venv-ifeval bench-std

# validate the code entries: each reference passes, an empty deliverable fails
.venv/bin/python journal/baseline/hidden_tests.py check-bench --bench journal/baseline/bench/v1-std

# list the chains, with no model calls
.venv/bin/python journal/baseline/arms.py plan --bench journal/baseline/bench/v1-std --arm a

# run the arms, then score the code domain
.venv/bin/python journal/baseline/arms.py run --bench journal/baseline/bench/v1-std --generator ... --arm ...
.venv/bin/python journal/baseline/hidden_tests.py score RUN_FILE --bench journal/baseline/bench/v1-std
```

The slice's structure and `data.lock` are tested by
`tests/test_baseline/test_bench_v1_std.py`; the tests that need the data skip
when it has not been fetched.

Last `check-bench`: `18/18 code prompts OK` (isolation netns). Every
reference passes all of its tests (5–12 per task), and every empty
deliverable passes 0.
