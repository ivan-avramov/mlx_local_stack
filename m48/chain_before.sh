#!/bin/bash
W="$HOME/ws/mlx_local_stack_workdir/m48"
while pgrep -f "parity_replay run.*m48-before-mtp-on" >/dev/null; do sleep 15; done
grep -q "^rc=0" "$W/parity/before_on.log" || { echo "before_on did not finish rc=0; not starting OFF arm" >> "$W/chain_before.log"; exit 1; }
"$W/parity_off_arm.sh" m48-before-mtp-off >> "$W/chain_before.log" 2>&1
echo "chain_before done $(date +%H:%M:%S)" >> "$W/chain_before.log"
