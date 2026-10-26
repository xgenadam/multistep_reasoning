# OpenCode v1.19.3 (official image, pinned by digest) plus Python and bash, for the real-world tier of the
# external-harness comparison (journal/design/lead-worker.md): the agent may run code and tests. Packages come from
# Alpine's repositories at build time; their versions are recorded in the design note.
FROM ghcr.io/anomalyco/opencode@sha256:6ebc13097f2381301220abe9d1b2a54f50cd1603a910dc1c66e93d8f2c4e8ebb
RUN apk add --no-cache python3 py3-pytest bash && python3 --version && apk info -v python3 py3-pytest bash
