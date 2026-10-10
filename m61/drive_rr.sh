#!/bin/bash
# C139(b) re-record: waits for the A/B driver to finish (rc 0) AND for rr_ready (set by the operator's session after the P202
# fixes are merged + full suites green), then 140 W check, watchdog, run_m61_rr.py s1 s2. rc in drive_rr.rc.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m61"; R="$HOME/ws/mlx_local_stack"; PY="$R/.venv-bench/bin/python"
/bin/rm -f "$D/drive_rr.rc"
log() { echo "- $(date -u +%Y-%m-%dT%H:%M:%SZ) DRIVE-RR $*" >> "$D/RUNLOG.md"; }
log "armed: waiting for drive_ab.rc=0 and rr_ready"
while [ ! -f "$D/drive_ab.rc" ] || [ ! -f "$D/rr_ready" ]; do sleep 60; done
[ "$(cat "$D/drive_ab.rc")" = "0" ] || { log "A/B rc=$(cat "$D/drive_ab.rc"): not starting"; echo 8 > "$D/drive_rr.rc"; exit 8; }
[ "$(pmset -g ac | awk '/Wattage/{print $3}')" = "140W" ] || { log "adapter not 140W: not starting"; echo 9 > "$D/drive_rr.rc"; exit 9; }
sleep 30
# rr_ready holds the reviewed m61-r5 commit; fast-forward main to it (main is idle now), then full suites must pass
want=$(cat "$D/rr_ready"); git -C "$R" merge --ff-only "$want" >> "$D/drive_rr.out" 2>&1 || { log "ff-merge to $want failed"; echo 7 > "$D/drive_rr.rc"; exit 7; }
[ "$(git -C "$R" rev-parse HEAD)" = "$(git -C "$R" rev-parse "$want")" ] || { log "main != $want after merge"; echo 7 > "$D/drive_rr.rc"; exit 7; }
( cd "$R/benchmark" && env -u STACK_WORKDIR ../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider > "$D/rr_suite_bench.log" 2>&1 ); b=$?
( cd "$R" && env -u STACK_WORKDIR .venv-bench/bin/python -m pytest configgen/tests -q -p no:cacheprovider > "$D/rr_suite_configgen.log" 2>&1 ); c=$?
log "pre-run suites bench rc=$b ($(tail -1 "$D/rr_suite_bench.log")) configgen rc=$c"
if [ $b != 0 ]; then
  # one retry for the known load-flaky test_runserver_term only
  if grep -E "^FAILED" "$D/rr_suite_bench.log" | grep -v test_runserver_term -q; then log "suite failures: not starting"; echo 6 > "$D/drive_rr.rc"; exit 6; fi
  ( cd "$R/benchmark" && env -u STACK_WORKDIR ../.venv-bench/bin/python -m pytest bench/tests/test_runserver_term.py -q -p no:cacheprovider >> "$D/rr_suite_bench.log" 2>&1 ) || { log "runserver_term failed twice: not starting"; echo 6 > "$D/drive_rr.rc"; exit 6; }
fi
[ $c = 0 ] || { log "configgen suite failed: not starting"; echo 6 > "$D/drive_rr.rc"; exit 6; }
log "starting re-record (main=$(git -C "$R" rev-parse --short HEAD))"
nohup "$PY" "$STACK_WORKDIR/m59/mem_watchdog.py" --log "$D/RUNLOG.md" --stop-file "$D/drive_rr.rc" > "$D/mem_watchdog_rr.out" 2>&1 < /dev/null &
cd "$R" && set -a && . ./.env 2>/dev/null; set +a; unset APC_ENABLED
"$PY" "$D/run_m61_rr.py" s1 s2 > "$D/rr.out" 2>&1; rc=$?
log "re-record rc=$rc"
echo $rc > "$D/drive_rr.rc"
