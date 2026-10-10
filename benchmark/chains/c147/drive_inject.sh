#!/bin/bash
# Detached launch of the C147 injected-positive driver; run as `nohup drive_inject.sh &`.
# Output $STACK_WORKDIR/m62/inject/{inject.out,inject.rc,RUNLOG.md}; inject.rc carries the driver's exit code.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
R="$(cd "$(dirname "$0")/../../.." && pwd)"
D="$STACK_WORKDIR/m62/inject"
PY="${C147_PY:-$R/.venv-bench/bin/python}"
mkdir -p "$D"
/bin/rm -f "$D/inject.rc"
cd "$R" && "$PY" "$R/benchmark/chains/c147/run_inject.py" "$@" > "$D/inject.out" 2>&1 < /dev/null; rc=$?
echo $rc > "$D/inject.rc"
exit $rc
