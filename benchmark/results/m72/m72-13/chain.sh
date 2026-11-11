#!/bin/zsh
# M72 1.3 real-model criteria after A5: A4 (a)(b)(c), divergence, A6 served smoke per arm. Fail-fast; every step's rc logged.
set -u
O=$STACK_WORKDIR/m72/real-s21; F=$STACK_WORKDIR/fe-m72-13; A=$STACK_WORKDIR/fe-m72-13/arm; L=$O/chain.log
log() { echo "[$(date +%H:%M:%S)] $*" >> $L; }
pwr() { pmset -g ac | awk '/Wattage|Voltage/{printf "%s ", $0}'; pmset -g batt | grep -o '[0-9]*%' | head -1; }
gpu() { ioreg -r -d 1 -c IOAccelerator | grep -o '"Device Utilization %"=[0-9]*' | head -1; }
mon() { while true; do echo "[$(date +%H:%M:%S)] MON $(pwr) gpu $(gpu)" >> $O/monitor.log; sleep 300; done }
until grep -q 'RC=' $STACK_WORKDIR/m72/a5-s21/run.log 2>/dev/null; do sleep 30; done
grep -q 'RC=0' $STACK_WORKDIR/m72/a5-s21/run.log || { log "A5 failed: stop"; exit 20; }
mon & mpid=$!
trap 'kill $mpid 2>/dev/null' EXIT
log "start $(pwr)"; sleep 300
run() { log "BEGIN $1"; shift; "$@" >> $O/steps.log 2>&1; rc=$?; log "END rc=$rc"; [ $rc -eq 0 ] || exit 21; }
PY=(uv run --project $STACK_REPO python)
export PYTHONPATH=$STACK_WORKDIR/fe-m72-13/impl/mlx-vlm STACK_WORKDIR=$STACK_WORKDIR/fe-m72-13/impl/workdir
cd $STACK_WORKDIR/fe-m72-13/impl/mlx_local_stack
run "a4 exact 8192"  $PY $O/m72_13_realmodel.py --check a4 --mode m72_exact --T 8192  --out $O/a4-exact-8192.json
run "a4 exact 32768" $PY $O/m72_13_realmodel.py --check a4 --mode m72_exact --T 32768 --out $O/a4-exact-32768.json
run "a4 v1 8192"     $PY $O/m72_13_realmodel.py --check a4 --mode m72_v1    --T 8192  --out $O/a4-v1-8192.json
run "diverge v1"     $PY $O/m72_13_realmodel.py --check diverge --mode m72_v1    --out $O/diverge-v1.json
run "diverge exact"  $PY $O/m72_13_realmodel.py --check diverge --mode m72_exact --out $O/diverge-exact.json
$PY $O/m72_13_realmodel.py --compare $O/diverge-v1.json $O/diverge-exact.json > $O/diverge-compare.json 2>> $O/steps.log || exit 22
unset PYTHONPATH
export STACK_WORKDIR=$STACK_WORKDIR
for arm in v1 exact; do
  W=$A/stack-$arm; cd $W
  log "BEGIN arm $arm setup"
  git -c protocol.file.allow=always -c submodule.src/mlx-vlm.url=$HOME/ws/mlx-vlm -c submodule.src/mlx-serve.url=$HOME/ws/mlx-serve submodule update --init src/mlx-vlm src/mlx-serve >> $O/steps.log 2>&1 || exit 23
  uv sync -q >> $O/steps.log 2>&1 || exit 24
  [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c LISTEN)" = "0" ] || { log ":8000 busy before start"; exit 25; }
  mkdir -p logs
  ( set -a; . $STACK_REPO/.env; set +a; env -u APC_ENABLED MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=$W/main_models.yaml nohup uv run mlx-serve start > logs/main_model.log 2>&1 < /dev/null & )
  for i in $(seq 1 120); do curl -sf http://127.0.0.1:8000/health >/dev/null && break; sleep 2; done
  log "router up for $arm: $(lsof -nP -t -iTCP:8000 -sTCP:LISTEN)"
  run "smoke $arm" uv run --project $STACK_REPO python $O/m72_13_served_smoke.py --arm-registry $W/main_models.yaml --arm-log $W/logs/main_model.log --out $O/smoke-$arm.json
  grep -E 'cmdline|--model|--draft-kind|--tq4-attention' logs/main_model.log | head -5 >> $O/steps.log
  cp logs/main_model.log $O/main_model-$arm.log
  bash $W/scripts/stack_stop.sh >> $O/steps.log 2>&1 || { log "stop failed"; exit 26; }
  log "stopped $arm; :8000 listeners: $(lsof -nP -t -iTCP:8000 -sTCP:LISTEN | wc -l)"
done
log "ALL DONE"
