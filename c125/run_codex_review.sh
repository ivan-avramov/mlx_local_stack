#!/bin/bash
# usage: run_codex_review.sh <name>   (prompt: review_<name>.prompt.md -> codex_review_<name>.{md,log,rc})
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/c125"; n="$1"
/bin/rm -f "$D/codex_review_$n.rc"
TMPDIR="$D/tmp" codex exec -m gpt-6-astra -s read-only --skip-git-repo-check -C "$HOME/ws/mlx_local_stack" \
  -o "$D/codex_review_$n.md" - < "$D/review_$n.prompt.md" > "$D/codex_review_$n.log" 2>&1
echo $? > "$D/codex_review_$n.rc"
