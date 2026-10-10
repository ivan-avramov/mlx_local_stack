#!/bin/bash
# M61 box run part 1: wait for the 140 W adapter (max 12 h), arm the P183 watchdog, smoke (opencode-v2-web, --limit 5, twice) +
# its web audit, then the P198 prompt A/B. rc markers per phase; the watchdog stops when drive_ab.rc appears.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m61"; R="$HOME/ws/mlx_local_stack"; PY="$R/.venv-bench/bin/python"
/bin/rm -f "$D/drive_ab.rc" "$D/smoke.rc" "$D/ab.rc"
log() { echo "- $(date -u +%Y-%m-%dT%H:%M:%SZ) DRIVE $*" >> "$D/RUNLOG.md"; }
for i in $(seq 1 720); do
  w=$(pmset -g ac | awk '/Wattage/{print $3}')
  [ "$w" = "140W" ] && break
  [ $((i % 30)) = 1 ] && log "waiting for 140W adapter (now $w)"
  sleep 60
done
[ "$(pmset -g ac | awk '/Wattage/{print $3}')" = "140W" ] || { log "adapter never reached 140W: abort"; echo 9 > "$D/drive_ab.rc"; exit 9; }
log "adapter 140W; arming watchdog"
nohup "$PY" "$STACK_WORKDIR/m59/mem_watchdog.py" --log "$D/RUNLOG.md" --stop-file "$D/drive_ab.rc" > "$D/mem_watchdog.out" 2>&1 < /dev/null &
cd "$R" && set -a && . ./.env 2>/dev/null; set +a; unset APC_ENABLED
"$PY" "$D/run_m61.py" smoke > "$D/smoke.out" 2>&1; rc=$?; echo $rc > "$D/smoke.rc"
[ $rc = 0 ] || { log "smoke rc=$rc: stop"; echo $rc > "$D/drive_ab.rc"; exit $rc; }
for f in "$D"/smoke/*.web.python.p*.jsonl; do "$PY" "$R/benchmark/web_audit.py" "$f" >> "$D/smoke_audit.out" 2>&1; log "web_audit $(basename "$f") rc=$?"; done
"$PY" "$D/run_m61.py" ab > "$D/ab.out" 2>&1; rc=$?; echo $rc > "$D/ab.rc"
log "ab rc=$rc"
echo $rc > "$D/drive_ab.rc"
