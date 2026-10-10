#!/bin/bash
# usage: run_codex.sh <name> <repo-dir>   (prompt: $STACK_WORKDIR/m59/<name>.prompt.md -> codex_<name>.{md,log,rc}); workspace-write + loopback network
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m59"; n="$1"; R="$2"
/bin/rm -f "$D/codex_$n.rc"
TMPDIR="$D/tmp" STACK_WORKDIR="$STACK_WORKDIR" codex exec -m gpt-6-astra -s workspace-write --skip-git-repo-check \
  -c 'sandbox_workspace_write.network_access=true' -C "$R" \
  -o "$D/codex_$n.md" - < "$D/$n.prompt.md" > "$D/codex_$n.log" 2>&1
echo $? > "$D/codex_$n.rc"
