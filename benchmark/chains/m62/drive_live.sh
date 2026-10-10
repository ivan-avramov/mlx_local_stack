#!/bin/bash
# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m62/drive_live.sh, the driver behind the opencode_v2_tg1_*.m62v3/.m62v4 (M62 V3/V4) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
# M62 V3 + V4 (operator go 2026-10-10). rc in live.rc.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m62"; R="$HOME/ws/mlx_local_stack"
/bin/rm -f "$D/live.rc"
cd "$R" && "$R/.venv-bench/bin/python" "$D/run_m62_live.py" v3 v4 > "$D/live.out" 2>&1; rc=$?
echo $rc > "$D/live.rc"
