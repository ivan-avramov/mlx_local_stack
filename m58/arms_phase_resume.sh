#!/bin/bash
# Resume after the A-s1 decode headroom refusal: rerun A-s1 decode on the SAME loaded instance (router still up), then B-s1, B-s2, A-s2.
set -u
R=$STACK_REPO; W=$HOME/ws/mlx_local_stack_workdir/m58; G=$W/arms; M=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed; PY=$R/.venv-bench/bin/python
log() { echo "$(date -u +%FT%TZ) $*" >> $G/status.log; }
source <(sed -n '/^state() /p; /^arm() /,/^}/p' $W/arms_phase.sh)
[ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN | grep -c LISTEN)" = "1" ] || { log "ABORT A-s1 router not up for the decode rerun"; exit 9; }
log "A-s1 decode RERUN (same loaded instance; contexts 65536,131072,245760) state: $(state)"
MLX_SERVE_CONFIG=$W/overlays/per_query.yaml PYTHONPATH=$R/benchmark $PY $W/decode_probe.py run --model $M --contexts 65536,131072,245760 --prompts-per-rung 3 --seed-base 401 --min-emitted-tokens 1024 --sampling-profile deployed --tag m58-A-s1 --out $G/decode.A-s1.json --watch-log $G/decode.A-s1.watch.log > $G/decode.A-s1.log 2>&1; rc=$?
log "A-s1 decode exit=$rc end state: $(state)"; [ $rc -eq 0 ] || exit $rc
arm B s1 $W/overlays/joint_v1.yaml
arm B s2 $W/overlays/joint_v1.yaml
arm A s2 $W/overlays/per_query.yaml
cd $R; scripts/stack_stop.sh >> $G/status.log 2>&1
log "ARMS_DONE"
