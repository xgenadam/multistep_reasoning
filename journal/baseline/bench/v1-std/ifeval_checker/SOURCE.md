# Vendored: Google's IFEval checker

The official instruction-following checker from the IFEval paper (Zhou et
al., 2023). It scores bench v1-std's report entries (sr01–sr20) for Q-02
bias guard 4.1. The user adopted it on 2026-10-24 (option A: the official
checker, in its own environment).

- **Source:** `github.com/google-research/google-research`, directory
  `instruction_following_eval/`, at commit
  `e6890f85757dd84e27ca6df2dd30651dafad28e0` (2026-07-22). That commit is
  the latest one touching the directory on 2026-10-24.
- **Licence:** Apache 2.0 (`LICENSE`, the repository's licence file at that
  commit).
- **Files:** `evaluation_lib.py`, `instructions.py`,
  `instructions_registry.py`, `instructions_util.py`, the two upstream test
  files and `README.md`, copied unchanged except for the change below.
  `__init__.py` is new and empty, so the directory imports as the package
  name the modules use. Upstream's `evaluation_main.py` (an absl CLI) and
  `run.sh` are not vendored: `journal/baseline/ifeval_score.py` calls
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

Upstream's unit tests pass with it in `.venv-ifeval` (2026-10-24):
`instructions_test` 41 OK, `instructions_util_test` 7 OK.

## The environment

`make venv-ifeval` builds `.venv-ifeval/` at the repo root (ignored). It
is separate from the project's `.venv` and is never imported from it. It
installs the four upstream requirements at the versions in
`requirements.lock`, and NLTK's `punkt_tab` into `.venv-ifeval/nltk_data`.
Run the tests with:

```
cd journal/baseline/bench/v1-std/ifeval_checker
NLTK_DATA=../../../../../.venv-ifeval/nltk_data ../../../../../.venv-ifeval/bin/python -m instruction_following_eval.instructions_test
```

The bench's own test (`tests/test_baseline/test_ifeval_score.py`) skips
when `.venv-ifeval` is absent.
