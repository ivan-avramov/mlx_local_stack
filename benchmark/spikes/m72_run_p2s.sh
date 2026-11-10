#!/bin/zsh
# M72 P2' stage 1 (C314): two --mode p2s passes (p2s-1 --arm-order forward, p2s-2 --arm-order reverse), 600 s idle
# between; power + GPU utilization logged before each pass and every 60 s. The probe's own power and idle-GPU gates
# refuse before measuring.
# Usage: benchmark/spikes/m72_run_p2s.sh <out_dir>. Exit: 0, 10 = <out_dir> already holds p2s-1.json / p2s-2.json
# (nothing run), or 11 / 12 = the first failing pass (never masked).
set -u
if (( $# != 1 )); then echo "usage: $0 <out_dir>" >&2; exit 2; fi
for p in p2s-1 p2s-2; do
  if [[ -e "$1/$p.json" ]]; then echo "REFUSED: $1/$p.json exists (use a fresh out_dir)" >&2; exit 10; fi
done
mkdir -p "$1" || exit 2
out=${1:A}
cd "${0:A:h}/../.." || exit 2
export PYTHONPATH=../mlx-vlm
gpu() { ioreg -r -c IOAccelerator -d 1 -k PerformanceStatistics | grep -o '"Device Utilization %"=[0-9]*'; }
pwr() { echo "$(pmset -g ac | grep -E 'Wattage|Voltage' | tr -s ' \n' ' ') batt $(pmset -g batt | grep -o '[0-9]*%')"; }
mon() { while true; do echo "[$(date +%H:%M:%S)] MON $(pwr) gpu $(gpu)" >>"$out/monitor.log"; sleep 60; done }
mon & mpid=$!
trap "kill $mpid" EXIT
run() {
  echo "[$(date +%H:%M:%S)] PRE $1 $(pwr) gpu $(gpu)" >>"$out/launcher.log"
  echo "[$(date +%H:%M:%S)] BEGIN $1 arm-order $2" >>"$out/launcher.log"
  uv run python benchmark/spikes/m72_tq4_probe.py --mode p2s --arm-order "$2" --out "$out/$1.json" >"$out/$1.log" 2>&1
  local rc=$?
  echo "[$(date +%H:%M:%S)] END $1 rc=$rc" >>"$out/launcher.log"
  return $rc
}
run p2s-1 forward || exit 11
echo "[$(date +%H:%M:%S)] IDLE 600s" >>"$out/launcher.log"
sleep 600
run p2s-2 reverse || exit 12
echo "[$(date +%H:%M:%S)] ALL DONE" >>"$out/launcher.log"
