#!/usr/bin/env bash
# Serve one GGUF judge with llama.cpp inside the nested podman engine (Q-04).
# The container shares this box's network namespace, so the judge answers at
# http://localhost:$PORT/v1 and quality.py takes JUDGE_BASE_URL=http://localhost:$PORT/v1.
#
# Usage:  scripts/server/judge-llama-server.sh <gguf path under ~/models> <served name> [port]
#         scripts/server/judge-llama-server.sh stop
# Knobs:  CTX (default 16384; judge prompts run ~4K tokens), PARALLEL (default 1: one slot, clean per-call wall), NGL (999),
#         KV (q8_0), SPLIT (layer; row is faster for dense models but not every MoE path), TS (tensor split, default 0.25,0.25,0.25,0.25), EXTRA (appended).
# The nested engine ignores --gpus; only --device nvidia.com/gpu=all passes the cards (AGENTS.md).
set -euo pipefail
IMAGE="${IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda}"
NAME="${NAME:-judge_llama}"
if [ "${1:-}" = stop ]; then docker stop -t 30 "$NAME" >/dev/null 2>&1 || true; docker rm -f "$NAME" >/dev/null 2>&1 || true; echo "stopped $NAME"; exit 0; fi
MODEL_REL="${1:?gguf path relative to ~/models}"; ALIAS="${2:?served model name}"; PORT="${3:-8092}"
CTX="${CTX:-16384}"; PARALLEL="${PARALLEL:-1}"; NGL="${NGL:-999}"; KV="${KV:-q8_0}"; SPLIT="${SPLIT:-layer}"
TS="${TS:-0.25,0.25,0.25,0.25}"
[ -f "$HOME/models/.gpu-halt" ] && { echo "GPU HALT flag set by the watchdog: $(cat "$HOME/models/.gpu-halt"); see ~/models/.gpu-watchdog.log" >&2; exit 7; }
test -f "$HOME/models/$MODEL_REL" || { echo "MODEL MISSING at ~/models/$MODEL_REL" >&2; exit 3; }
docker stop -t 30 "$NAME" >/dev/null 2>&1 || true; docker rm -f "$NAME" >/dev/null 2>&1 || true
if curl -s -m 3 -o /dev/null "http://localhost:$PORT/v1/models"; then echo "port $PORT already answers; stop that server first" >&2; exit 5; fi
busy=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>1000' | wc -l)
[ "$busy" -eq 0 ] || { echo "a GPU has >1 GB in use; one process owns the GPUs at a time" >&2; exit 6; }
docker run -d --name "$NAME" --restart no --device nvidia.com/gpu=all \
  --network host --ipc host --ulimit memlock=-1:-1 \
  -v "$HOME/models:/models:ro" \
  "$IMAGE" \
    -m "/models/$MODEL_REL" --alias "$ALIAS" --host 0.0.0.0 --port "$PORT" \
    --n-gpu-layers "$NGL" --ctx-size "$CTX" --parallel "$PARALLEL" \
    --split-mode "$SPLIT" --tensor-split "$TS" --flash-attn on \
    --cache-type-k "$KV" --cache-type-v "$KV" \
    --batch-size 1024 --ubatch-size 512 --jinja --metrics ${EXTRA:-} >/dev/null
echo "launched $NAME model=$MODEL_REL alias=$ALIAS port=$PORT ctx=$CTX parallel=$PARALLEL kv=$KV split=$SPLIT"
t0=$(date +%s)
until curl -s -m 3 "http://localhost:$PORT/health" 2>/dev/null | grep -q '"ok"'; do
  docker ps --format '{{.Names}}' | grep -qx "$NAME" || { docker logs "$NAME" 2>&1 | tail -20; echo "$NAME exited during load" >&2; exit 1; }
  [ $(( $(date +%s) - t0 )) -gt 1800 ] && { echo "not ready after 30 min" >&2; exit 1; }
  sleep 5
done
echo "READY after $(( $(date +%s) - t0 ))s (load time for the Q-04 swap-cost column)"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
