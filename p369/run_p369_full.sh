#!/bin/zsh
# C248 / C251: one P369 --phase full run for one pick on S'. Stack root = the all-OFF worktree (P527); fork = the reviewed head 1cce312f.
# Usage: run_p369_full.sh <full registry name> <tag> <passed smoke dir>
set -u
set -a; . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"; set +a
pick=$1; tag=$2; smoke=$3
STACK=$STACK_WORKDIR/worktrees/stack-p369-full-off
FORK=$STACK_WORKDIR/p369/fork-1cce312f
P2=$STACK_WORKDIR/p369/phase2
o=$P2/$(date -u +%Y%m%d)-1cce312f-full-$tag-s2
print "$(date -u +%FT%TZ) START full $pick -> $o (smoke $smoke)" >> $P2/c248-full.log
(cd $FORK && $STACK/.venv/bin/python dev/p369_phase2/orchestrate.py --stack-root $STACK --fork-root $FORK --out $o \
    --phase full --pick $pick --smoke-summary $smoke/summary.json --reviewed-head 1cce312f > $o.log 2>&1)
rc=$?
print $rc > $o.rc
print "$(date -u +%FT%TZ) END full $pick rc=$rc" >> $P2/c248-full.log
exit $rc
