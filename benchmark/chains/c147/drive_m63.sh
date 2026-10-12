#!/bin/bash
# Detached launch of the M63 MTP-ON tg1 chain (spec docs/specs/m63-mtp-on-tg1-arm.md); run as `nohup drive_m63.sh <runner args> &`.
#   drive_m63.sh chain s1 reload --smoke --probe-code-sha <sha>     rehearsal, out-root $STACK_WORKDIR/m63-smoke
#   drive_m63.sh chain s1 s2 reload --probe-code-sha <sha>          the ON arm, out-root $STACK_WORKDIR/m63
# Output <out-root>/{chain.out,chain.rc,RUNLOG.md,chain.json}; chain.rc carries the runner's exit code
# (0 done, 2 abort, 3 STOP). Stop cleanly with: touch "<out-root>/STOP".
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
R="$(cd "$(dirname "$0")/../../.." && pwd)"
D="$STACK_WORKDIR/m63"
for arg in "$@"; do
  [ "$arg" = "--smoke" ] && D="$STACK_WORKDIR/m63-smoke"
done
PY="${C147_PY:-$R/.venv-bench/bin/python}"
mkdir -p "$D"
/bin/rm -f "$D/chain.rc"
cd "$R" && "$PY" "$R/benchmark/chains/c147/run_tg1_chain.py" "$@" --predictor mtp --out-root "$D" > "$D/chain.out" 2>&1 < /dev/null; rc=$?
echo $rc > "$D/chain.rc"
exit $rc
