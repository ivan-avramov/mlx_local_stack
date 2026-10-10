#!/bin/bash
# M58 G1b: parity replay of the first pick's C84 frozen set under per_query, joint_v1 and a per_query reload control.
set -u
R=$STACK_REPO; W=$HOME/ws/mlx_local_stack_workdir/m58; G=$W/g1b; mkdir -p $G; M=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
FROZEN=$HOME/ws/mlx_local_stack_workdir/upstream/2026-09-14-activation/quality-v2/frozen-after.json
log() { echo "$(date -u +%FT%TZ) $*" >> $G/status.log; }
session() { # $1 = tag, $2 = overlay
  cd $R; scripts/stack_stop.sh >> $G/status.log 2>&1
  [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "0" ] || { log "ABORT :8000 bound"; exit 9; }
  MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=$2 nohup uv run mlx-serve start > $G/router.$1.log 2>&1 < /dev/null &
  for i in $(seq 1 60); do [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "1" ] && break; sleep 1; done
  log "session $1 router pid=$(lsof -nP -iTCP:8000 -sTCP:LISTEN | tail -n +2 | awk '{print $2}' | head -1) overlay=$2"
  ( cd $R/benchmark && MLX_SERVE_CONFIG=$2 PYTHONPATH=. ../.venv-bench/bin/python -m bench.parity_replay run --frozen $FROZEN --models $M --tag m58-$1 --out $G/replay_$1.json > $G/replay_$1.log 2>&1 ); rc=$?
  log "session $1 replay exit=$rc worker=$(ps -axo args | grep -F mlx_vlm.server | grep -F "$M" | grep -v grep | grep -o -- '--mtp-verify[^ ]* [^ ]*' | tr '\n' ' ')"
  [ $rc -eq 0 ] || exit $rc
}
session per_query  $W/overlays/per_query.yaml
session joint_v1   $W/overlays/joint_v1.yaml
session per_query2 $W/overlays/per_query.yaml
cd $R/benchmark
PYTHONPATH=. ../.venv-bench/bin/python -m bench.parity_replay compare $G/replay_per_query.json $G/replay_per_query2.json > $G/compare_control.log 2>&1; log "compare control (per_query vs reload) exit=$?"
PYTHONPATH=. ../.venv-bench/bin/python -m bench.parity_replay compare $G/replay_per_query.json $G/replay_joint_v1.json > $G/compare_policy.log 2>&1; log "compare policy (per_query vs joint_v1) exit=$?"
log "G1B_DONE"
