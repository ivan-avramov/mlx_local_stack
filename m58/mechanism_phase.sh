#!/bin/bash
# M58 mechanism session (non-latency): both arms under MLX_VLM_MTP_PROFILE=1 at 131072, same seeded prompts; profiler lines go to the
# worker's stderr = $TMPDIR/mlx-manager-logs/<model>.log (recreated per worker start) — copied to the workdir per arm.
set -u
R=$STACK_REPO; W=$HOME/ws/mlx_local_stack_workdir/m58; G=$W/mechanism; mkdir -p $G; M=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed; PY=$R/.venv-bench/bin/python
log() { echo "$(date -u +%FT%TZ) $*" >> $G/status.log; }
for arm in per_query joint_v1; do
  cd $R; scripts/stack_stop.sh >> $G/status.log 2>&1
  [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "0" ] || { log "ABORT :8000 bound"; exit 9; }
  MLX_VLM_MTP_PROFILE=1 MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=$W/overlays/$arm.yaml nohup uv run mlx-serve start > $G/router.$arm.log 2>&1 < /dev/null &
  for i in $(seq 1 60); do [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "1" ] && break; sleep 1; done
  log "$arm router pid=$(lsof -nP -iTCP:8000 -sTCP:LISTEN | tail -n +2 | awk '{print $2}' | head -1)"
  MLX_SERVE_CONFIG=$W/overlays/$arm.yaml PYTHONPATH=$R/benchmark $PY $W/decode_probe.py run --model $M --contexts 131072 --prompts-per-rung 2 --seed-base 501 --min-emitted-tokens 1024 --sampling-profile deployed --tag m58-mech-$arm --out $G/decode.$arm.json --watch-log $G/decode.$arm.watch.log > $G/decode.$arm.log 2>&1; rc=$?
  log "$arm decode exit=$rc"; /bin/cp -f "$TMPDIR/mlx-manager-logs/$M.log" $G/worker.$arm.log; [ $rc -eq 0 ] || exit $rc
done
cd $R; scripts/stack_stop.sh >> $G/status.log 2>&1; log "MECH_DONE"
