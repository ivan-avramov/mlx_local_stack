#!/bin/bash
# usage: run_codex.sh <name> <mode: write|ro>   (prompt: $STACK_WORKDIR/m61/<name>.prompt.md -> codex_<name>.{md,log,rc})
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/m61"; n="$1"
/bin/rm -f "$D/codex_$n.rc"
if [ "$2" = write ]; then S=(-s workspace-write -c 'sandbox_workspace_write.network_access=true'); else S=(-s read-only); fi
TMPDIR="$D/tmp" STACK_WORKDIR="$STACK_WORKDIR" codex exec -m gpt-6-astra "${S[@]}" --skip-git-repo-check -C "${3:-$HOME/ws/mlx_local_stack}" \
  -o "$D/codex_$n.md" - < "$D/$n.prompt.md" > "$D/codex_$n.log" 2>&1
echo $? > "$D/codex_$n.rc"
