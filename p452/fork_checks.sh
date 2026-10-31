#!/usr/bin/env bash
set -uo pipefail
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
F=$HOME/ws/mlx-vlm; O=$STACK_WORKDIR/p452; H=$(git -C $F rev-parse HEAD); echo "fork head $H"
[ -z "$(git -C $F status --porcelain --untracked-files=no)" ] || { echo "fork tree dirty"; exit 1; }
for i in 1 2; do (cd $F/mlx_vlm && ../.venv/bin/python -m pytest -q -p no:cacheprovider ./tests > $O/fork-suite-$i.log 2>&1); echo "suite $i rc=$? $(grep -E 'passed|failed' $O/fork-suite-$i.log | tail -1)"; done
S=$O/audit-clone; rm -rf $S; git clone -q --no-hardlinks $F $S && git -C $S checkout -q --detach $H && git -C $S remote add upstream https://github.com/Blaizzy/mlx-vlm.git && git -C $S remote set-url --push upstream no_push && git -C $S fetch -q --no-tags upstream main "+refs/tags/*:refs/tags/*" || { echo "audit clone / fetch failed"; exit 1; }
REF=$(grep -E '^\s*UPSTREAM_SYNC_REF:' $S/.github/workflows/upstream-parity.yml | awk '{print $2}'); echo "parity ref $REF"
rc_all=0
for a in check_upstream_parity check_upstream_symbols "check_upstream_deletions --strict" check_fork_markers check_dead_helpers check_body_divergence check_upstream_registries check_call_arguments; do
  set -- $a; n=$1; shift
  (cd $S && $F/.venv/bin/python dev/$n.py --upstream-ref $REF "$@" > $O/audit-$n.log 2>&1); rc=$?; [ $rc = 0 ] || rc_all=1; echo "audit $n rc=$rc"
done
rm -rf $S; echo "audits rc_all=$rc_all"
