#!/bin/bash
# Stop the full stack (runserver.sh, router, workers, compose) and VERIFY :8000 is free.
# Kills by PID and escalates to KILL. Before M51 (2026-09-28) `kill -TERM` on runserver.sh left the
# shell AND the router alive (bash parks a trapped signal behind the foreground `docker compose
# logs -f`; a lean router then failed to bind and a parity arm silently ran against the daily
# driver). runserver.sh now tears down on TERM itself; this stays the belt-and-braces stop for
# stale shells, orphaned workers and routers started by hand. Exit 1 if :8000 is still bound.
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
