#!/bin/zsh
# C255 / C249 part (2): normal-length decode speed ON vs OFF per entry — math500, a seeded-random 20 items (P546) shared by both arms,
# deployed sampling, a lean router per arm worktree (MLX_VLM_CACHE_SESSION_MAX=1), one order-balanced pair per entry, >= 10 min idle,
# the bench watcher every 5 min with power. ON = worktree stack-c249 (main e3c70a79); OFF = stack-c249-off (e3c70a79 + all four OFF).
set -u
set -a; . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"; set +a
W=$STACK_WORKDIR/worktrees
P2=$STACK_WORKDIR/p369/phase2
LOG=$P2/c249-part2.log
N=20
SEED=1355
port_free() { ! lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; }
note() { print "$(date -u +%FT%TZ) $* | $(pmset -g ac | tr -s ' ' | tr '\n' ' ' | cut -c1-80) | $(pmset -g batt | tail -1 | tr -s ' ')" >> $LOG; }
run_arm() {  # $1 entry  $2 arm (on|off)
  local m=$1 arm=$2 wt tune o
  [[ $arm == on ]] && wt=$W/stack-c249 || wt=$W/stack-c249-off
  tune=c249-mtp$arm-20261030
  o=$P2/c249p2-${m}-$arm
  port_free || { note "REFUSED :8000 busy before $m $arm"; return 2; }
  note "START $m arm=$arm wt=$wt"
  (cd $wt && MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=$wt/main_models.yaml nohup uv run mlx-serve start > $wt/logs/main_model.log 2>&1 < /dev/null &)
  local i=0
  until curl -sf http://127.0.0.1:8000/v1/models >/dev/null 2>&1; do i=$((i+1)); (( i > 120 )) && { note "router not ready $m $arm"; return 3; }; sleep 5; done
  note "router ready $m $arm (owner $(lsof -nP -iTCP:8000 -sTCP:LISTEN -t | head -1))"
  (cd $wt/benchmark && MLX_SERVE_CONFIG=$wt/main_models.yaml $wt/.venv-bench/bin/python run.py generate --models $m --benches math500 \
      --limit math500=$N --seed $SEED --seed-base $SEED --sampling-profile deployed --order roundrobin --chunks all --tune $tune \
      > $o.generate.log 2>&1) &
  local gpid=$!
  (cd $wt/benchmark && $wt/.venv-bench/bin/python m1/bench_watch.py --models $m --bench math500 --tune $tune --total $N \
      --driver-pid $gpid --out $o.watch.log --interval 300 > $o.watch.out 2>&1) &
  local wpid=$!
  wait $gpid; local rc=$?
  kill $wpid 2>/dev/null; wait $wpid 2>/dev/null
  note "END generate $m arm=$arm rc=$rc"
  (cd $wt && ./scripts/stack_stop.sh >> $o.stop.log 2>&1)
  i=0; until port_free; do i=$((i+1)); (( i > 60 )) && { note "router did not stop $m $arm"; return 4; }; sleep 5; done
  note "STOPPED $m arm=$arm"
  return $rc
}
overall=0; first=1
for pair in "Qwen3.8-27B-mlx-uniform-4bit:on:off" "Qwen3.6-27B-Opus-Distill-OptiQ-4bit:off:on" "Ornith-1.0-35B-mlx-uniform-4bit:on:off"; do
  m=${pair%%:*}; rest=${pair#*:}; a1=${rest%%:*}; a2=${rest##*:}
  for arm in $a1 $a2; do
    (( first )) || sleep 600
    first=0
    run_arm $m $arm || { overall=1; note "STOP: arm failed ($m $arm)"; exit 1; }
  done
done
note "DONE"
exit $overall
