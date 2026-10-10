#!/bin/bash
# usage: run_codex_work.sh <dir-under-STACK_WORKDIR> <name>  (prompt: <name>.prompt.md -> codex_<name>.{md,log,rc}); workspace-write in the stack repo
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/$1"; n="$2"
/bin/rm -f "$D/codex_$n.rc"
TMPDIR="$D/tmp" codex exec -m gpt-6-astra -s workspace-write --skip-git-repo-check -C "$HOME/ws/mlx_local_stack" \
  -o "$D/codex_$n.md" - < "$D/$n.prompt.md" > "$D/codex_$n.log" 2>&1
echo $? > "$D/codex_$n.rc"
