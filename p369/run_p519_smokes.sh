#!/bin/zsh
# P519 (session 11): P369 regression smoke on S' for each remaining MTP entry, sequentially; one log + rc per entry.
set -u
set -a; . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"; set +a
PY=$HOME/ws/mlx_local_stack/.venv/bin/python
FORK=$STACK_WORKDIR/p369/fork-1cce312f
P2=$STACK_WORKDIR/p369/phase2
overall=0
for spec in "Qwen3.8-27B-mlx-uniform-4bit:uniform" "Qwen3.6-27B-Opus-Distill-OptiQ-4bit:qwen36" "Ornith-1.0-35B-mlx-uniform-4bit:ornith"; do
  m=${spec%%:*}; tag=${spec##*:}
  o=$P2/20261029-1cce312f-smoke-$tag-s2
  print "$(date -u +%FT%TZ) START $m -> $o" >> $P2/p519-smokes.log
  (cd $FORK && $PY dev/p369_phase2/orchestrate.py --stack-root $HOME/ws/mlx_local_stack --fork-root $FORK \
      --out $o --phase smoke --pick $m > $o.log 2>&1)
  rc=$?
  print $rc > $o.rc
  print "$(date -u +%FT%TZ) END $m rc=$rc" >> $P2/p519-smokes.log
  (( rc != 0 )) && overall=1
done
exit $overall
