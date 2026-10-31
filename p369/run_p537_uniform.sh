#!/bin/zsh
# C252: Qwen3.8-27B-mlx-uniform-4bit — authorizing smoke, then full, on the reviewed head a4cd07e0 (P537 straddle offsets,
# P527 guard), stack root = the all-OFF worktree. Stops after the smoke unless it is SMOKE_PASS.
set -u
set -a; . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"; set +a
STACK=$STACK_WORKDIR/worktrees/stack-p369-full-off
FORK=$STACK_WORKDIR/p369/fork-a4cd07e0
P2=$STACK_WORKDIR/p369/phase2
PICK=Qwen3.8-27B-mlx-uniform-4bit
SM=$P2/20261029-a4cd07e0-smoke-uniform-s2
FU=$P2/20261029-a4cd07e0-full-uniform-s2
print "$(date -u +%FT%TZ) START smoke $PICK -> $SM (reviewed head a4cd07e0)" >> $P2/c248-full.log
(cd $FORK && $STACK/.venv/bin/python dev/p369_phase2/orchestrate.py --stack-root $STACK --fork-root $FORK --out $SM \
    --phase smoke --pick $PICK --reviewed-head a4cd07e0 > $SM.log 2>&1)
rc=$?; print $rc > $SM.rc
print "$(date -u +%FT%TZ) END smoke $PICK rc=$rc" >> $P2/c248-full.log
(( rc == 0 )) || exit $rc
print "$(date -u +%FT%TZ) START full $PICK -> $FU (smoke $SM)" >> $P2/c248-full.log
(cd $FORK && $STACK/.venv/bin/python dev/p369_phase2/orchestrate.py --stack-root $STACK --fork-root $FORK --out $FU \
    --phase full --pick $PICK --smoke-summary $SM/summary.json --reviewed-head a4cd07e0 > $FU.log 2>&1)
rc=$?; print $rc > $FU.rc
print "$(date -u +%FT%TZ) END full $PICK rc=$rc" >> $P2/c248-full.log
exit $rc
