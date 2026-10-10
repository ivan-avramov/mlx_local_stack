#!/bin/bash
W="$HOME/ws/mlx_local_stack_workdir/m48"; R=$STACK_REPO
log() { echo "[$(date +%H:%M:%S)] $*" >> "$W/chain_after.log"; }
while ! grep -q "chain_before done" "$W/chain_before.log" 2>/dev/null; do sleep 20; done
log "BEFORE arms done; bumping src/mlx-vlm"
cd "$R" && git -C src/mlx-vlm fetch -q $HOME/ws/mlx-vlm main && git -C src/mlx-vlm checkout -q 1bd249d3 && git add src/mlx-vlm && log "submodule at $(git -C src/mlx-vlm rev-parse --short HEAD)"
"$W/after_arm.sh"; log "after_arm rc=$?"
"$W/parity_off_arm.sh" m48-after-mtp-off >> "$W/chain_after.log" 2>&1; log "after off arm done"
cd "$R"; unset APC_ENABLED; nohup ./runserver.sh > logs/runserver.out 2>&1 </dev/null & log "daily driver restarted pid $!"
for i in $(seq 1 90); do curl -sf http://localhost:8000/health >/dev/null 2>&1 && curl -s http://localhost:3000/health >/dev/null 2>&1 && break; sleep 10; done
log "chain_after done"
