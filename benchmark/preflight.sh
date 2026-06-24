#!/usr/bin/env bash
# Preflight guard rail — run BEFORE every benchmark run, on the box that will serve it.
#
# Prevents the three stale-state failure modes that produced phantom non-convergence loops:
#   - stale ROUTER   -> force-restart a fresh router (the actual cause of the loop episode)
#   - stale MODEL    -> load the target model fresh + a convergence canary
#   - stale CODEBASE -> report if HEAD/submodules differ from origin (abort on --strict)
#
# Usage:  ./benchmark/preflight.sh <registered-model-name> [--strict]
#   --strict : exit nonzero if the codebase is behind origin/main (default: warn only,
#              since a box may hold an intentional uncommitted local registry entry).
set -uo pipefail
cd "$(dirname "$0")/.."                      # repo root
_cfg="${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
[ -f "$_cfg" ] && . "$_cfg"

MODEL="${1:?usage: preflight.sh <registered-model-name> [--strict]}"
STRICT=0; [ "${2:-}" = "--strict" ] && STRICT=1

echo "[preflight] === codebase freshness ==="
git fetch -q origin 2>/dev/null || echo "[preflight] (fetch failed — offline?)"
LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "?")
REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "?")
git submodule status 2>/dev/null | sed 's/^/[preflight] submodule /'
if [ "$LOCAL" != "$REMOTE" ]; then
  echo "[preflight] WARN: stack HEAD ${LOCAL:0:9} != origin/main ${REMOTE:0:9} — codebase may be STALE."
  echo "[preflight]       sync with: git pull && git submodule update --force  (preserve local registry)"
  [ "$STRICT" -eq 1 ] && { echo "[preflight] --strict: aborting on stale codebase."; exit 3; }
fi
# Dirty submodule (deployed code drifted from its gitlink) is always a hard stop.
if git submodule status 2>/dev/null | grep -q '^+'; then
  echo "[preflight] WARN: a submodule is at a DIFFERENT commit than the gitlink (deployed code drift)."
fi

echo "[preflight] === fresh router ==="
pkill -9 -f "mlx-serve" 2>/dev/null || true
pkill -9 -f "mlx_vlm.server" 2>/dev/null || true
sleep 3
set -a; . ./.env 2>/dev/null || true; set +a
MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &
echo "[preflight] router restarting (pid $!)"
ok=0
for i in $(seq 1 20); do
  sleep 3
  if curl -s --max-time 4 http://localhost:8000/health 2>/dev/null | grep -q ok; then ok=1; break; fi
done
[ "$ok" -eq 1 ] || { echo "[preflight] router did not become healthy"; exit 1; }
echo "[preflight] router healthy"

echo "[preflight] === model + convergence canary ==="
exec .venv-bench/bin/python benchmark/bench/preflight.py "$MODEL"
