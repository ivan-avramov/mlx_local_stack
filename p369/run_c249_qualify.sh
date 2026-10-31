#!/bin/zsh
# C249 / C254 part (1): the 256K capacity + decode ON vs OFF per entry, ABBA (OFF, ON, ON, OFF), >= 10 min idle between arms
# (qualify's own --idle-s also applies inside a run). Stack root = a clean worktree at the pushed main e3c70a79 (all four ON);
# fork root = the pushed P542 head fd67082a. MTP-ON arms are gated on each entry's P369 FULL PASS summary.
set -u
set -a; . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"; set +a
STACK=$STACK_WORKDIR/worktrees/stack-c249
FORK=$STACK_WORKDIR/p369/fork-fd67082a
P2=$STACK_WORKDIR/p369/phase2
PY=$FORK/.venv/bin/python
typeset -A SUM
SUM[Qwen3.8-27B-mlx-uniform-4bit]=$P2/20261029-a4cd07e0-full-uniform-s2/summary.json
SUM[Qwen3.6-27B-Opus-Distill-OptiQ-4bit]=$P2/20261029-1cce312f-full-qwen36-s2/summary.json
SUM[Ornith-1.0-35B-mlx-uniform-4bit]=$P2/20261029-1cce312f-full-ornith-s2/summary.json
typeset -A TAG
TAG[Qwen3.8-27B-mlx-uniform-4bit]=uniform; TAG[Qwen3.6-27B-Opus-Distill-OptiQ-4bit]=qwen36; TAG[Ornith-1.0-35B-mlx-uniform-4bit]=ornith
LOG=$P2/c249.log
overall=0; first=1
for m in Qwen3.8-27B-mlx-uniform-4bit Qwen3.6-27B-Opus-Distill-OptiQ-4bit Ornith-1.0-35B-mlx-uniform-4bit; do
  k=0
  for arm in off on on off; do
    k=$((k+1))
    (( first )) || sleep 600
    first=0
    o=$P2/20261030-fd67082a-c249-${TAG[$m]}-$k-$arm
    print "$(date -u +%FT%TZ) START $m arm=$arm k=$k -> $o $(pmset -g batt | tail -1 | tr -s ' ')" >> $LOG
    if [[ $arm == on ]]; then
      (cd $FORK && $PY dev/p369_phase2/qualify.py --stack-root $STACK --fork-root $FORK --out $o --entry $m \
          --predictor on --p369-summary $m=${SUM[$m]} --reviewed-head fd67082a > $o.log 2>&1)
    else
      (cd $FORK && $PY dev/p369_phase2/qualify.py --stack-root $STACK --fork-root $FORK --out $o --entry $m \
          --predictor off --reviewed-head fd67082a > $o.log 2>&1)
    fi
    rc=$?; print $rc > $o.rc
    print "$(date -u +%FT%TZ) END $m arm=$arm k=$k rc=$rc" >> $LOG
    (( rc != 0 )) && overall=1
  done
done
exit $overall
