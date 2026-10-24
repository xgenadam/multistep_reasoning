# Google's IFEval checker: pinned source, fetched by reference

The official instruction-following checker from the IFEval paper (Zhou et
al., 2023). It scores bench v1-std's report entries (sr01–sr20) for Q-02
bias guard 4.1. The user adopted it on 2026-10-24 (option A: the official
checker, in its own environment).

**The checker's code is not in this repo.** Only this file,
`requirements.lock` and `local-change.patch` are committed. `make
venv-ifeval bench-std` (from the repo root) runs `../fetch.py`, which
downloads the pinned files below, checks each sha256, applies the patch and
checks the result against `../data.lock`. The fetched files are git-ignored.

- **Source:** `github.com/google-research/google-research`, directory
  `instruction_following_eval/`, at commit
  `e6890f85757dd84e27ca6df2dd30651dafad28e0` (2026-07-22). That commit is
  the latest one touching the directory on 2026-10-24. Each file comes from
  `https://raw.githubusercontent.com/google-research/google-research/<commit>/instruction_following_eval/<file>`.
- **Licence:** Apache License 2.0, the repository's `LICENSE` at that
  commit. fetch.py writes it as `LICENSE` here (and, as the licence text
  for the datasets, beside the slice).
- **Files** (the experiments ran on exactly these bytes):

  | File | sha256 at the commit | Used as |
  | --- | --- | --- |
  | `evaluation_lib.py` | `35decc06000718487f44d7deafa6d3f48a8ec0886281edf40162c0265b7d248c` | unchanged |
  | `instructions.py` | `60e086f5342a03ce8e18b64bbcccf86308f523c08aa826707a562150a52f3edf` | unchanged |
  | `instructions_registry.py` | `ec92d72c264f6d906978613085db262356174300370a3fffe6fefd5969ce9cfc` | unchanged |
  | `instructions_util.py` | `a73797261eee5bf447e279d82a2b700b1bdd3cb1193412dbab1270a85832bc6b` | patched: `188324d4764366fc85d2e50966719e89a469f21ce0b0f773ec0abe1447d62b94` |
  | `instructions_test.py` | `e677c190c393162f7733e89ca3b47ae98b6d9e816d800681d6e14ad918128de5` | unchanged |
  | `instructions_util_test.py` | `e8e17d434e074c6e2ad997334f4d743b3cafe0abf15cca46d4cf97b94d67ccfe` | unchanged |
  | `README.md` | `fef3c44408e4b39837af345095ccce7da798853fd60ea94a1de63afa9d3d67b3` | unchanged |
  | `LICENSE` (repo root) | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` | unchanged |

  `__init__.py` is new and empty, so the directory imports as the package
  name the modules use. Upstream's `evaluation_main.py` (an absl CLI) and
  `run.sh` are not fetched: `journal/baseline/ifeval_score.py` calls
  `evaluation_lib` directly.
- **Read before use:**
  - The code makes no network calls, starts no subprocesses, has no
    `eval`/`exec`, and opens only its input and output JSONL files.
  - It runs about 25 string checks on a response.
  - Its one load of external data was the pickle below.

## The one local change

`instructions_util._get_sentence_tokenizer` upstream unpickles
`nltk:tokenizers/punkt/english.pickle`. NLTK 3.8.2 and later refuse pickle
loading (CVE-2024-39705), and unpickling runs code anyway. The function
now returns `nltk.tokenize.PunktTokenizer("english")`. That is the same
Punkt English model, read from NLTK's pickle-free `punkt_tab` data. A
comment in the file marks the change.

The change is `local-change.patch` (a unified diff, upstream → the file the
experiments ran on; Apache 2.0 § 4(b)'s notice of modification). fetch.py
applies it with an exact-context applier (no fuzz) and refuses a result
whose sha256 is not the patched one in the table.

Upstream's unit tests pass with it in `.venv-ifeval` (2026-10-24):
`instructions_test` 41 OK, `instructions_util_test` 7 OK.

## The environment

`make venv-ifeval` builds `.venv-ifeval/` at the repo root (ignored). It
is separate from the project's `.venv` and is never imported from it. It
installs the four upstream requirements at the versions in
`requirements.lock`, and NLTK's `punkt_tab` into `.venv-ifeval/nltk_data`.
Run the tests (after `make bench-std`) with:

```
cd journal/baseline/bench/v1-std/ifeval_checker
NLTK_DATA=../../../../../.venv-ifeval/nltk_data ../../../../../.venv-ifeval/bin/python -m instruction_following_eval.instructions_test
```

The bench's own test (`tests/test_baseline/test_ifeval_score.py`) skips
when `.venv-ifeval`, the checker or the slice's data are absent.
