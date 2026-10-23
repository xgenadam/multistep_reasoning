#!/usr/bin/env bash
# Serve one GGUF judge with llama.cpp inside the nested podman engine (Q-04).
# The container shares this box's network namespace, so the judge answers at
# http://localhost:$PORT/v1 and quality.py takes JUDGE_BASE_URL=http://localhost:$PORT/v1.
#
# Usage:  scripts/server/judge-llama-server.sh <gguf path under ~/models> <served name> [port]
#         scripts/server/judge-llama-server.sh stop
# Knobs:  CTX (default 16384; judge prompts run ~4K tokens), PARALLEL (default 1: one slot, clean per-call wall), NGL (999),
#         KV (q8_0), SPLIT (layer; row is faster for dense models but not every MoE path), TS (tensor split, default 0.25,0.25,0.25,0.25), EXTRA (appended),
#         DRY_RUN=1 (print the docker run command and the refusal checks, start and stop nothing; exit 0).
# Also the llama.cpp path of scripts/server/generator-server.sh (NAME=gen_llama), so keep the knobs and output stable.
# The nested engine ignores --gpus; only --device nvidia.com/gpu=all passes the cards (AGENTS.md).
set -euo pipefail
IMAGE="${IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda}"
NAME="${NAME:-judge_llama}"
if [ "${1:-}" = stop ]; then docker stop -t 30 "$NAME" >/dev/null 2>&1 || true; docker rm -f "$NAME" >/dev/null 2>&1 || true; echo "stopped $NAME"; exit 0; fi
MODEL_REL="${1:?gguf path relative to ~/models}"; ALIAS="${2:?served model name}"; PORT="${3:-8092}"
CTX="${CTX:-16384}"; PARALLEL="${PARALLEL:-1}"; NGL="${NGL:-999}"; KV="${KV:-q8_0}"; SPLIT="${SPLIT:-layer}"
TS="${TS:-0.25,0.25,0.25,0.25}"
run_cmd() {  # $1 = split mode; the docker run argv, one place for the boot and DRY_RUN
  RUN=(docker run -d --name "$NAME" --restart no --device nvidia.com/gpu=all
    --network host --ipc host --ulimit memlock=-1:-1
    -v "$HOME/models:/models:ro"
    "$IMAGE"
      -m "/models/$MODEL_REL" --alias "$ALIAS" --host 0.0.0.0 --port "$PORT"
      --n-gpu-layers "$NGL" --ctx-size "$CTX" --parallel "$PARALLEL"
      --split-mode "$1" --tensor-split "$TS" --flash-attn on
      --cache-type-k "$KV" --cache-type-v "$KV"
      --batch-size 1024 --ubatch-size 512 --jinja --metrics)
  # EXTRA is word-split on purpose (several flags in one knob); keep its values free of spaces.
  # shellcheck disable=SC2206
  RUN+=(${EXTRA:-})
}
if [ "${DRY_RUN:-0}" = 1 ]; then
  run_cmd "$SPLIT"; echo "DRY_RUN: would run:"; printf ' %q' "${RUN[@]}"; echo
  [ -f "$HOME/models/.gpu-halt" ] && echo "DRY_RUN: would REFUSE: halt flag set ($(cat "$HOME/models/.gpu-halt"))"
  [ -f "$HOME/models/$MODEL_REL" ] || echo "DRY_RUN: would REFUSE: model missing at ~/models/$MODEL_REL"
  curl -s -m 3 -o /dev/null "http://localhost:$PORT/v1/models" && echo "DRY_RUN: port $PORT answers now (a real boot first stops $NAME, then refuses if it still answers)"
  echo "DRY_RUN: GPU memory used (MiB): $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>&1 | tr '\n' ' ')(a real boot refuses above 1000 on any card)"
  exit 0
fi
[ -f "$HOME/models/.gpu-halt" ] && { echo "GPU HALT flag set by the watchdog: $(cat "$HOME/models/.gpu-halt"); see ~/models/.gpu-watchdog.log" >&2; exit 7; }
test -f "$HOME/models/$MODEL_REL" || { echo "MODEL MISSING at ~/models/$MODEL_REL" >&2; exit 3; }
docker stop -t 30 "$NAME" >/dev/null 2>&1 || true; docker rm -f "$NAME" >/dev/null 2>&1 || true
if curl -s -m 3 -o /dev/null "http://localhost:$PORT/v1/models"; then echo "port $PORT already answers; stop that server first" >&2; exit 5; fi
busy=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>1000' | wc -l)
[ "$busy" -eq 0 ] || { echo "a GPU has >1 GB in use; one process owns the GPUs at a time" >&2; exit 6; }
boot() {  # $1 = split mode; returns 0 when healthy, 2 when the model failed to load
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  run_cmd "$1"; "${RUN[@]}" >/dev/null
  echo "launched $NAME model=$MODEL_REL alias=$ALIAS port=$PORT ctx=$CTX parallel=$PARALLEL kv=$KV split=$1"
  t0=$(date +%s)
  until curl -s -m 3 "http://localhost:$PORT/health" 2>/dev/null | grep -q '"ok"'; do
    docker ps --format '{{.Names}}' | grep -qx "$NAME" || { docker logs "$NAME" 2>&1 | tail -20; echo "$NAME exited during load" >&2; return 2; }
    [ $(( $(date +%s) - t0 )) -gt 1800 ] && { echo "not ready after 30 min" >&2; exit 1; }
    sleep 5
  done
}
# This llama.cpp build cannot load some models with row split ("does not support split buffers",
# 2026-10-23); fall back to layer split and say so, so the cost row records the mode actually used.
if ! boot "$SPLIT"; then
  if [ "$SPLIT" != layer ] && docker logs "$NAME" 2>&1 | grep -q 'does not support split buffers'; then
    echo "SPLIT FALLBACK: $SPLIT unsupported for this model in this build; booting with layer"; SPLIT=layer
    boot layer || exit 1
  else exit 1; fi
fi
echo "split_used=$SPLIT"
echo "READY after $(( $(date +%s) - t0 ))s (load time for the Q-04 swap-cost column)"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
