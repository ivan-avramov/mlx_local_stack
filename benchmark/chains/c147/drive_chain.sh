#!/bin/bash
# Detached launch of the C147 tg1 chain runner; the operator runs it as `nohup drive_chain.sh <runner args> &`.
#   drive_chain.sh pilot
#   drive_chain.sh chain s1 s2 reload --probe-code-sha <sha from run_opencode_probe_v2.py --print-identity>
# Output $STACK_WORKDIR/c147/{chain.out,chain.rc,RUNLOG.md,chain.json}; chain.rc carries the runner's exit code
# (0 done, 2 abort, 3 STOP). Stop cleanly with: touch "$STACK_WORKDIR/c147/STOP".
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
R="$(cd "$(dirname "$0")/../../.." && pwd)"
D="$STACK_WORKDIR/c147"
PY="${C147_PY:-$R/.venv-bench/bin/python}"
mkdir -p "$D"
/bin/rm -f "$D/chain.rc"
cd "$R" && "$PY" "$R/benchmark/chains/c147/run_tg1_chain.py" "$@" > "$D/chain.out" 2>&1 < /dev/null; rc=$?
echo $rc > "$D/chain.rc"
exit $rc
