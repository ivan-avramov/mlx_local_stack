#!/bin/bash
# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m59/run_codex_ro.sh, the driver behind the opencode_v2_*.m59.* (M59) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m59"; n="$1"
/bin/rm -f "$D/codex_$n.rc"
TMPDIR="$D/review_opus_fix_tmp" codex exec -m gpt-6-astra -s read-only --skip-git-repo-check -C "$HOME/ws/mlx_local_stack" \
  -o "$D/codex_$n.md" - < "$D/$n.prompt.md" > "$D/codex_$n.log" 2>&1
echo $? > "$D/codex_$n.rc"
