#!/usr/bin/env bash
# Sequential Hugging Face downloads into ~/models (Q-04 judge candidates).
# Queue: ~/models/.download-queue.txt, one job per line: <repo> <include-glob> <local-dir-under-~/models>
# Log:   ~/models/.download.log. Re-run after appending to the queue; a finished queue exits 0.
set -u
export PATH="$HOME/.local/bin:$PATH"
Q="$HOME/models/.download-queue.txt"; LOG="$HOME/models/.download.log"
touch "$Q"
while :; do
  sed -i '/^[[:space:]]*$/d' "$Q"
  line=$(head -n 1 "$Q"); [ -z "$line" ] && { echo "$(date -u +%FT%TZ) queue empty" >> "$LOG"; break; }
  set -- $line; repo=$1; inc=$2; dir=$3
  echo "$(date -u +%FT%TZ) start $repo $inc -> ~/models/$dir" >> "$LOG"
  if hf download "$repo" --include "$inc" --local-dir "$HOME/models/$dir" >> "$LOG" 2>&1; then
    echo "$(date -u +%FT%TZ) done  $repo ($(du -sh "$HOME/models/$dir" | cut -f1))" >> "$LOG"
    tail -n +2 "$Q" > "$Q.tmp" && mv "$Q.tmp" "$Q"
  else
    echo "$(date -u +%FT%TZ) FAILED $repo (left at the head of the queue)" >> "$LOG"; exit 1
  fi
done
