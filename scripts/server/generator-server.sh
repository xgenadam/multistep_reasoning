#!/usr/bin/env bash
# Serve one Q-02 generator on this box (4 x RTX 3090, 96 GiB VRAM), one at a time; the judge keeps :8092.
#
# Usage:  scripts/server/generator-server.sh <flash-next|qwen3.8-27b|qwen3.6-35b-a3b>
#         scripts/server/generator-server.sh stop
#
#   generator        engine     port  served name (the experiment driver sends it; vLLM 404s on a wrong one)
#   flash-next       vLLM       8090  qwen3.8-flash-next   the user's prefix lane, unmodified (prefix caching on)
#   qwen3.8-27b      llama.cpp  8093  qwen3.8-27b          ~/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q6_K.gguf
#   qwen3.6-35b-a3b  llama.cpp  8094  qwen3.6-35b-a3b      ~/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
# Base URL: http://localhost:<port>/v1 (host network). Prints READY after <n>s, the per-card VRAM and /v1/models.
#
# Knobs: DRY_RUN=1 (print the resolved command, start nothing), PARALLEL (llama.cpp slots, default 5),
#        SLOT_CTX (tokens per slot, default 65536), KV (llama.cpp KV type, default f16), SPLIT (per-model default
#        below), TS, EXTRA (more llama-server flags), FN_LANE (the flash-next launcher), FN_NAME (its container).
# Refuses (as judge-llama-server.sh does) when ~/models/.gpu-halt exists, a card has > 1 GB in use, or the port
# already answers. `stop` stops gen_llama and the flash-next container (vllm_qwen38fn_3090: the lane's default name,
# shared with the flash-next judge; one process owns the GPUs at a time, so stop takes whichever is up) and waits
# for the cards to drop under 1 GB.
#
# Slots and context. The campaign runs 3 jobs at once and the harness's scenarios run in a thread pool; nothing in
# the pipeline issues concurrent calls inside a turn (run_multi_concurrent in llama_utils.py is used only by its
# tests). 5 slots = the 3 jobs plus headroom, and the same 5 the :5000 generator had. Each slot gets 65,536 tokens:
# a single-call arm with up to 3 "continue" turns at max_tokens 8192 reaches ~40K. llama-server splits --ctx-size
# across slots (no unified KV when --parallel is set), so --ctx-size = 5 x 65,536 = 327,680. That is above the
# models' 262,144 training context in total, but no single sequence exceeds 65,536.
#
# Fit (GGUF metadata, read 2026-10-23). Both are hybrids: Gated DeltaNet blocks with full attention every 4th
# block (full_attention_interval 4); only the attention blocks hold a per-token KV cache, so KV is small.
#   qwen3.8-27b (qwen35, dense): 65 blocks = 48 DeltaNet + 16 attention + 1 MTP (nextn) block; 4 KV heads x 256.
#     KV f16 per token = 17 x 4 x 256 x 2 (K,V) x 2 B = 68 KiB -> 327,680 tokens = 21.3 GiB (q8_0 would be 11.3).
#     Recurrent state ~150 MiB per slot (48 x 48 heads x 128 x 128 f32 + conv). Weights 20.5 GiB (Q6_K).
#     Total ~43 GiB + compute buffers of 96 GiB.
#   qwen3.6-35b-a3b (qwen35moe, 256 experts, 8 active): 40 blocks = 30 DeltaNet + 10 attention; 2 KV heads x 256.
#     KV f16 per token = 10 x 2 x 256 x 2 x 2 B = 20 KiB -> 327,680 tokens = 6.3 GiB. Recurrent ~63 MiB per slot.
#     Weights 20.6 GiB (Q4_K_M). Total ~28 GiB.
# KV f16 (not the judge's q8_0): both fit with > 50 GiB to spare, so the generators take no KV-quantisation loss.
# Split: layer for both. Row split would suit the dense 27B, but this build (llama.cpp c7fc50941) cannot load the
# qwen35 architecture with it: SPLIT=row failed to load and fell back to layer on 2026-10-23, so row only costs a
# failed boot. Layer split keeps the KV of each layer on its card, and 0.25 x 4 spreads the weights evenly.
# Thinking: requests carry chat_template_kwargs.enable_thinking. llama.cpp gets --jinja (in the judge launcher)
# and --reasoning-format deepseek, so thinking comes back in message.reasoning_content and not as <think> in
# content. The server-side default is enable_thinking false, the same default as the flash-next lane.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEN_NAME=gen_llama
FN_NAME="${FN_NAME:-vllm_qwen38fn_3090}"
FN_LANE="${FN_LANE:-$HOME/workspace/AI/Qwen38-Flash-Next-4x3090/vllm-w4a16/launch/launch-qwen38fn-w4a16-prefix.sh}"
gpu_mem() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits; }

if [ "${1:-}" = stop ]; then
  for c in "$GEN_NAME" "$FN_NAME"; do
    if docker ps --format '{{.Names}}' | grep -qx "$c"; then
      docker stop -t 60 "$c" >/dev/null 2>&1 || true; docker rm -f "$c" >/dev/null 2>&1 || true; echo "stopped $c"
    fi
  done
  docker rm -f "$GEN_NAME" >/dev/null 2>&1 || true   # an exited gen_llama; leave an exited lane container to the lane
  for _ in $(seq 1 24); do [ "$(gpu_mem | awk '$1>1000' | wc -l)" -eq 0 ] && break; sleep 5; done
  echo "GPU memory used (MiB): $(gpu_mem | tr '\n' ' ')"
  [ "$(gpu_mem | awk '$1>1000' | wc -l)" -eq 0 ] || { echo "a GPU still has >1 GB in use after stop" >&2; exit 6; }
  exit 0
