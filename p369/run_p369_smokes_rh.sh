#!/bin/zsh
# P535: the authorizing P369 smokes for the C248 full runs — same stack root (all-OFF worktree) and fork as the full runs, with
# --reviewed-head 1cce312f (C251). Sequential; one log + rc per pick.
set -u
set -a; . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"; set +a
STACK=$STACK_WORKDIR/worktrees/stack-p369-full-off
FORK=$STACK_WORKDIR/p369/fork-1cce312f
P2=$STACK_WORKDIR/p369/phase2
overall=0
for spec in "Qwen3.8-27B-mlx-uniform-4bit:uniform" "Qwen3.6-27B-Opus-Distill-OptiQ-4bit:qwen36" "Ornith-1.0-35B-mlx-uniform-4bit:ornith" "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed:fable"; do
  m=${spec%%:*}; tag=${spec##*:}
  o=$P2/20261029-1cce312f-smoke-$tag-s2-rh
  print "$(date -u +%FT%TZ) START smoke-rh $m -> $o" >> $P2/c248-full.log
  (cd $FORK && $STACK/.venv/bin/python dev/p369_phase2/orchestrate.py --stack-root $STACK --fork-root $FORK \
      --out $o --phase smoke --pick $m --reviewed-head 1cce312f > $o.log 2>&1)
  rc=$?
  print $rc > $o.rc
  print "$(date -u +%FT%TZ) END smoke-rh $m rc=$rc" >> $P2/c248-full.log
  (( rc != 0 )) && overall=1
done
exit $overall
