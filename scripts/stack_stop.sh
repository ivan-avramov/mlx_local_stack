#!/bin/bash
# Stop the full stack (runserver.sh, router, workers, compose) and VERIFY :8000 is free.
# Kills by PID and escalates to KILL: `kill -TERM` on runserver.sh has left the shell AND the
# router alive (2026-09-28: a lean router then failed to bind and a parity arm silently ran
# against the daily driver). Exit 1 if :8000 is still bound after the sweep.
set -u
R="$(cd "$(dirname "$0")/.." && pwd)"
sweep() { for p in $(pgrep -f "$1"); do kill "-$2" "$p" 2>/dev/null; done; }
sweep "bash ./runserver.sh" TERM; sleep 8; sweep "bash ./runserver.sh" KILL
sweep "mlx-serve start|mlx_vlm.server|mlx_vlm/server" TERM; sleep 5
sweep "mlx-serve start|mlx_vlm.server|mlx_vlm/server" KILL
(cd "$R" && docker compose down >/dev/null 2>&1)
for _ in $(seq 1 30); do
  [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c LISTEN)" = "0" ] && { echo "stack_stop: :8000 free"; exit 0; }
  sleep 2
done
echo "stack_stop: :8000 STILL BOUND by: $(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $1, $2}' | tr '\n' ' ')" >&2
exit 1
