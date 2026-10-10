#!/bin/bash
# M58 gate phase under joint_v1+ab: router restart, seeded pilot, straddle probe, cold capacity rungs, decode runner 64K/128K.
set -u
R=$STACK_REPO; W=$HOME/ws/mlx_local_stack_workdir/m58; G=$W/gate; M=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
O=$W/overlays/joint_v1_ab.yaml; PY=$R/.venv-bench/bin/python
log() { echo "$(date -u +%FT%TZ) $*" >> $G/status.log; }
cd $R
scripts/stack_stop.sh >> $G/status.log 2>&1
[ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "0" ] || { log "ABORT :8000 still bound"; exit 9; }
MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=$O nohup uv run mlx-serve start > $G/router.log 2>&1 < /dev/null &
for i in $(seq 1 60); do [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "1" ] && break; sleep 1; done
rp=$(lsof -nP -iTCP:8000 -sTCP:LISTEN | tail -n +2 | awk '{print $2}' | head -1); log "router pid=$rp config=$(ps -o command= -E -p $rp | tr ' ' '\n' | grep '^MLX_SERVE_CONFIG=' ) session_max=$(ps -o command= -E -p $rp | tr ' ' '\n' | grep '^MLX_VLM_CACHE_SESSION_MAX=')"
log "pilot start"
MLX_SERVE_CONFIG=$O PYTHONPATH=$R/benchmark $PY $W/decode_probe.py run --model $M --contexts 8192,131072 --prompts-per-rung 5 --seed-base 201 --min-emitted-tokens 1024 --sampling-profile deployed --tag pilot-ab --out $G/pilot_ab.json --watch-log $G/pilot_ab.watch.log > $G/pilot_ab.log 2>&1; rc=$?; log "pilot exit=$rc"; [ $rc -eq 0 ] || exit $rc
log "worker cmdline: $(ps -axo args | grep -F mlx_vlm.server | grep -F "$M" | grep -v grep | grep -o -- '--mtp-verify[^ ]* [^ ]*\|--mtp-verify-ab\|--draft-kind [^ ]*' | tr '\n' ' ')"
log "straddle start"
$PY $W/straddle_probe.py --cpt 4.611 --out $G/straddle_ab.json > $G/straddle_ab.log 2>&1; rc=$?; log "straddle exit=$rc $(tail -1 $G/straddle_ab.log)"; [ $rc -eq 0 ] || exit $rc
log "capacity start"
( cd $R/benchmark && MLX_SERVE_CONFIG=$O ../.venv-bench/bin/python -m bench.run_capacity --model $M --sampling-profile deployed --grid 8192,65536,131072,262144 --out-tag m58-g1a-ab --no-preload > $G/capacity_ab.log 2>&1 ); rc=$?; log "capacity exit=$rc"; [ $rc -eq 0 ] || exit $rc
log "decode64/128 start"
MLX_SERVE_CONFIG=$O PYTHONPATH=$R/benchmark $PY $W/decode_probe.py run --model $M --contexts 65536,131072 --prompts-per-rung 3 --seed-base 301 --min-emitted-tokens 1024 --sampling-profile deployed --tag g1a-ab --out $G/decode_ab.json --watch-log $G/decode_ab.watch.log > $G/decode_ab.log 2>&1; rc=$?; log "decode exit=$rc"; [ $rc -eq 0 ] || exit $rc
log "GATE_DONE"
