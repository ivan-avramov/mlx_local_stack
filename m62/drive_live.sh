#!/bin/bash
# M62 V3 + V4 (operator go 2026-10-10). rc in live.rc.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m62"; R="$HOME/ws/mlx_local_stack"
/bin/rm -f "$D/live.rc"
cd "$R" && "$R/.venv-bench/bin/python" "$D/run_m62_live.py" v3 v4 > "$D/live.out" 2>&1; rc=$?
echo $rc > "$D/live.rc"
