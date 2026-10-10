#!/bin/bash
# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m59/c137_then_chain.sh, the driver behind the opencode_v2_*.m59.* (M59) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
# C137 replay (fused_v1, then auto) followed by the M59 chain; each phase leaves an .rc marker. Detached via nohup.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m59"; R="$HOME/ws/mlx_local_stack"
cd "$R" && set -a && . ./.env 2>/dev/null; set +a; unset APC_ENABLED
PY="$R/.venv-bench/bin/python"
/bin/rm -f "$D/c137_fused.rc" "$D/c137_auto.rc" "$D/chain.rc"
M59_OVERLAY="$D/overlay_m59_draft_off.yaml" "$PY" "$D/c137_replay.py" fused_v1 > "$D/c137_fused.out" 2>&1; echo $? > "$D/c137_fused.rc"
M59_OVERLAY="$D/overlay_m59_draft_off_auto.yaml" "$PY" "$D/c137_replay.py" auto > "$D/c137_auto.out" 2>&1; echo $? > "$D/c137_auto.rc"
"$PY" "$D/run_m59.py" chain > "$D/run_m59_chain.out" 2>&1; echo $? > "$D/chain.rc"
