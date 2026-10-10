#!/bin/bash
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m59"; n="$1"
/bin/rm -f "$D/codex_$n.rc"
TMPDIR="$D/review_opus_fix_tmp" codex exec -m gpt-6-astra -s read-only --skip-git-repo-check -C "$HOME/ws/mlx_local_stack" \
  -o "$D/codex_$n.md" - < "$D/$n.prompt.md" > "$D/codex_$n.log" 2>&1
echo $? > "$D/codex_$n.rc"
