#!/bin/bash
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
export PATH="$HOME/.orbstack/bin:$PATH"
export C147_OVERLAY="$STACK_WORKDIR/p426/tg1-rehearsal-20261023/overlay_draft_off.yaml"
cd "$STACK_REPO" && "$STACK_REPO/.venv-bench/bin/python" "$STACK_REPO/benchmark/chains/c147/run_tg1_chain.py" chain s1 s2 reload --smoke \
  --probe-code-sha 9d9b97f9544ffa5667e53460966576341538b54f1286b953e664466071442022 \
  --frozen-prompt-date 'Fri Oct 23 2026' --out-root "$STACK_WORKDIR/p426/tg1-rehearsal-20261023" > "$STACK_WORKDIR/p426/tg1-rehearsal-20261023/chain.out" 2>&1 < /dev/null; rc=$?
echo $rc > "$STACK_WORKDIR/p426/tg1-rehearsal-20261023/chain.rc"
exit $rc
