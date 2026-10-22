#!/usr/bin/env bash
# Q-04: one candidate judge end to end. Boots the GGUF with judge-llama-server.sh (load time and
# VRAM are the swap-cost columns), runs the bespoke validation set (both orders, --repeat 2, Q-1/Q-5),
# then the standard slice (both orders, --repeat 1), and stops the server.
# Usage: scripts/server/q04-run-judge.sh <gguf path under ~/models> <alias>
# Knobs: SKIP_STD=1 (bespoke only), KEEP=1 (leave the server up), PORT (8092), plus the launcher's knobs.
# Verdict files land in journal/baseline/verdicts/ (quality.py's default); boot logs in runs/q04/.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
MODEL_REL="${1:?gguf path relative to ~/models}"; ALIAS="${2:?alias}"; PORT="${PORT:-8092}"
PY=.venv/bin/python; Q=journal/baseline/quality.py
mkdir -p runs/q04; BOOT="runs/q04/$ALIAS-boot.log"
echo "=== boot $ALIAS ($(date -u +%FT%TZ))"
scripts/server/judge-llama-server.sh "$MODEL_REL" "$ALIAS" "$PORT" 2>&1 | tee "$BOOT" || { echo "boot failed"; exit 1; }
LOAD_S=$(grep -oE 'READY after [0-9]+s' "$BOOT" | grep -oE '[0-9]+')
VRAM=$(grep -E '^[0-3], [0-9]+ MiB' "$BOOT" | awk -F', ' '{s+=$2} END {print s}')
echo "load_s=$LOAD_S vram_mib_total=$VRAM"
export JUDGE_BASE_URL="http://localhost:$PORT/v1" JUDGE_MODEL="$ALIAS"
echo "=== bespoke set ($(date -u +%FT%TZ))"
$PY $Q judge --pairs journal/baseline/bench/validation/pairs.yaml --repeat 2 --jobs 1 --thinking off --seed 0 --label "q04-$ALIAS" 2>&1 | tail -14
if [ "${SKIP_STD:-0}" != 1 ]; then
  echo "=== standard slice ($(date -u +%FT%TZ))"
  $PY $Q judge --pairs journal/baseline/bench/std/pairs.yaml --repeat 1 --jobs 1 --thinking off --seed 0 --label "q04-$ALIAS-std" 2>&1 | grep -vE '^(L[NIOM]|J[CR])[0-9]{3} ' | tail -12
fi
[ "${KEEP:-0}" = 1 ] || scripts/server/judge-llama-server.sh stop
echo "=== done $ALIAS ($(date -u +%FT%TZ)) load_s=$LOAD_S vram_mib_total=$VRAM"
ls -t journal/baseline/verdicts/*q04-$ALIAS*.json 2>/dev/null | head -2
