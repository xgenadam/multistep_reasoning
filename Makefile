# Interpreter rule: use .venv/bin/python if present, else
# dsh-podman-venv/bin/python (which has no interpreter in the agent container).
# The LLM endpoint is never defaulted (D-P): export LLM_BASE_URL, e.g.
#   export LLM_BASE_URL=http://host.containers.internal:5000/v1

# 3.12 only: see requires-python in pyproject.toml. uv fetches a managed
# 3.12 when the box has none; without uv, python3.12 must be on PATH.
PYTHON ?= 3.12
VENV   := .venv
PY     := $(VENV)/bin/python

.PHONY: venv test smoke check board

venv:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python $(PYTHON) $(VENV) && \
		uv pip install --python $(PY) -e '.[test]'; \
	else \
		python$(PYTHON) -m venv $(VENV) && \
		$(PY) -m pip install -e '.[test]'; \
	fi

test:
	$(PY) -m pytest tests/ -q

smoke:
	$(PY) journal/baseline/harness.py --smoke

# Usage: make check RUN=journal/baseline/runs/<file>.json
check:
	$(PY) journal/baseline/check.py $(RUN)

board:
	@echo 'make board: placeholder until O-01 adds journal/board.py'
