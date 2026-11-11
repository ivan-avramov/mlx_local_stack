#!/bin/zsh
set -u
O=$STACK_WORKDIR/m72/real-s21; A=$STACK_WORKDIR/fe-m72-13/arm; L=$O/chain.log
log() { echo "[$(date +%H:%M:%S)] $*" >> $L; }
smoke() { log "BEGIN smoke $1"; uv run --project $STACK_REPO python $O/m72_13_served_smoke.py --arm-registry $A/stack-$1/main_models.yaml --arm-log $A/stack-$1/logs/main_model.log --corpus-root $A/stack-$1/benchmark --out $O/smoke-$1.json >> $O/steps.log 2>&1; rc=$?; log "END smoke $1 rc=$rc"; cp $A/stack-$1/logs/main_model.log $O/main_model-$1.log; return $rc; }
stop() { bash $A/stack-$1/scripts/stack_stop.sh >> $O/steps.log 2>&1; rc=$?; log "stop $1 rc=$rc; :8000 listeners $(lsof -nP -t -iTCP:8000 -sTCP:LISTEN | wc -l | tr -d ' ')"; return $rc; }
smoke v1; r1=$?
stop v1 || exit 26
W=$A/stack-exact; cd $W
git -c protocol.file.allow=always -c submodule.src/mlx-vlm.url=$HOME/ws/mlx-vlm -c submodule.src/mlx-serve.url=$HOME/ws/mlx-serve submodule update --init src/mlx-vlm src/mlx-serve >> $O/steps.log 2>&1 || exit 23
uv sync -q >> $O/steps.log 2>&1 || exit 24
[ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c LISTEN)" = "0" ] || { log ":8000 busy"; exit 25; }
mkdir -p logs
( set -a; . $STACK_REPO/.env; set +a; env -u APC_ENABLED MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=$W/main_models.yaml nohup uv run mlx-serve start > logs/main_model.log 2>&1 < /dev/null & )
for i in $(seq 1 120); do curl -sf http://127.0.0.1:8000/health >/dev/null && break; sleep 2; done
log "router up for exact: $(lsof -nP -t -iTCP:8000 -sTCP:LISTEN)"
smoke exact; r2=$?
stop exact || exit 26
log "A6 DONE r1=$r1 r2=$r2"
