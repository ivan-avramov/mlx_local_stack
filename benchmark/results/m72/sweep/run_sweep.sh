#!/bin/zsh
# M72 tuning step 1: two block-plan sweep passes (forward / reverse setting order), 600 s idle between; power + GPU every 60 s.
set -u
out=$1; cd "$2"; export PYTHONPATH=../mlx-vlm
gpu() { ioreg -r -c IOAccelerator -d 1 -k PerformanceStatistics | grep -o '"Device Utilization %"=[0-9]*'; }
mon() { while true; do echo "[$(date +%H:%M:%S)] MON $(pmset -g ac | grep -E 'Wattage|Voltage' | tr -s ' \n' ' ') gpu $(gpu)" >>"$out/monitor.log"; sleep 60; done }
mon & mpid=$!
trap "kill $mpid" EXIT
run() { echo "[$(date +%H:%M:%S)] BEGIN $1 $2 gpu $(gpu)" >>"$out/launcher.log"
  uv run python benchmark/spikes/m72_mma_sweep.py --out "$out/$1.json" --order "$2" >"$out/$1.log" 2>&1; local rc=$?
  echo "[$(date +%H:%M:%S)] END $1 rc=$rc" >>"$out/launcher.log"; return $rc; }
run sweep-1 forward || exit 11
echo "[$(date +%H:%M:%S)] IDLE 600s" >>"$out/launcher.log"; sleep 600
run sweep-2 reverse || exit 12
echo "[$(date +%H:%M:%S)] ALL DONE" >>"$out/launcher.log"
