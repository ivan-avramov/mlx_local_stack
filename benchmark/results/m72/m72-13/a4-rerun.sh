#!/bin/zsh
set -u
L=$STACK_WORKDIR/m72/real-s21/chain.log; log() { echo "[$(date +%H:%M:%S)] $*" >> $L; }
[ "$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c LISTEN)" = "0" ] || exit 9
export PYTHONPATH=$STACK_WORKDIR/fe-m72-13/impl/mlx-vlm STACK_WORKDIR=$STACK_WORKDIR/fe-m72-13/impl/workdir; cd $STACK_WORKDIR/fe-m72-13/impl/mlx_local_stack
for spec in "m72_exact 8192" "m72_exact 32768" "m72_v1 8192"; do m=${spec% *}; t=${spec#* }
  log "BEGIN a4 rerun $m $t"; uv run --project $STACK_REPO python $STACK_WORKDIR/m72/real-s21/m72_13_realmodel.py --check a4 --mode $m --T $t --out $STACK_WORKDIR/m72/real-s21/a4-${m#m72_}-$t.json >> $STACK_WORKDIR/m72/real-s21/steps.log 2>&1; rc=$?; log "END rc=$rc"; [ $rc -eq 0 ] || exit 21
done
log "A4 RERUN DONE"
