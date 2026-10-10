#!/bin/bash
# Waits for the chain to exit, then P182 stall re-run, then the C137 shrink-off discriminator. rc markers per phase.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m59"; R="$HOME/ws/mlx_local_stack"; PY="$R/.venv-bench/bin/python"
while [ ! -f "$D/chain.rc" ]; do sleep 60; done
[ "$(cat "$D/chain.rc")" = "0" ] || { echo "chain rc=$(cat "$D/chain.rc"): not starting follow-ups" > "$D/after_chain.rc"; exit 1; }
sleep 30
cd "$R" && set -a && . ./.env 2>/dev/null; set +a; unset APC_ENABLED
/bin/rm -f "$D/stallprobe.rc" "$D/c137_noshrink.rc"
"$PY" "$D/run_m59.py" stallprobe > "$D/stallprobe.out" 2>&1; echo $? > "$D/stallprobe.rc"
M59_OVERLAY="$D/overlay_m59_draft_off_noshrink.yaml" "$PY" "$D/c137_replay.py" fused_v1_noshrink > "$D/c137_noshrink.out" 2>&1; echo $? > "$D/c137_noshrink.rc"
echo done > "$D/after_chain.rc"
