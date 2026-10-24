# Interpreter rule: use .venv/bin/python if present, else
# dsh-podman-venv/bin/python (which has no interpreter in the agent container).
# The LLM endpoint is never defaulted (D-P): export LLM_BASE_URL, e.g.
#   export LLM_BASE_URL=http://host.containers.internal:5000/v1

# 3.12 only: see requires-python in pyproject.toml. uv fetches a managed
# 3.12 when the box has none; without uv, python3.12 must be on PATH.
PYTHON ?= 3.12
VENV   := .venv
PY     := $(VENV)/bin/python

.PHONY: venv venv-ifeval test smoke check board

venv:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python $(PYTHON) $(VENV) && \
		uv pip install --python $(PY) -e '.[test]'; \
	else \
		python$(PYTHON) -m venv $(VENV) && \
		$(PY) -m pip install -e '.[test]'; \
	fi

# Google's IFEval checker (bench/v1-std/ifeval_checker/SOURCE.md) in its own
# venv, never imported from .venv: pinned packages plus NLTK's pickle-free
# punkt_tab data.
IFEVAL_VENV := .venv-ifeval
IFEVAL_LOCK := journal/baseline/bench/v1-std/ifeval_checker/requirements.lock
venv-ifeval:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python $(PYTHON) $(IFEVAL_VENV) && \
		uv pip install --python $(IFEVAL_VENV)/bin/python -r $(IFEVAL_LOCK); \
	else \
		python$(PYTHON) -m venv $(IFEVAL_VENV) && \
		$(IFEVAL_VENV)/bin/python -m pip install -r $(IFEVAL_LOCK); \
	fi
	$(IFEVAL_VENV)/bin/python -I -c "import nltk; assert nltk.download('punkt_tab', download_dir='$(CURDIR)/$(IFEVAL_VENV)/nltk_data', quiet=True)"

test:
	$(PY) -m pytest tests/ -q

smoke:
	$(PY) journal/baseline/harness.py --smoke

# Usage: make check RUN=journal/baseline/runs/<file>.json
check:
	$(PY) journal/baseline/check.py $(RUN)

# Ticket table from front-matter + lint (O-4, O-6). Stdlib only, so it
# falls back to python3 when the venv is absent.
board:
	@$(if $(wildcard $(PY)),$(PY),python3) journal/board.py $(ARGS)
