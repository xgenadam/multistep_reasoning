#!/usr/bin/env bash
# Q-04 remaining slow-tier order (2026-10-23): after the Devstral layer-split run ends,
#   1. Devstral-2 row-split speed check: bespoke set, --repeat 1 (24 calls), cost column only;
#   2. Qwen3-235B-A22B (MoE): launcher default, layer split;
#   3. Mistral-Medium-3.5-128B (dense): SPLIT=row.
# Each step waits for its download. Stops at once if the watchdog's halt flag is set.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
halted() { [ -f "$HOME/models/.gpu-halt" ] && { echo "halt flag set; chain stops"; exit 7; }; }
wait_dl() { until grep -qE "done  .*$1|FAILED" "$HOME/models/.download.log"; do sleep 30; done; }
until grep -q '^=== done devstral' runs/q04/devstral-2-123b-q3km-run.log 2>/dev/null; do halted; sleep 30; done
halted
echo "=== devstral row-split speed check ($(date -u +%FT%TZ))"
f=$(ls "$HOME"/models/Devstral-2-123B-Instruct-2512-GGUF/Q3_K_M/*00001-of-*.gguf)
SPLIT=row scripts/server/judge-llama-server.sh "${f#$HOME/models/}" devstral-2-123b-q3km 8092 > runs/q04/devstral-row-boot.log 2>&1 \
  && JUDGE_BASE_URL=http://localhost:8092/v1 JUDGE_MODEL=devstral-2-123b-q3km .venv/bin/python journal/baseline/quality.py judge \
     --pairs journal/baseline/bench/validation/pairs.yaml --repeat 1 --jobs 1 --thinking off --seed 0 \
     --label q04-devstral-2-123b-q3km-rowsplit > runs/q04/devstral-row-run.log 2>&1
scripts/server/judge-llama-server.sh stop
tail -3 runs/q04/devstral-row-run.log
for job in "Qwen3-235B-A22B|UD-Q2_K_XL|qwen3-235b-a22b-q2kxl|layer" "Mistral-Medium-3.5-128B|mistralai_Mistral-Medium-3.5-128B-Q3_K_M|mistral-medium-3.5-128b-q3km|row"; do
  IFS='|' read -r name sub alias split <<<"$job"
  wait_dl "$name"; halted
  f=$(ls "$HOME/models/$name-GGUF/$sub/"*00001-of-*.gguf) || { echo "$alias: file missing"; continue; }
  echo "=== $alias split=$split ($(date -u +%FT%TZ))"
  SPLIT=$split scripts/server/q04-run-judge.sh "${f#$HOME/models/}" "$alias" > "runs/q04/$alias-run.log" 2>&1
  echo "$alias exit $?"
done
echo "=== chain done ($(date -u +%FT%TZ))"
