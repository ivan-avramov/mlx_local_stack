#!/bin/bash
# M48 AFTER phase on the bumped stack: fresh runserver, smoke, leg C (pick), leg B opencode with a 20K tool
# result, parity AFTER (MTP on). Leaves the stack UP. Caller then runs parity_off_arm.sh m48-after-mtp-off.
set -u
W="$HOME/ws/mlx_local_stack_workdir/m48"; R=$STACK_REPO; cd "$R"
log() { echo "[$(date +%H:%M:%S)] $*" >> "$W/after_arm.log"; }
RS=$(pgrep -f "bash ./runserver.sh" | head -1); [ -n "$RS" ] && { kill -TERM "$RS"; for i in $(seq 1 60); do pgrep -f "bash ./runserver.sh" >/dev/null || break; sleep 2; done; }
for p in $(pgrep -f "mlx_vlm.server|mlx-serve start"); do kill -TERM "$p" 2>/dev/null; done; sleep 5
unset APC_ENABLED
nohup ./runserver.sh > logs/runserver.out 2>&1 </dev/null & log "runserver pid $!"
for i in $(seq 1 90); do R1=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null); O=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/health 2>/dev/null); [ "$R1" = "200" ] && [ "$O" = "200" ] && break; sleep 10; done; log "health router=$R1 owui=$O"
ps -Eww -o command= -p $(pgrep -f "mlx-serve start" | head -1) | tr ' ' '\n' | grep -E "^APC_|^MLX_VLM_CACHE_SESSION_MAX=|^MLX_SERVE_CONFIG=" | sort -u | tr '\n' ' ' >> "$W/after_arm.log"; echo >> "$W/after_arm.log"
cd benchmark; export PYTHONPATH=. MLX_SERVE_CONFIG=../main_models.yaml
../.venv/bin/python -m bench.stack_smoke --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --tag m48-after > "$W/smoke_after_pick.log" 2>&1; log "smoke pick rc=$?"
pgrep -fl "mlx_vlm.server" | grep -o "\-\-model [^ ]*\|--draft-kind [^ ]*\|--cache-session-retain-prompt-end [^ ]*" >> "$W/after_arm.log"
../.venv/bin/python -m bench.session_cache_probe --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --legs C --tag m48-after --workdir "$W/probe_after" --out "$W/legC_after_pick.json" > "$W/legC_after_pick.log" 2>&1; log "legC after rc=$?"
../.venv/bin/python -m bench.session_cache_probe --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --legs B --turns 6 --big-file-tokens 20000 --tag m48-after-b --workdir "$W/probe_after_b" --out "$W/legB_after_pick.json" > "$W/legB_after_pick.log" 2>&1; log "legB after rc=$?"
../.venv/bin/python -m bench.stack_smoke --model Qwen3.8-27B-mlx-uniform-4bit --tag m48-after > "$W/smoke_after_second.log" 2>&1; log "smoke second rc=$?"
../.venv/bin/python -m bench.parity_replay run --frozen "$HOME/ws/mlx_local_stack_workdir/upstream/2026-09-14-activation/quality-v2/frozen-after.json" --tag m48-after-mtp-on --out "$W/parity/after_on.json" > "$W/parity/after_on.log" 2>&1; log "parity after(on) rc=$?"
sysctl vm.swapusage >> "$W/after_arm.log"; grep -c "memory.pressure" "$R/logs/main_model.log" >> "$W/after_arm.log" 2>/dev/null
log "AFTER phase done"
