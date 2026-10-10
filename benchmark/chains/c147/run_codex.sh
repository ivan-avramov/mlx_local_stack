#!/bin/bash
# C147 cold reviews/implementers on Codex. usage: run_codex.sh <name> <mode: write|ro> [model] [repo]
# prompt: $STACK_WORKDIR/c147/<name>.prompt.md -> $STACK_WORKDIR/c147/codex_<name>.{md,log,rc}
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
D="$STACK_WORKDIR/c147"; n="$1"; M="${3:-gpt-6.1-sol}"
mkdir -p "$D/tmp"; /bin/rm -f "$D/codex_$n.rc"
if [ "$2" = write ]; then S=(-s workspace-write -c 'sandbox_workspace_write.network_access=true'); else S=(-s read-only); fi
TMPDIR="$D/tmp" STACK_WORKDIR="$STACK_WORKDIR" codex exec -m "$M" "${S[@]}" --skip-git-repo-check -C "${4:-$STACK_REPO}" \
  -o "$D/codex_$n.md" - < "$D/$n.prompt.md" > "$D/codex_$n.log" 2>&1
echo $? > "$D/codex_$n.rc"
