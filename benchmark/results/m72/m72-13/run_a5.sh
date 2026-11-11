#!/bin/zsh
# M72 1.3 A5 + A6 speed sanity + A7 real values: prompt 131,072, capacity 262,144 in every leg; candidate 3 fork in-process
set -u
O=$STACK_WORKDIR/m72/a5-s21
pwr() { pmset -g ac | awk '/Wattage|Voltage/{printf "%s ", $0}'; pmset -g batt | grep -o '[0-9]*%' | head -1; }
gpu() { ioreg -r -d 1 -c IOAccelerator | grep -o '"Device Utilization %"=[0-9]*' | head -1; }
mon() { while true; do echo "[$(date +%H:%M:%S)] MON $(pwr) gpu $(gpu)" >> $O/monitor.log; sleep 60; done }
mon & mpid=$!
cd $STACK_WORKDIR/fe-m72-13/impl/mlx_local_stack && export PYTHONPATH=$STACK_WORKDIR/fe-m72-13/impl/mlx-vlm:$STACK_WORKDIR/fe-m72-13/impl/mlx_local_stack/benchmark/spikes STACK_WORKDIR=$STACK_WORKDIR/fe-m72-13/impl/workdir
uv run --project $STACK_REPO python benchmark/spikes/m72_e2e_prefill.py --tokens 131072 --capacity 262144 --legs tq4_p2s:layer tq4_m72 tq4_m72 tq4_p2s:layer --idle 600 --out $O/a5-131072-cap262144.json >> $O/run.log 2>&1
rc=$?
kill $mpid
echo "[$(date +%H:%M:%S)] RC=$rc" >> $O/run.log
exit $rc
