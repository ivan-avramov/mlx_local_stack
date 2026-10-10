#!/bin/bash
# M2 Stage-1 screens ONLY (n=15 humanevalplus, deployed profile) — ladders deferred to a
# quiet-box moment per ruling 8 (45.6 GB co-resident baseline, 8% free at launch time).
set -u
REPO="$HOME/ws/mlx_local_stack"
LOG="$HOME/ws/mlx_local_stack_workdir/status/m2_qwen38.log"
MODELS="Qwen3.8-27B-mlx-uniform-4bit Qwen3.8-27B-static-mixed-4bit Qwen3.8-27B-OptiQ-4.5bpw-mixed"
cd "$REPO/benchmark" || exit 1
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
say "=== M2 SCREENS-ONLY start (ladders deferred) ==="
for M in $MODELS; do
  say "--- stage-1 screen (n=15 humanevalplus, deployed): $M"
  nohup ../.venv-bench/bin/python m1/bench_watch.py --models "$M" --bench humanevalplus --total 15 \
    --driver-pattern "run.py generate" --out "$HOME/ws/mlx_local_stack_workdir/status/m2_watch_$M.md" \
    --interval 300 >/dev/null 2>&1 &
  WPID=$!
  ../.venv-bench/bin/python run.py generate --models "$M" --benches humanevalplus --limit humanevalplus=15 \
    --sampling-profile deployed --order roundrobin --chunks all >> "$LOG" 2>&1
  say "screen rc=$? for $M"
  kill $WPID 2>/dev/null
  curl -s -X POST localhost:8000/v1/models/unload -H 'Content-Type: application/json' -d "{\"model\":\"$M\"}" >/dev/null
done
say "=== M2 SCREENS COMPLETE ==="
