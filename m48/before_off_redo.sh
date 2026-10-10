#!/bin/bash
# After chain_after: redo the BEFORE MTP-off arm on the pre-M48 fork (7199aca0), then restore the bump and the daily driver.
W="$HOME/ws/mlx_local_stack_workdir/m48"; R=$STACK_REPO
log() { echo "[$(date +%H:%M:%S)] $*" >> "$W/before_off_redo.log"; }
while ! grep -q "chain_after done" "$W/chain_after.log" 2>/dev/null; do sleep 30; done
cd "$R" && git -C src/mlx-vlm checkout -q 7199aca0 && log "submodule at $(git -C src/mlx-vlm rev-parse --short HEAD) (pre-M48)"
"$W/parity_off_arm.sh" m48-before-mtp-off-redo; log "before off redo rc=$?"
git -C src/mlx-vlm checkout -q 1bd249d3 && git add src/mlx-vlm && log "submodule restored to $(git -C src/mlx-vlm rev-parse --short HEAD)"
cd "$R"; unset APC_ENABLED; nohup ./runserver.sh > logs/runserver.out 2>&1 </dev/null & log "daily driver restarted pid $!"
log "before_off_redo done"
