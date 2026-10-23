#!/usr/bin/env bash
# GPU watchdog for agent-run GPU work. Samples every INTERVAL s; on a trip it puts the box in a safe state:
#   1. writes ~/models/.gpu-halt (judge-llama-server.sh refuses to boot while it exists),
#   2. kills the Q-04 run chain (q04-run-judge.sh, quality.py judge) and the Q-02 experiment drivers
#      (journal/baseline/arms.py, journal/baseline/harness.py) so nothing re-launches or keeps sending requests,
#   3. stops every GPU container: the judge (judge_llama), the generators (gen_<generator>, vllm_qwen38fn_3090) and any
#      other container from a CUDA image. The nested podman records --device nvidia.com/gpu=all nowhere in
#      `inspect` (HostConfig.Devices is [] on 2026-10-23), so the names and the image's NVIDIA_VISIBLE_DEVICES
#      are what identify a GPU container,
#   4. logs the reason. Downloads are left running (no GPU).
# Clear with: rm ~/models/.gpu-halt  (after a human or the agent has looked at the log).
# Trips: core temp >= HARD (any sample); core temp >= SOFT for SUSTAIN consecutive samples; hardware or
# thermal slowdown active; fan <= 0 % while core > 70 C; power above the limit + 5 %; nvidia-smi failing
# 3 samples in a row (lost GPU / Xid). GDDR6X memory junction temp is NOT readable on these cards (N/A).
# Log: ~/models/.gpu-watchdog.log (WARN at WARN C, one line per minute while warm; TRIP lines).
set -u
INTERVAL="${INTERVAL:-5}"; WARN="${WARN:-83}"; SOFT="${SOFT:-88}"; HARD="${HARD:-92}"; SUSTAIN="${SUSTAIN:-3}"
LOG="$HOME/models/.gpu-watchdog.log"; HALT="$HOME/models/.gpu-halt"
soft_n=0; fail_n=0; last_warn=0
log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }
safe_state() {
  log "TRIP: $1"; echo "$(date -u +%FT%TZ) $1" > "$HALT"
  pkill -f 'q04-chain.sh' 2>/dev/null; pkill -f 'q04-run-judge.sh' 2>/dev/null; pkill -f 'quality.py judge' 2>/dev/null
  # pkill patterns are extended regexes. The drivers run as `<venv>/bin/python [-flags] [path/]arms.py ...`;
  # the pattern needs the interpreter, so an editor or a grep that names the file survives.
  pkill -f 'python[0-9.]*( +-[^ ]+)* +([^ ]*/)?(arms|harness)\.py' 2>/dev/null
  for c in $(docker ps --format '{{.Names}}' 2>/dev/null); do
    case "$c" in judge_llama|gen_*|vllm_qwen38fn_3090) gpu=1 ;; *) gpu=0 ;; esac
    if [ $gpu = 1 ] || docker inspect -f '{{json .HostConfig}} {{json .Config.Env}}' "$c" 2>/dev/null | grep -qE 'nvidia.com/gpu|NVIDIA_VISIBLE_DEVICES'; then
      docker stop -t 20 "$c" >/dev/null 2>&1; log "stopped container $c"
    fi
  done
  # A server can outlive its container record in the nested podman (2026-10-23 21:34Z: `docker ps` listed no
  # gen_* while its llama-server kept 11 GB per card and ran for 9 more minutes), so whatever still holds a GPU
  # context is killed by PID: TERM, then KILL after 10 s.
  sleep 5
  for sig in TERM KILL; do
    for p in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits 2>/dev/null | sort -u); do
      cmd=$(ps -o comm= -p "$p" 2>/dev/null); kill -s $sig "$p" 2>/dev/null && log "killed ($sig) GPU process $p $cmd"
    done
    [ $sig = TERM ] && sleep 10
  done
  sleep 15; log "after stop: $(nvidia-smi --query-gpu=index,temperature.gpu,memory.used --format=csv,noheader 2>&1 | tr '\n' ';')"
}
log "start interval=${INTERVAL}s warn=$WARN soft=$SOFT x$SUSTAIN hard=$HARD"
while :; do
  out=$(nvidia-smi --query-gpu=index,temperature.gpu,fan.speed,power.draw,power.limit,clocks_throttle_reasons.hw_slowdown,clocks_throttle_reasons.hw_thermal_slowdown --format=csv,noheader,nounits 2>&1)
  if [ $? -ne 0 ] || [ "$(echo "$out" | wc -l)" -lt 4 ]; then
    fail_n=$((fail_n+1)); log "nvidia-smi problem ($fail_n): $(echo "$out" | head -2 | tr '\n' ' ')"
    if [ $fail_n -ge 3 ] && [ ! -f "$HALT" ]; then safe_state "nvidia-smi failed 3 samples in a row"; fi
    sleep "$INTERVAL"; continue
  fi
  fail_n=0; reason=""; maxt=0; soft_hit=0
  while IFS=', ' read -r i t fan pw pl hws hwt; do
    [ "$t" -gt "$maxt" ] && maxt=$t
    [ "$t" -ge "$HARD" ] && reason="GPU$i core ${t}C >= hard $HARD"
    [ "$t" -ge "$SOFT" ] && soft_hit=1
    [ "$hws" = Active ] || [ "$hwt" = Active ] && reason="GPU$i hardware slowdown active (hw=$hws thermal=$hwt) at ${t}C"
    [ "${fan%%.*}" -le 0 ] 2>/dev/null && [ "$t" -gt 70 ] && reason="GPU$i fan at ${fan}% with core ${t}C"
    awk -v p="$pw" -v l="$pl" 'BEGIN{exit !(p > l*1.05)}' && reason="GPU$i power ${pw}W over limit ${pl}W"
  done <<< "$out"
  if [ $soft_hit = 1 ]; then soft_n=$((soft_n+1)); else soft_n=0; fi
  [ $soft_n -ge "$SUSTAIN" ] && reason="core >= ${SOFT}C for $soft_n samples (max ${maxt}C)"
  if [ -n "$reason" ]; then
    [ -f "$HALT" ] || safe_state "$reason"
  elif [ "$maxt" -ge "$WARN" ] && [ $(( $(date +%s) - last_warn )) -ge 60 ]; then
    log "WARN max core ${maxt}C: $(echo "$out" | awk -F', ' '{printf "GPU%s %sC fan%s%% %sW; ", $1,$2,$3,$4}')"; last_warn=$(date +%s)
  fi
  sleep "$INTERVAL"
done
