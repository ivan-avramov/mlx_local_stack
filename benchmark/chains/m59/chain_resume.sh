#!/bin/bash
# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m59/chain_resume.sh, the driver behind the opencode_v2_*.m59.* (M59) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m59"; R="$HOME/ws/mlx_local_stack"
cd "$R" && set -a && . ./.env 2>/dev/null; set +a; unset APC_ENABLED
"$R/.venv-bench/bin/python" "$D/run_m59.py" chain s1 s2 > "$D/run_m59_chain_resume.out" 2>&1; echo $? > "$D/chain.rc"
