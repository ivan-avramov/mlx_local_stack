#!/bin/zsh
# M72 1.2 D1+D2: two --mode mq passes, 10-min idle between; GPU-idle + floor + power logged before each; 60 s monitor.
set -u
out=$1; floor=$2; cd "$3"; export PYTHONPATH=../mlx-vlm
mon() { while true; do echo "[$(date +%H:%M:%S)] MON $(pmset -g ac | grep -E 'Wattage|Voltage' | tr -s ' \n' ' ') batt $(pmset -g batt | grep -o '[0-9]*%') gpu $(ioreg -r -c IOAccelerator -d 1 -k PerformanceStatistics | grep -o '"Device Utilization %"=[0-9]*')" >>"$out/monitor.log"; sleep 60; done }
mon & mpid=$!
trap "kill $mpid" EXIT
pre() { echo "[$(date +%H:%M:%S)] PRE $1 gpu $(ioreg -r -c IOAccelerator -d 1 -k PerformanceStatistics | grep -o '"Device Utilization %"=[0-9]*') $(uv run python $floor)" >>"$out/launcher.log"; }
run() { pre $1; echo "[$(date +%H:%M:%S)] BEGIN $1" >>"$out/launcher.log"
  uv run python benchmark/spikes/m72_tq4_probe.py --mode mq --out "$out/$1.json" >"$out/$1.log" 2>&1; local rc=$?
  echo "[$(date +%H:%M:%S)] END $1 rc=$rc" >>"$out/launcher.log"; return $rc; }
run mq-1 || exit 11
echo "[$(date +%H:%M:%S)] IDLE 600s" >>"$out/launcher.log"; sleep 600
run mq-2 || exit 12
echo "[$(date +%H:%M:%S)] ALL DONE" >>"$out/launcher.log"
