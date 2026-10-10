#!/bin/bash
# Stop the full stack / any router and VERIFY :8000 is free. Kills by PID; escalates to KILL.
R=$STACK_REPO
for p in $(pgrep -f "bash ./runserver.sh"); do kill -TERM "$p" 2>/dev/null; done
sleep 8
for p in $(pgrep -f "bash ./runserver.sh"); do kill -KILL "$p" 2>/dev/null; done
for p in $(pgrep -f "mlx-serve start|mlx_vlm.server|mlx_vlm/server"); do kill -TERM "$p" 2>/dev/null; done
sleep 5
for p in $(pgrep -f "mlx-serve start|mlx_vlm.server|mlx_vlm/server"); do kill -KILL "$p" 2>/dev/null; done
(cd "$R" && docker compose down >/dev/null 2>&1)
for i in $(seq 1 30); do [ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c LISTEN)" = "0" ] && exit 0; sleep 2; done
echo "stack_stop: :8000 still bound" >&2; exit 1
