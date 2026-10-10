#!/bin/bash
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m59"; R="$HOME/ws/mlx_local_stack"
cd "$R" && set -a && . ./.env 2>/dev/null; set +a; unset APC_ENABLED
"$R/.venv-bench/bin/python" "$D/run_m59.py" chain s1 s2 > "$D/run_m59_chain_resume.out" 2>&1; echo $? > "$D/chain.rc"