fi

GEN="${1:?usage: generator-server.sh <flash-next|qwen3.8-27b|qwen3.6-35b-a3b|stop>}"
case "$GEN" in
  flash-next)      PORT=8090; SERVED=qwen3.8-flash-next ;;
  qwen3.8-27b)     PORT=8093; SERVED=qwen3.8-27b;     MODEL_REL=Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q6_K.gguf;          DEF_SPLIT=layer ;;
  qwen3.6-35b-a3b) PORT=8094; SERVED=qwen3.6-35b-a3b; MODEL_REL=Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf; DEF_SPLIT=layer ;;
  *) echo "unknown generator '$GEN' (flash-next|qwen3.8-27b|qwen3.6-35b-a3b|stop)" >&2; exit 2 ;;
esac

show_models() { echo "/v1/models: $(curl -s -m 10 "http://localhost:$PORT/v1/models")"
  curl -s -m 10 "http://localhost:$PORT/v1/models" | grep -q "\"$SERVED\"" || { echo "served name $SERVED not listed" >&2; exit 4; }; }

if [ "$GEN" != flash-next ]; then
  PARALLEL="${PARALLEL:-5}"; SLOT_CTX="${SLOT_CTX:-65536}"
  export NAME="$GEN_NAME" PARALLEL CTX=$(( PARALLEL * SLOT_CTX )) KV="${KV:-f16}" SPLIT="${SPLIT:-$DEF_SPLIT}"
  export TS="${TS:-0.25,0.25,0.25,0.25}" DRY_RUN="${DRY_RUN:-0}"
  export EXTRA="--reasoning-format deepseek --chat-template-kwargs {\"enable_thinking\":false}${EXTRA:+ $EXTRA}"
  echo "generator $GEN: port=$PORT served=$SERVED slots=$PARALLEL x $SLOT_CTX ctx=$CTX kv=$KV split=$SPLIT"
  "$HERE/judge-llama-server.sh" "$MODEL_REL" "$SERVED" "$PORT"   # refusals, boot, health wait, READY, VRAM
  [ "$DRY_RUN" = 1 ] || show_models
  exit 0
fi

# flash-next: the user's prefix lane (prefix -> tuned -> qwen38fn-w4a16-3090-tp4.sh), run as is with PORT, NAME and
# GPU_ARGS; the nested podman ignores --gpus, so the cards pass only with --device nvidia.com/gpu=all.
test -f "$FN_LANE" || { echo "flash-next lane missing at $FN_LANE" >&2; exit 3; }
FN_ENV=(PORT="$PORT" NAME="$FN_NAME" GPU_ARGS="--device nvidia.com/gpu=all")
if [ "${DRY_RUN:-0}" = 1 ]; then
  # The lane has no dry run and must not be modified: run it with a docker shim first on PATH that prints the
  # `docker run` argv and fails it (exit 99), and makes stop/rm no-ops. Nothing is started or stopped.
  shim=$(mktemp -d); trap 'rm -rf "$shim"' EXIT
  cat > "$shim/docker" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = run ]; then printf 'DRY_RUN: would run: docker'; printf ' %q' "$@"; echo; exit 99; fi
exit 0
EOF
  chmod +x "$shim/docker"
  echo "generator flash-next: port=$PORT served=$SERVED lane=$FN_LANE name=$FN_NAME"
  echo "DRY_RUN: env ${FN_ENV[*]} bash $FN_LANE"
  rc=0; env PATH="$shim:$PATH" "${FN_ENV[@]}" bash "$FN_LANE" || rc=$?
  [ "$rc" -eq 99 ] || { echo "DRY_RUN: the lane stopped before docker run (exit $rc)" >&2; exit "$rc"; }
  [ -f "$HOME/models/.gpu-halt" ] && echo "DRY_RUN: would REFUSE: halt flag set ($(cat "$HOME/models/.gpu-halt"))"
  curl -s -m 3 -o /dev/null "http://localhost:$PORT/v1/models" && echo "DRY_RUN: would REFUSE: port $PORT answers"
  echo "DRY_RUN: GPU memory used (MiB): $(gpu_mem | tr '\n' ' ')(a real boot refuses above 1000 on any card)"
  exit 0
fi
[ -f "$HOME/models/.gpu-halt" ] && { echo "GPU HALT flag set by the watchdog: $(cat "$HOME/models/.gpu-halt"); see ~/models/.gpu-watchdog.log" >&2; exit 7; }
if curl -s -m 3 -o /dev/null "http://localhost:$PORT/v1/models"; then echo "port $PORT already answers; stop that server first" >&2; exit 5; fi
[ "$(gpu_mem | awk '$1>1000' | wc -l)" -eq 0 ] || { echo "a GPU has >1 GB in use; one process owns the GPUs at a time" >&2; exit 6; }
t0=$(date +%s)
env "${FN_ENV[@]}" bash "$FN_LANE"   # returns once the container runs and its overlays check out
until curl -s -m 3 -o /dev/null -w '%{http_code}' "http://localhost:$PORT/health" 2>/dev/null | grep -qx 200; do
  docker ps --format '{{.Names}}' | grep -qx "$FN_NAME" || { docker logs "$FN_NAME" 2>&1 | tail -20; echo "$FN_NAME exited during load" >&2; exit 1; }
  [ $(( $(date +%s) - t0 )) -gt 1800 ] && { echo "not ready after 30 min" >&2; exit 1; }
  sleep 5
done
echo "READY after $(( $(date +%s) - t0 ))s"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
show_models
