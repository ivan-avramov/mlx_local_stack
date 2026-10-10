#!/bin/bash
# M58 latency arms: A per_query, B joint_v1 (AB off); order A→B then B→A; 10-min idle before every arm-session; fresh lean router each.
set -u
R=$STACK_REPO; W=$HOME/ws/mlx_local_stack_workdir/m58; G=$W/arms; mkdir -p $G; M=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
PY=$R/.venv-bench/bin/python
log() { echo "$(date -u +%FT%TZ) $*" >> $G/status.log; }
state() { echo "power=$(pmset -g ac | tr -s ' ' | grep -o 'Wattage = [0-9]*W') batt=$(pmset -g batt | grep -o '[0-9]*%') swap=$(sysctl -n vm.swapusage | grep -o 'used = [0-9.]*M') free=$(memory_pressure 2>/dev/null | tail -1 | grep -o '[0-9]*%')"; }
arm() { # $1 = arm (A|B), $2 = session (s1|s2), $3 = overlay
  cd $R; scripts/stack_stop.sh >> $G/status.log 2>&1
  [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "0" ] || { log "ABORT :8000 bound"; exit 9; }
  [ "$(ps -axo args | grep -E 'mlx_vlm.server|decode_probe|run_capacity' | grep -v grep | wc -l | tr -d ' ')" = "0" ] || { log "ABORT stray processes"; exit 9; }
  log "idle 600s before $1-$2 ($(state))"; sleep 600
  log "start $1-$2 state: $(state)"
  MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=$3 nohup uv run mlx-serve start > $G/router.$1-$2.log 2>&1 < /dev/null &
  for i in $(seq 1 60); do [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "1" ] && break; sleep 1; done
  log "$1-$2 router pid=$(lsof -nP -iTCP:8000 -sTCP:LISTEN | tail -n +2 | awk '{print $2}' | head -1) overlay=$3"
  ( cd $R/benchmark && MLX_SERVE_CONFIG=$3 ../.venv-bench/bin/python -m bench.run_capacity --model $M --sampling-profile deployed --grid 8192,65536,131072,262144 --out-tag m58-$1-$2 > $G/capacity.$1-$2.log 2>&1 ); rc=$?
  log "$1-$2 capacity exit=$rc worker=$(ps -axo args | grep -F mlx_vlm.server | grep -F "$M" | grep -v grep | grep -o -- '--mtp-verify[^ ]* [^ ]*\|--attention-policy [^ ]*' | tr '\n' ' ')"; [ $rc -eq 0 ] || exit $rc
  MLX_SERVE_CONFIG=$3 PYTHONPATH=$R/benchmark $PY $W/decode_probe.py run --model $M --contexts 65536,131072,245760 --prompts-per-rung 3 --seed-base 401 --min-emitted-tokens 1024 --sampling-profile deployed --tag m58-$1-$2 --out $G/decode.$1-$2.json --watch-log $G/decode.$1-$2.watch.log > $G/decode.$1-$2.log 2>&1; rc=$?
  log "$1-$2 decode exit=$rc end state: $(state)"; [ $rc -eq 0 ] || exit $rc
}
arm B s1 $W/overlays/joint_v1.yaml
arm B s2 $W/overlays/joint_v1.yaml
arm A s2 $W/overlays/per_query.yaml
cd $R; scripts/stack_stop.sh >> $G/status.log 2>&1
log "ARMS_DONE"
