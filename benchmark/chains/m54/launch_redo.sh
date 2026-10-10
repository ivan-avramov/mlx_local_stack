#!/bin/bash
# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m54/launch_redo.sh, the driver behind the agentbench_os.v1.chain* (M54) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
# Unattended: wait for chain 4 runner to finish, verify preconditions, launch redo of arms 1+2 on the SAME router session.
M=$STACK_WORKDIR/m54; R=$STACK_REPO
A=$M/arms_aac939b; O=$M/arms_aac939b_redo; LOG=$M/launch_redo.log
ROUTER_PID=90462; OV_SHA=81fa0c15a0de17a1
PY=$R/.venv-bench/bin/python
MODELS="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed Qwen3.8-27B-mlx-uniform-4bit"
log(){ echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a $LOG; }
log "launcher armed pid $$; waiting for ALL ARMS COMPLETE and runner exit"
while [ "$1" != "--now" ]; do
  if /usr/bin/grep -q "ALL ARMS COMPLETE" $A/RUNLOG.md && ! pgrep -f "arms_aac939b/run_arms.py" >/dev/null; then break; fi
  if ! pgrep -f "arms_aac939b/run_arms.py" >/dev/null && ! /usr/bin/grep -q "ALL ARMS COMPLETE" $A/RUNLOG.md; then
    log "ABORT: runner exited WITHOUT ALL ARMS COMPLETE (chain stopped early) -- not launching redo"; exit 3; fi
  sleep 60
done
log "chain 4 runner finished; checking preconditions"
sleep 30
fail=0
owner=$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t | sort -u | tr '\n' ' ')
[ "$owner" = "$ROUTER_PID " ] || { log "FAIL router owner on :8000 = '$owner' (expected $ROUTER_PID)"; fail=1; }
curl -s -m 10 http://localhost:8000/v1/models >/dev/null || { log "FAIL router not answering"; fail=1; }
n=$(pgrep -f "bench.run_agentbench_os|opencode run|session_cache_probe|agentbench_watch" | wc -l | tr -d ' '); [ "$n" = "0" ] || { log "FAIL $n driver/probe/watch processes alive"; fail=1; }
$R/scripts/sweep_orphan_shells.sh --kill >> $LOG 2>&1; $R/scripts/sweep_orphan_shells.sh | /usr/bin/grep -q "no orphaned" || { log "FAIL orphans remain"; fail=1; }
docker ps -q --filter name=agentbench-os | /usr/bin/grep -q . && { log "WARN agentbench containers still present:"; docker ps --filter name=agentbench-os --format '{{.Names}}' >> $LOG; }
w=$(pmset -g ac | awk '/Wattage/{print $3}'); [ "$w" = "140W" ] || { log "FAIL adapter wattage '$w' (need 140W)"; fail=1; }
b=$(pmset -g batt | /usr/bin/grep -oE '[0-9]+%' | head -1 | tr -d '%'); [ "${b:-0}" -ge 20 ] || { log "FAIL battery ${b}% < 20"; fail=1; }
s=$(shasum -a 256 $M/overlay_m54_draft_off.yaml | cut -c1-16); [ "$s" = "$OV_SHA" ] || { log "FAIL overlay sha $s != $OV_SHA"; fail=1; }
ps -Eww -o command= -p $ROUTER_PID | /usr/bin/grep -q "APC_ENABLED" && { log "FAIL APC_ENABLED present on router"; fail=1; }
l=$(uptime | sed 's/.*averages: //'); log "load=$l batt=${b}% adapter=$w orphans=0 router=$ROUTER_PID sha=$s"
[ $fail = 0 ] || { log "PRECONDITIONS FAILED -- redo NOT launched; fix and run: $M/launch_redo.sh --now"; exit 2; }
mkdir -p $O; cd $R; set -a; . ./.env 2>/dev/null; set +a
nohup $PY $M/run_arms_redo.py $MODELS > $O/runner.stdout 2>&1 </dev/null &
echo $! > $O/runner.pid; log "REDO LAUNCHED runner pid $! models=[$MODELS] out=$O"
