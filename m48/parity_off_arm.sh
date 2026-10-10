#!/bin/bash
# Usage: parity_off_arm.sh <tag> — lean router on the draft-OFF overlay, replay the 40 frozen requests, stop.
# Verifies (1) :8000 free before start, (2) the lean router owns :8000, (3) the worker has NO --draft-kind.
set -u
TAG="$1"; W="$HOME/ws/mlx_local_stack_workdir/m48"; R=$STACK_REPO
"$W/stack_stop.sh" || { echo "ABORT $TAG: could not free :8000" >> "$W/parity/${TAG}.log"; exit 1; }
cd "$R"; set -a; . ./.env 2>/dev/null; set +a; unset APC_ENABLED
MLX_VLM_CACHE_SESSION_MAX=2 MLX_SERVE_CONFIG="$W/overlay_draft_off.yaml" nohup uv run mlx-serve start > "logs/main_model_overlay_${TAG}.log" 2>&1 </dev/null &
for i in $(seq 1 60); do curl -sf http://localhost:8000/health >/dev/null 2>&1 && break; sleep 5; done
OWNER=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | head -1)
grep -q "overlay_draft_off" <(ps -Eww -o command= -p "$OWNER" 2>/dev/null | tr ' ' '\n') || { echo "ABORT $TAG: :8000 owner $OWNER is not the overlay router" >> "$W/parity/${TAG}.log"; exit 1; }
cd benchmark
PYTHONPATH=. MLX_SERVE_CONFIG="$W/overlay_draft_off.yaml" ../.venv/bin/python -m bench.parity_replay run \
  --frozen "$HOME/ws/mlx_local_stack_workdir/upstream/2026-09-14-activation/quality-v2/frozen-after.json" \
  --tag "$TAG" --out "$W/parity/${TAG}.json" > "$W/parity/${TAG}.log" 2>&1
echo "rc=$?" >> "$W/parity/${TAG}.log"
pgrep -fl "mlx_vlm.server" | grep -o "\-\-model [^ ]*\|--draft-kind [^ ]*" >> "$W/parity/${TAG}.log"
echo "router owner pid $OWNER; overlay $W/overlay_draft_off.yaml" >> "$W/parity/${TAG}.log"
"$W/stack_stop.sh"; echo "stopped; :8000 listeners $(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c LISTEN)" >> "$W/parity/${TAG}.log"
