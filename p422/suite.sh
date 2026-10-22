#!/bin/zsh
# P422 fork suite (+ the eight gating audits when $2 == audits) on the fork worktree head; $1 = run label
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
mkdir -p "${TMPDIR:-/tmp}"
cd $HOME/ws/mlx-vlm || exit 2
git rev-parse HEAD
(cd mlx_vlm && ../.venv/bin/python -m pytest -q -p no:cacheprovider ./tests --ignore=tests/test_smoke.py -rs)
rc=$?
echo "SUITE_EXIT=$rc"
[ $rc -ne 0 ] && exit $rc
if [ "$2" = audits ]; then
  for a in check_upstream_parity check_upstream_symbols check_upstream_deletions check_dead_helpers check_fork_markers \
           check_body_divergence check_upstream_registries check_call_arguments; do
    .venv/bin/python dev/$a.py --upstream-ref 952d4f6b
    arc=$?
    echo "AUDIT $a EXIT=$arc"
    [ $arc -ne 0 ] && rc=$arc
  done
fi
echo "ALL_EXIT=$rc"
exit $rc
