#!/bin/zsh
# C317 (1): one order-balanced pipelined-eval round at 131,072 — layer / pipe2 / pipe2 / layer, 600 s idles, fresh process per leg
set -u
O=$STACK_WORKDIR/m72/e2e-s21
pwr() { pmset -g ac | awk '/Wattage|Voltage/{printf "%s ", $0}'; pmset -g batt | grep -o '[0-9]*%' | head -1; }
gpu() { ioreg -r -d 1 -c IOAccelerator | grep -o '"Device Utilization %"=[0-9]*' | head -1; }
mon() { while true; do echo "[$(date +%H:%M:%S)] MON $(pwr) gpu $(gpu)" >> $O/monitor.log; sleep 60; done }
mon & mpid=$!
echo "[$(date +%H:%M:%S)] start; idle 600 s after the smoke" >> $O/run.log; sleep 600
cd $STACK_REPO && export PYTHONPATH=../mlx-vlm:benchmark/spikes
uv run python benchmark/spikes/m72_e2e_prefill.py --tokens 131072 --legs tq4_p2s:layer tq4_p2s:pipe2 tq4_p2s:pipe2 tq4_p2s:layer --idle 600 --out $O/e2e-131072-pipe2.json >> $O/run.log 2>&1
rc=$?
kill $mpid
echo "[$(date +%H:%M:%S)] RC=$rc" >> $O/run.log
exit $rc
